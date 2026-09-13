import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {signEml} from './dkim.mjs';
import {parseEml,buildEmailProof} from '../src/lib/prover.ts';
import {canonicalizeBody,decodeBodyWindow,latin1Bytes,substringPattern} from '../src/lib/body.ts';
const hash='0x'+'00'.repeat(32);
function fixture(body, extra='', headers=['from','subject','date','content-type']) {
 return signEml('From: Demo <demo@fixture.example>\r\nSubject: Daily newsletter\r\nDate: Thu, 10 Sep 2026 12:00:00 +0000\r\nContent-Type: text/html; charset=utf-8\r\n'+extra+'\r\n'+body,{domain:'fixture.example',headers});
}
test('quoted-printable body proof binds exact decoded UTF-8 bytes and signed hash',()=>{
 const p=parseEml(fixture('<p>Foulkes won the Demo=\r\ncratic primary. Caf=C3=A9.</p>\r\n'));
 const proof=buildEmailProof(p,hash,{contentField:1,pattern:'Foulkes won the Democratic primary'});
 assert.match(p.bodyExcerpt,/Café/);
 assert.match(buildEmailProof(p,hash,{contentField:1,pattern:"Café"}).bodyExcerpt,/Café/);
 const bh=/bh=([^;]+)/.exec(Buffer.from(p.headerBytes).toString('latin1'))[1];
 assert.equal(createHash('sha256').update(p.canonicalBody).digest('base64'),bh);
 assert.equal(Buffer.from(decodeBodyWindow(p.canonicalBody,Number(proof.bodyOffset),Number(proof.bodyLength),1)).toString('utf8'),proof.bodyExcerpt);
});
test('unsigned transfer-encoding cannot change the fixed body profile',()=>{
 const raw=fixture('<p>A=20B</p>\r\n','Content-Transfer-Encoding: quoted-printable\r\n');
 const a=parseEml(raw),b=parseEml(raw.replace('Content-Transfer-Encoding: quoted-printable','Content-Transfer-Encoding: base64'));
 assert.equal(a.bodyExcerpt,b.bodyExcerpt);assert.match(a.bodyExcerpt,/A B/);
});
test('signed unsupported encoding is refused',()=>{
 const p=parseEml(fixture('SGVsbG8=\r\n','Content-Transfer-Encoding: base64\r\n',['from','subject','date','content-type','content-transfer-encoding']));
 assert.match(p.bodyError,/Unsupported/);assert.throws(()=>buildEmailProof(p,hash,{contentField:1,pattern:'Hello'}));
});
test('body anchors and malformed escape boundaries are rejected',()=>{
 assert.equal(substringPattern('^Fed cuts rates$'),false);assert.equal(substringPattern('[^a].*\\$40'),true);
 assert.throws(()=>decodeBodyWindow(latin1Bytes('a=20b'),2,2,1));
 assert.throws(()=>decodeBodyWindow(latin1Bytes('a=20b'),0,2,1));
});
test('large email chooses a tight authenticated window around evidence',()=>{
 const p=parseEml(fixture('<p>'+('padding '.repeat(15000))+'Foulkes won the primary.</p>\r\n'));
 const proof=buildEmailProof(p,hash,{contentField:1,pattern:'Foulkes won the primary'});
 assert.ok(proof.bodyOffset>100000n);assert.ok(proof.bodyLength<512n);assert.match(proof.bodyExcerpt,/Foulkes won the primary/);
});
test('subject-only proofs do not attach private body bytes',()=>{
 const p=parseEml(fixture('Private content\r\n'));const proof=buildEmailProof(p,hash);
 assert.equal(proof.canonicalBody,'0x');assert.equal(proof.bodyExcerpt,'');assert.equal(proof.bodyLength,0n);
});
test('RFC relaxed and simple empty-body canonicalization differs',()=>{
 assert.equal(canonicalizeBody('\r\n\r\n','relaxed').length,0);
 assert.deepEqual(canonicalizeBody('\r\n\r\n','simple'),latin1Bytes('\r\n'));
});
