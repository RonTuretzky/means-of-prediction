import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import round4
import complete_body_feedback as body

class CompleteBodyTests(unittest.TestCase):
    def fixture(self,d):
        root=Path(d)/'slides/round';root.mkdir(parents=True)
        archive=Path(d)/'nyt';(archive/'raw').mkdir(parents=True)
        raw=b'Subject: Example\r\n\r\nFull message with footer and URL'
        mid=hashlib.sha256(raw).hexdigest();(archive/'raw'/(mid+'.eml')).write_bytes(raw)
        html='<p>Result <a href="https://example.test/long">link</a></p><footer>Full footer</footer>'
        full='Result link [https://example.test/long]\nFull footer'
        (root/'development-corpus.private.json').write_text(json.dumps([{'id':mid,'html':html,'text':'Result link','profileCompatible':True}]))
        db=sqlite3.connect(archive/'mail.sqlite');db.execute('CREATE TABLE messages (id TEXT,body TEXT,metadata TEXT,subject TEXT)')
        db.execute('INSERT INTO messages VALUES (?,?,?,?)',(mid,full,'{"attachmentCount":0}','Example'));db.commit();db.close()
        return root,archive,mid,html,full

    def test_full_source_footer_and_url_are_preserved_even_when_old_text_is_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            root,archive,mid,html,full=self.fixture(d)
            with patch.object(body,'ROOT',root),patch.object(round4,'ROOT',root),patch.object(body,'BASE',root.parent),patch('builtins.print'):
                body.prepare()
            manifest=json.loads((root/'complete-body-supplement-manifest.json').read_text())
            email=json.loads((root/'complete-body-inputs/0.private.json').read_text())['emails'][0]
            self.assertEqual(manifest['cleanedTextInOriginalCorpus'],1)
            self.assertEqual(email['fullMailparserText'],full);self.assertEqual(email['fullHtml'],html)
            self.assertEqual(email['subject'],'Example')
            self.assertEqual(json.loads((root/'development-corpus.private.json').read_text())[0]['text'],'Result link')

    def test_changed_raw_email_cannot_enter_full_body_learning(self):
        with tempfile.TemporaryDirectory() as d:
            root,archive,mid,html,full=self.fixture(d)
            (archive/'raw'/(mid+'.eml')).write_bytes(b'Changed content')
            with patch.object(body,'ROOT',root),patch.object(round4,'ROOT',root),patch.object(body,'BASE',root.parent):
                with self.assertRaisesRegex(RuntimeError,'Content-addressed email changed'):body.prepare()
            self.assertFalse((root/'complete-body-supplement-manifest.json').exists())

    def test_unindexed_attachments_cannot_be_claimed_as_complete_email_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root,archive,mid,html,full=self.fixture(d)
            db=sqlite3.connect(archive/'mail.sqlite');db.execute('UPDATE messages SET metadata=?',('{"attachmentCount":1}',));db.commit();db.close()
            with patch.object(body,'ROOT',root),patch.object(round4,'ROOT',root),patch.object(body,'BASE',root.parent):
                with self.assertRaisesRegex(RuntimeError,'Attachment content'):body.prepare()

if __name__=='__main__':unittest.main()
