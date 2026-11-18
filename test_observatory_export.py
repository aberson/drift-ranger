"""Private export tests use disposable synthetic records only."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import drift_ranger as dr


class ExportTests(unittest.TestCase):
    def test_roundtrip_and_immutable_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory).resolve()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(dr.main(["init", "Example.Project", "--store", str(store),
                    "--intent", "Make routine reliable", "--entry-point", "Open the app",
                    "--next-gap", "First real workflow"]), 0)
                for unit in ("one", "two"):
                    self.assertEqual(dr.main(["checkpoint", "Example.Project", "--store", str(store),
                        "--unit", unit, "--can", "Preview", "--cannot", "Deliver",
                        "--next-gap", "Connect", "--progress", "unchanged"]), 0)
                before = {p: p.read_bytes() for p in store.rglob("*.json")}
                self.assertEqual(dr.main(["export-observatory", "--store", str(store)]), 0)
            artifact = json.loads((store / "observatory/intents.json").read_text())
            row = artifact["items"][0]
            self.assertEqual(row["summary"], "Make routine reliable")
            self.assertEqual(row["detail"]["Advisory"], "REASSESS")
            self.assertEqual(row["detail"]["Current capability"], "Preview")
            self.assertRegex(row["id"], r"^intent-[a-f0-9]{24}$")
            for path, original in before.items():
                self.assertEqual(path.read_bytes(), original)
            # Bad input cannot replace the last valid snapshot.
            saved = (store / "observatory/intents.json").read_bytes()
            (store / "Example.Project/intent.json").write_text("broken")
            with self.assertRaises(dr.DriftRangerError):
                dr.command_export_observatory(store)
            self.assertEqual((store / "observatory/intents.json").read_bytes(), saved)

    def test_empty_and_missing_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory).resolve()
            with contextlib.redirect_stdout(io.StringIO()):
                dr.command_export_observatory(store)
            self.assertEqual(json.loads((store / "observatory/intents.json").read_text())["items"], [])
            with self.assertRaises(dr.DriftRangerError):
                dr.command_export_observatory(store / "missing")

    def test_oversized_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory).resolve()
            project = store / "example"
            project.mkdir()
            (project / "intent.json").write_bytes(b" " * 262145)
            with self.assertRaises(dr.DriftRangerError):
                dr.command_export_observatory(store)
            self.assertFalse((store / "observatory/intents.json").exists())


if __name__ == "__main__":
    unittest.main()
