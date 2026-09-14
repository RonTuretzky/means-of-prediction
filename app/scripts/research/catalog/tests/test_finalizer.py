import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.scripts.research.catalog.finalize_when_ready import ready


class FinalizerTests(unittest.TestCase):
    def test_does_not_trust_checkpoint_without_complete_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'checkpoint.json').write_text(json.dumps({'complete': True, 'nextCursor': None}))
            with patch('app.scripts.research.catalog.finalize_when_ready.alive', return_value=True):
                self.assertFalse(ready([directory], [123])[0])
            (directory / 'manifest.json').write_text(json.dumps({'complete': True}))
            self.assertTrue(ready([directory], [123])[0])

    def test_dead_incomplete_worker_needs_attention(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / 'checkpoint.json').write_text(json.dumps({'complete': False, 'nextCursor': 'opaque'}))
            with patch('app.scripts.research.catalog.finalize_when_ready.alive', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'exited before completion'):
                    ready([directory], [123])
