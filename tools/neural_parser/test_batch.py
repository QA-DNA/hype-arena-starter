"""Adapter invariants and frozen-runtime parity, using public/synthetic text only."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

try:
    from .batch import BatchExtractor, practice_forms, write_json_atomic
except ImportError:
    from batch import BatchExtractor, practice_forms, write_json_atomic


def row(text, id="duplicate", **extra):
    return dict(id=id, text=text, date="2026-10-29", label="", **extra)


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = BatchExtractor(os.environ.get("VERIDYCT_EXTRACTOR_BUNDLE", "/opt/veridyct-extractor/model"), batch_size=7)

    def test_frozen_single_and_batch_parity_with_unicode(self):
        texts = ["Hooly AI Pro costs \u20ac79 per month.",
                 "Hooly AI Pro costs \u20ac71 per month.",
                 "Hooly has 500 employees.",
                 "Hooly is not SOC 2 certified.",
                 "Holdan started at Hooly on 12 January 2026.",
                 "Its version is no newer than 20.0.",
                 "It replies in under a second."]
        expected = [self.engine.engine.extract(t)["form"] for t in texts]
        self.assertTrue(expected[0])
        self.assertTrue(any(a["value"].get("value") == 79 for a in expected[0]))
        self.assertTrue(any(a["value"].get("value") == 71 for a in expected[1]))
        old_batch = self.engine.batch_size
        try:
            for size in (1, 7, 48):
                self.engine.batch_size = size
                output, report = self.engine.extract_rows([row(t) for t in texts * 7])
                self.assertEqual([r["form"] for r in output], expected * 7)
                self.assertEqual([r["text"] for r in output], texts * 7)
                self.assertEqual(report["counts"].get("unsupported", 0), 0)
        finally:
            self.engine.batch_size = old_batch

    def test_preserves_supplied_forms_and_all_row_fields(self):
        atom = {"subject": "known", "attribute": "opaque", "value": {"kind": "quantity", "value": 3}}
        rows = [row("Hooly AI Pro costs \u20ac79 per month.", form=[atom], extra="retained")]
        before = copy.deepcopy(rows)
        output, report = self.engine.extract_rows(rows)
        self.assertEqual(output, before)
        self.assertEqual(rows, before)
        self.assertEqual(report["counts"]["preserved"], 1)

    def test_missing_null_and_empty_forms_are_filled(self):
        rows = [row("Hooly AI Pro costs \u20ac79 per month."),
                row("Hooly AI Pro costs \u20ac79 per month.", form=None),
                row("Hooly AI Pro costs \u20ac79 per month.", form=[])]
        output, _ = self.engine.extract_rows(rows)
        self.assertTrue(output[0]["form"])
        self.assertEqual(output[0]["form"], output[1]["form"])
        self.assertEqual(output[1]["form"], output[2]["form"])

    def test_label_date_and_gold_named_fields_never_become_network_features(self):
        a = row("Hooly AI Pro costs \u20ac79 per month.")
        b = dict(a, date="1900-01-01", label="false", gold={"invented": 99},
                 context_row_id="secret", previous_text="Hooly Workspace.")
        output, _ = self.engine.extract_rows([a, b])
        self.assertEqual(output[0]["form"], output[1]["form"])
        self.assertEqual(output[1]["label"], "false")

    def test_oversized_and_empty_input_do_not_discard_following_rows(self):
        rows = [row("word " * 400, id="too-many-tokens"), row("", id="empty"),
                row("x" * 65537, id="too-many-characters"),
                row("Hooly AI Pro costs \u20ac79 per month.", id="valid")]
        events = []
        output, report = self.engine.extract_rows(rows, events.append)
        self.assertEqual(len(output), 4)
        self.assertEqual(output[0]["form"], [])
        self.assertEqual(output[1]["form"], [])
        self.assertEqual(output[2]["form"], [])
        self.assertTrue(output[3]["form"])
        self.assertEqual(report["counts"]["unsupported"], 2)
        self.assertEqual(len(events), 2)

    def test_empty_array(self):
        output, report = self.engine.extract_rows([])
        self.assertEqual(output, [])
        self.assertEqual(report["counts"]["rows"], 0)

    def test_batch_failure_isolates_single_row(self):
        old_predict = self.engine.engine.predict_encoded

        def fail_bad(items):
            if any(item["id"] == "bad" for item in items):
                raise ValueError("synthetic inference failure")
            return old_predict(items)

        try:
            self.engine.engine.predict_encoded = fail_bad
            rows = [row("Hooly AI Pro costs \u20ac79 per month.", id="bad"),
                    row("Hooly AI Pro costs \u20ac71 per month.", id="good")]
            output, report = self.engine.extract_rows(rows)
            self.assertEqual(output[0]["form"], [])
            self.assertTrue(output[1]["form"])
            self.assertEqual(report["counts"]["unsupported"], 1)
            self.assertEqual(report["unsupported"][0]["code"], "inference")
        finally:
            self.engine.engine.predict_encoded = old_predict

    def test_public_practice_exact_text_reuse_including_empty(self):
        old = self.engine.practice
        try:
            self.engine.practice = {"Hooly AI Pro costs \u20ac79 per month.": []}
            output, report = self.engine.extract_rows([row("Hooly AI Pro costs \u20ac79 per month.")])
            self.assertEqual(output[0]["form"], [])
            self.assertEqual(report["counts"]["practice_reused"], 1)
        finally:
            self.engine.practice = old

    def test_previous_three_is_explicit_public_text_only(self):
        old_context, old_predict = self.engine.context, self.engine.engine.predict_encoded
        seen = {}

        def record(items):
            for item in items:
                seen[item["id"]] = item["previous_text"]
            return old_predict(items)

        try:
            self.engine.context = "previous3text"
            self.engine.engine.predict_encoded = record
            rows = [row("Hooly AI Pro.", id="0"), row("Hooly Workspace.", id="1"),
                    row("Hooly.", id="2"), row("It costs \u20ac79 per month.", id="3"),
                    row("It costs \u20ac71 per month.", id="4")]
            _, report = self.engine.extract_rows(rows)
            self.assertEqual(seen["3"], " ".join(r["text"] for r in rows[:3]))
            self.assertEqual(seen["4"], " ".join(r["text"] for r in rows[1:4]))
            self.assertTrue(report["context_experimental"])
        finally:
            self.engine.context, self.engine.engine.predict_encoded = old_context, old_predict

    def test_atomic_json_unicode(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rows.json"
            write_json_atomic(path, [row("\u20ac79")])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))[0]["text"], "\u20ac79")
            self.assertEqual(len(list(Path(temporary).iterdir())), 1)

    def test_schema_error(self):
        with self.assertRaisesRegex(ValueError, "requires string text"):
            self.engine.extract_rows([{"id": "bad", "date": "2026-10-29"}])

    def test_changed_weights_are_refused_before_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "model.onnx").write_bytes(b"changed weights")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch: model.onnx"):
                BatchExtractor(temporary)


if __name__ == "__main__":
    unittest.main()
