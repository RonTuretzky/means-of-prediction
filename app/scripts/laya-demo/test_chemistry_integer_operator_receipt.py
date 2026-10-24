#!/usr/bin/env python3
"""Adversarial frozen-token derivation tests; private files are read-only."""

import copy
import hashlib
import json
import unittest
from pathlib import Path

from chemistry_integer_operator_receipt import validate_subset


PRIVATE = Path("/Users/wk/.local/share/means-of-prediction/chemistry-demo-20261021")


class FrozenSubsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (PRIVATE / "frozen.private.json").exists():
            raise unittest.SkipTest("local frozen Chemistry fixture absent")
        cls.original = json.loads((PRIVATE / "tokens.private.json").read_text())
        cls.evidence = json.loads((PRIVATE / "frozen.private.json").read_text())
        cls.subset = json.loads((PRIVATE / "tokens.reuters_early.private.json").read_text())
        cls.original_sha = hashlib.sha256((PRIVATE / "tokens.private.json").read_bytes()).hexdigest()

    def test_canonical_subset_accepted(self):
        self.assertEqual(validate_subset(self.subset, self.original, self.evidence,
                                         self.original_sha)["sourceKey"], "reuters_early")

    def test_changed_token_rejected_even_with_self_consistent_metadata(self):
        fake = copy.deepcopy(self.subset)
        fake["variants"][0]["batch"]["input_ids"][0][0] += 1
        with self.assertRaisesRegex(ValueError, "subset differs"):
            validate_subset(fake, self.original, self.evidence, self.original_sha)

    def test_changed_marker_rejected(self):
        fake = copy.deepcopy(self.subset)
        fake["variants"][0]["batch"]["marker_pos"][1][0] += 1
        with self.assertRaisesRegex(ValueError, "subset differs"):
            validate_subset(fake, self.original, self.evidence, self.original_sha)

    def test_copied_gate_hash_with_changed_source_rejected(self):
        fake = copy.deepcopy(self.subset)
        fake["variants"][0]["sourceKey"] = "ap"
        with self.assertRaisesRegex(ValueError, "subset differs"):
            validate_subset(fake, self.original, self.evidence, self.original_sha)

    def test_changed_gate_metadata_rejected(self):
        fake = copy.deepcopy(self.subset)
        fake["variants"][0]["gateHashes"]["tokenIdsHash"] = "0x" + "00" * 32
        with self.assertRaisesRegex(ValueError, "subset differs"):
            validate_subset(fake, self.original, self.evidence, self.original_sha)

    def test_parent_hash_self_claim_rejected(self):
        fake = copy.deepcopy(self.subset)
        fake["parentFrozenTokensSHA256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "subset differs"):
            validate_subset(fake, self.original, self.evidence, self.original_sha)


if __name__ == "__main__":
    unittest.main()
