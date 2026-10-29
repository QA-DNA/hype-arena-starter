"""Boundary tests for the evaluation harness, independent of learned outcomes."""
import unittest

from run import classification, normalize, partition_rows


class ProtocolTests(unittest.TestCase):
    def rows(self):
        return [dict(id="a", text="  STRA\u00dfE \uff21 ", label="true"),
                dict(id="b", text="strasse a", label="false"),
                dict(id="c", text="safe", label="true")]

    def test_unicode_duplicate_training_evidence_is_removed(self):
        rows = self.rows()
        assignments = [dict(split="s", partition=p, id=r["id"])
                       for r, p in zip(rows, ("train", "test", "train"))]
        train, test, provided = partition_rows(rows, assignments, "s")
        self.assertEqual([r["id"] for r in train], ["c"])
        self.assertEqual([r["id"] for r in test], ["b"])
        self.assertEqual(len(provided), 2)
        self.assertEqual(normalize(rows[0]["text"]), normalize(rows[1]["text"]))

    def test_assignment_identity_must_be_complete_unique_and_known(self):
        rows = self.rows()
        valid = [dict(split="s", partition=p, id=r["id"])
                 for r, p in zip(rows, ("train", "test", "train"))]
        for bad in (valid[:-1], valid + [valid[0]],
                    valid[:-1] + [dict(split="s", partition="test", id="unknown")],
                    [dict(r, partition="validation") for r in valid]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                partition_rows(rows, bad, "s")

    def test_brier_and_log_loss_use_actual_probabilities_and_all_classes(self):
        import numpy as np
        result = classification([0, 1, 2], np.array([0, 1, 0]),
                                [[0.8, 0.1, 0.1], [0.2, 0.6, 0.2], [0.5, 0.3, 0.2]])
        self.assertAlmostEqual(result["accuracy"], 2 / 3)
        self.assertAlmostEqual(result["coverage"], 1)
        self.assertAlmostEqual(result["brier"], (0.06 + 0.24 + 0.98) / 3)
        self.assertAlmostEqual(result["log_loss"], -np.log([0.8, 0.6, 0.2]).mean())
        self.assertEqual(result["per_class"]["unsure"]["f1"], 0)


if __name__ == "__main__":
    unittest.main()
