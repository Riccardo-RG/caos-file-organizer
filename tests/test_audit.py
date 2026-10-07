"""Regressions found by the independent safety audit.

Fixtures stay in temporary directories inside the project; personal files are
never selected or changed by these tests.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from organizer import Organizer, OrganizerError


class OrganizerAuditTests(unittest.TestCase):
    def setUp(self):
        workspace = Path(__file__).resolve().parents[1]
        self.temporary = tempfile.TemporaryDirectory(dir=workspace)
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "Files"
        self.root.mkdir()
        self.organizer = Organizer(self.base / "State")

    def test_legal_backslash_name_does_not_block_other_files(self):
        (self.root / "normal.pdf").write_bytes(b"normal document")
        unusual = self.root / "notes\\2026.pdf"
        unusual.write_bytes(b"unusual but legal filename")
        plan = self.organizer.preview(str(self.root), {})
        ordinary = next(item for item in plan["files"] if item["source"] == "normal.pdf")
        operation = self.organizer.apply(plan["id"], [ordinary["id"]])
        self.assertEqual(operation["state"], "applied")
        self.assertEqual((self.root / "Documenti/normal.pdf").read_bytes(), b"normal document")
        self.assertEqual(unusual.read_bytes(), b"unusual but legal filename")
        self.organizer.undo(operation["id"])
        self.assertEqual((self.root / "normal.pdf").read_bytes(), b"normal document")

    def test_bundle_roots_and_their_descendants_cannot_be_organized(self):
        for suffix in (".photoslibrary", ".app", ".musiclibrary"):
            with self.subTest(suffix=suffix):
                bundle = self.base / ("Protected" + suffix)
                internal = bundle / "Contents"
                internal.mkdir(parents=True)
                content = internal / "database.db"
                content.write_bytes(b"internal application data")
                for selected_root in (bundle, internal):
                    with self.subTest(selected_root=selected_root):
                        with self.assertRaises(OrganizerError):
                            self.organizer.preview(str(selected_root), {"recursive": True})
                self.assertEqual(content.read_bytes(), b"internal application data")

    def test_crash_recovery_retries_when_original_root_returns(self):
        original = self.root / "normal.pdf"
        original.write_bytes(b"original document")
        plan = self.organizer.preview(str(self.root), {})
        save = self.organizer._save_operation

        def interrupt_after_rename(operation):
            if operation["entries"][0]["state"] == "moved":
                raise KeyboardInterrupt("Crash before final move journal")
            return save(operation)

        with patch.object(self.organizer, "_save_operation", side_effect=interrupt_after_rename):
            with self.assertRaises(KeyboardInterrupt):
                self.organizer.apply(plan["id"])
        unavailable = self.base / "Disconnected"
        self.root.rename(unavailable)
        offline = Organizer(self.organizer.data_dir)
        operation_id = offline.history()[0]["id"]
        unavailable.rename(self.root)
        reconnected = Organizer(self.organizer.data_dir)
        operation = reconnected.undo(operation_id)
        self.assertEqual(operation["state"], "undone")
        self.assertEqual(original.read_bytes(), b"original document")

    def test_interrupted_undo_recovers_after_original_root_returns(self):
        original = self.root / "normal.pdf"
        original.write_bytes(b"original document")
        plan = self.organizer.preview(str(self.root), {})
        operation = self.organizer.apply(plan["id"])
        save = self.organizer._save_operation

        def interrupt_after_restore(value):
            if value["entries"][0]["state"] == "undone":
                raise KeyboardInterrupt("Crash before final undo journal")
            return save(value)

        with patch.object(self.organizer, "_save_operation", side_effect=interrupt_after_restore):
            with self.assertRaises(KeyboardInterrupt):
                self.organizer.undo(operation["id"])
        unavailable = self.base / "Disconnected"
        self.root.rename(unavailable)
        offline = Organizer(self.organizer.data_dir)
        offline.history()
        unavailable.rename(self.root)
        reconnected = Organizer(self.organizer.data_dir)
        self.assertEqual(reconnected.details(operation["id"])["state"], "undone")
        self.assertEqual(original.read_bytes(), b"original document")
        self.assertFalse((self.root / "Documenti").exists())


if __name__ == "__main__":
    unittest.main()
