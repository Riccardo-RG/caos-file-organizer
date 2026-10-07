import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from organizer import Organizer, OrganizerError, _parts, _rename_exclusive


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/private/tmp" if Path("/private/tmp").exists() else None)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / "Files"
        self.root.mkdir()
        self.store = self.base / "State"
        self.organizer = Organizer(self.store)

    def tearDown(self):
        self.temporary.cleanup()

    def file(self, name, content=b"example-content"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def preview(self, **options):
        return self.organizer.preview(str(self.root), options)

    def tree(self):
        return {str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*") if path.is_file() and not path.is_symlink()}

    def test_preview_does_not_modify_files_or_create_folders(self):
        original = self.file("holiday.jpg", bytes(range(256)))
        before = self.tree()
        plan = self.preview()
        self.assertEqual(plan["files"][0]["destination"], "Immagini/holiday.jpg")
        self.assertEqual(plan["summary"], {"total": 1, "ready": 1, "unchanged": 0, "skipped": 0, "bytes": 256})
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root / "Immagini").exists())
        self.assertTrue(original.exists())

    def test_roundtrip_exact_bytes_names_metadata_and_generated_directories(self):
        paths = [self.file("foto estate.JPG", bytes(range(256))), self.file("fattura.pdf", b"%PDF sample"),
                 self.file("subdir/clip.MOV", b"\x00movie\xff"), self.file("subdir/notes.txt", b"notes")]
        os.chmod(paths[0], 0o640)
        before = self.tree()
        original_metadata = {str(p.relative_to(self.root)): (p.stat().st_mode, p.stat().st_mtime_ns) for p in paths}
        plan = self.preview(recursive=True, grouping="type_month", rename="clean")
        operation = self.organizer.apply(plan["id"])
        self.assertEqual(operation["state"], "applied")
        self.assertEqual(operation["count"], 4)
        self.assertFalse(paths[0].exists())
        self.assertEqual(self.organizer.undo(operation["id"])["state"], "undone")
        self.assertEqual(self.tree(), before)
        for relative, metadata in original_metadata.items():
            info = (self.root / relative).stat()
            self.assertEqual((info.st_mode, info.st_mtime_ns), metadata)
        self.assertFalse((self.root / "Immagini").exists())
        self.assertTrue((self.root / "subdir").is_dir())

    def test_collision_existing_and_internal_are_deterministic(self):
        self.file("Immagini/photo.jpg", b"keep-existing")
        self.file("a/photo.jpg", b"a")
        self.file("b/photo.jpg", b"b")
        first = self.preview(recursive=True)
        second = self.preview(recursive=True)
        self.assertEqual(first["files"], second["files"])
        self.assertEqual([f["destination"] for f in first["files"]], ["Immagini/photo (2).jpg", "Immagini/photo (3).jpg"])
        result = self.organizer.apply(first["id"])
        self.assertEqual((self.root / "Immagini/photo.jpg").read_bytes(), b"keep-existing")
        self.assertEqual(result["state"], "applied")

    def test_collision_case_insensitive(self):
        self.file("Immagini/PHOTO.JPG", b"existing")
        self.file("photo.jpg", b"new")
        self.assertEqual(self.preview()["files"][0]["destination"], "Immagini/photo (2).jpg")

    def test_sequence_is_deterministic_and_selection_does_not_renumber(self):
        self.file("z.pdf")
        self.file("a.JPG")
        plan = self.preview(rename="sequence", prefix="viaggio")
        self.assertEqual([x["destination"] for x in plan["files"]], ["Immagini/viaggio-001.jpg", "Documenti/viaggio-002.pdf"])
        result = self.organizer.apply(plan["id"], [plan["files"][1]["id"]])
        self.assertEqual(result["count"], 1)
        self.assertTrue((self.root / "a.JPG").exists())
        self.assertTrue((self.root / "Documenti/viaggio-002.pdf").exists())

    def test_clean_and_unchanged(self):
        self.file("  Foto di Èva! (1).JPG")
        self.file("normal.txt")
        plan = self.preview(organize=False, rename="clean")
        self.assertEqual(plan["files"][0]["destination"], "foto-di-èva-1.jpg")
        self.assertEqual(plan["files"][1]["status"], "unchanged")
        self.assertEqual(plan["summary"]["ready"], 1)

    def test_month_uses_modified_time(self):
        path = self.file("report.pdf")
        os.utime(path, (1705320000, 1705320000))  # Mid-January 2024 in every timezone.
        self.assertEqual(self.preview(grouping="month")["files"][0]["destination"], "2024-01/report.pdf")

    def test_filters_incomplete_hidden_bundles_outputs_and_symlinks(self):
        self.file("visible.jpg")
        self.file("readme.pdf")
        self.file("unfinished.crdownload")
        self.file(".secret.pdf")
        self.file(".hidden/secret.pdf")
        self.file("Thing.app/inside.txt")
        self.file("Library.photoslibrary/inside.jpg")
        self.file("Immagini/already.jpg")
        self.file("2024-01/already.pdf")
        self.file("sub/real.pdf")
        (self.root / "link.pdf").symlink_to(self.root / "readme.pdf")
        (self.root / "link-folder").symlink_to(self.root / "sub", target_is_directory=True)
        plan = self.preview(recursive=True, categories=["images", "other"])
        self.assertEqual([x["source"] for x in plan["files"]], ["readme.pdf", "sub/real.pdf", "unfinished.crdownload", "visible.jpg"])
        self.assertEqual(plan["summary"]["ready"], 1)
        self.assertEqual(plan["summary"]["skipped"], 3)

    def test_data_directory_is_ignored(self):
        organizer = Organizer(self.root / "app-data")
        self.file("hello.txt")
        plan = organizer.preview(str(self.root), {"recursive": True})
        self.assertEqual([x["source"] for x in plan["files"]], ["hello.txt"])
        with self.assertRaises(OrganizerError):
            organizer.preview(str(organizer.data_dir), {})

    def test_stale_file_rejects_entire_selection_before_any_move(self):
        self.file("a.pdf", b"a")
        path = self.file("z.jpg", b"z")
        plan = self.preview()
        path.write_bytes(b"changed")
        before = self.tree()
        with self.assertRaisesRegex(OrganizerError, "modificat"):
            self.organizer.apply(plan["id"])
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.organizer.history(), [])
        self.assertFalse((self.root / "Documenti").exists())

    def test_same_size_same_mtime_change_is_stale(self):
        path = self.file("a.pdf", b"one")
        plan = self.preview()
        info = path.stat()
        path.write_bytes(b"two")
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])
        self.assertEqual(path.read_bytes(), b"two")

    def test_destination_created_after_preview_is_never_overwritten(self):
        self.file("a.pdf", b"original")
        plan = self.preview()
        self.file("Documenti/a.pdf", b"new-user-file")
        before = self.tree()
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])
        self.assertEqual(self.tree(), before)

    def test_source_replaced_with_symlink_is_rejected(self):
        source = self.file("a.pdf", b"source")
        outside = self.base / "outside.pdf"
        outside.write_bytes(b"outside")
        plan = self.preview()
        source.unlink()
        source.symlink_to(outside)
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])
        self.assertEqual(outside.read_bytes(), b"outside")
        self.assertTrue(source.is_symlink())

    def test_destination_directory_symlink_is_rejected(self):
        self.file("a.pdf")
        outside = self.base / "outside"
        outside.mkdir()
        plan = self.preview()
        (self.root / "Documenti").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])
        self.assertEqual(list(outside.iterdir()), [])

    def test_source_ancestor_replaced_by_symlink_is_rejected(self):
        self.file("sub/a.pdf")
        plan = self.preview(recursive=True)
        (self.root / "sub").rename(self.base / "moved")
        (self.root / "sub").symlink_to(self.base / "moved", target_is_directory=True)
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])
        self.assertTrue((self.base / "moved/a.pdf").exists())

    def test_root_replaced_after_preview_is_rejected(self):
        self.file("a.pdf")
        plan = self.preview()
        self.root.rename(self.base / "old")
        self.root.mkdir()
        self.file("a.pdf", b"new")
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])
        self.assertEqual((self.root / "a.pdf").read_bytes(), b"new")

    def test_path_traversal_and_invalid_ids_are_rejected(self):
        for relative in ("../x", "a/../../x", "/tmp/a", "a//b", "a/./b", "a\\b"):
            with self.subTest(relative=relative), self.assertRaises(OrganizerError):
                _parts(relative)
        for item in ("../other", "../../etc/passwd", "", [], None):
            with self.subTest(item=item), self.assertRaises(OrganizerError):
                self.organizer.apply(item)

    def test_invalid_options(self):
        for options in ({"organize": "true"}, {"recursive": 1}, {"grouping": "bad"},
                        {"rename": "bad"}, {"categories": "images"}, {"categories": [[]]},
                        {"rename": "sequence", "prefix": "../escape"},
                        {"rename": "sequence", "prefix": ".hidden"}):
            with self.subTest(options=options), self.assertRaises(OrganizerError):
                self.preview(**options)

    def test_selection_validation_and_reused_plan(self):
        self.file("a.pdf")
        plan = self.preview()
        for selected in ([], ["missing"], "f000001", [None]):
            with self.subTest(selected=selected), self.assertRaises(OrganizerError):
                self.organizer.apply(plan["id"], selected)
        self.assertEqual(self.organizer.history(), [])
        self.organizer.apply(plan["id"])
        with self.assertRaises(OrganizerError):
            self.organizer.apply(plan["id"])

    def test_undo_modified_file_rejects_entire_operation(self):
        self.file("a.pdf", b"a")
        self.file("b.jpg", b"b")
        operation = self.organizer.apply(self.preview()["id"])
        self.file("Documenti/a.pdf", b"user-edited")
        before = self.tree()
        with self.assertRaisesRegex(OrganizerError, "annullare"):
            self.organizer.undo(operation["id"])
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.organizer.history()[0]["state"], "applied")

    def test_undo_never_overwrites_new_original_path(self):
        self.file("a.pdf", b"original")
        operation = self.organizer.apply(self.preview()["id"])
        self.file("a.pdf", b"new")
        before = self.tree()
        with self.assertRaises(OrganizerError):
            self.organizer.undo(operation["id"])
        self.assertEqual(self.tree(), before)

    def test_undo_symlink_destination_is_rejected(self):
        self.file("a.pdf", b"original")
        operation = self.organizer.apply(self.preview()["id"])
        destination = self.root / "Documenti/a.pdf"
        destination.rename(self.base / "original.pdf")
        destination.symlink_to(self.base / "original.pdf")
        with self.assertRaises(OrganizerError):
            self.organizer.undo(operation["id"])
        self.assertTrue((self.base / "original.pdf").exists())

    def test_persistence_after_new_instance_and_existing_folder_preserved(self):
        self.file("Documenti/existing.pdf", b"existing")
        self.file("a.pdf", b"new")
        before = self.tree()
        plan = self.preview()
        organizer2 = Organizer(self.store)
        operation = organizer2.apply(plan["id"])
        organizer3 = Organizer(self.store)
        self.assertEqual(organizer3.history()[0]["id"], operation["id"])
        organizer3.undo(operation["id"])
        self.assertEqual(self.tree(), before)
        self.assertTrue((self.root / "Documenti").is_dir())

    def test_rollback_when_second_move_fails(self):
        self.file("a.pdf", b"a")
        self.file("b.jpg", b"b")
        before = self.tree()
        real_rename = _rename_exclusive
        calls = 0

        def failing_rename(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Simulated filesystem failure")
            return real_rename(*args, **kwargs)

        with patch("organizer._rename_exclusive", side_effect=failing_rename):
            operation = self.organizer.apply(self.preview()["id"])
        self.assertEqual(operation["state"], "failed")
        self.assertEqual(self.tree(), before)
        self.assertFalse((self.root / "Documenti").exists())
        self.assertFalse((self.root / "Immagini").exists())

    def test_interruption_before_atomic_move_leaves_original_in_place(self):
        self.file("a.pdf", b"original")
        plan = self.preview()
        with patch("organizer._rename_exclusive", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.organizer.apply(plan["id"])
        self.assertTrue((self.root / "a.pdf").exists())
        self.assertFalse((self.root / "Documenti/a.pdf").exists())
        restarted = Organizer(self.store)
        operation = restarted.history()[0]
        self.assertEqual(operation["state"], "failed")
        self.assertEqual(self.tree(), {"a.pdf": hashlib.sha256(b"original").hexdigest()})

    def test_interruption_after_atomic_move_is_recovered(self):
        self.file("a.pdf", b"original")
        real_save = self.organizer._save_operation

        def stop_before_commit(operation):
            if any(e["state"] == "moved" for e in operation["entries"]):
                raise KeyboardInterrupt("Simulated interruption before completion journal")
            return real_save(operation)

        with patch.object(self.organizer, "_save_operation", side_effect=stop_before_commit), self.assertRaises(KeyboardInterrupt):
            self.organizer.apply(self.preview()["id"])
        restarted = Organizer(self.store)
        operation = restarted.history()[0]
        self.assertEqual(operation["state"], "applied")
        restarted.undo(operation["id"])
        self.assertEqual((self.root / "a.pdf").read_bytes(), b"original")

    def test_atomic_save_racing_move_does_not_delete_replacement(self):
        self.file("a.pdf", b"original")
        plan = self.preview()
        replaced = False

        def racing_rename(source_fd, source_name, destination_fd, destination_name):
            nonlocal replaced
            if not replaced:
                replaced = True
                replacement = self.file("replacement.tmp", b"editor-new-content")
                os.replace(replacement, self.root / "a.pdf")
            return _rename_exclusive(source_fd, source_name, destination_fd, destination_name)

        with patch("organizer._rename_exclusive", side_effect=racing_rename):
            result = self.organizer.apply(plan["id"])
        self.assertEqual(result["state"], "partial")
        self.assertEqual((self.root / "Documenti/a.pdf").read_bytes(), b"editor-new-content")
        self.assertFalse((self.root / "a.pdf").exists())
        with self.assertRaises(OrganizerError):
            self.organizer.undo(result["id"])

    def test_destination_racing_native_rename_is_never_overwritten(self):
        self.file("a.pdf", b"original")
        plan = self.preview()

        def racing_rename(source_fd, source_name, destination_fd, destination_name):
            self.file("Documenti/a.pdf", b"new-user-file")
            return _rename_exclusive(source_fd, source_name, destination_fd, destination_name)

        with patch("organizer._rename_exclusive", side_effect=racing_rename):
            result = self.organizer.apply(plan["id"])
        self.assertEqual(result["state"], "failed")
        self.assertEqual((self.root / "a.pdf").read_bytes(), b"original")
        self.assertEqual((self.root / "Documenti/a.pdf").read_bytes(), b"new-user-file")

    def test_hardlinked_files_roundtrip(self):
        first = self.file("a.pdf", b"shared-bytes")
        os.link(first, self.root / "b.pdf")
        before = self.tree()
        result = self.organizer.apply(self.preview()["id"])
        self.assertEqual(result["state"], "applied")
        self.assertEqual(self.organizer.undo(result["id"])["state"], "undone")
        self.assertEqual(self.tree(), before)
        self.assertEqual(first.stat().st_ino, (self.root / "b.pdf").stat().st_ino)

    def test_successive_renames_can_be_undone_in_reverse_order(self):
        self.file("a.pdf", b"original")
        first = self.organizer.apply(self.preview(organize=False, rename="sequence", prefix="one")["id"])
        second = self.organizer.apply(self.preview(organize=False, rename="sequence", prefix="two")["id"])
        self.organizer.undo(second["id"])
        self.organizer.undo(first["id"])
        self.assertEqual((self.root / "a.pdf").read_bytes(), b"original")

    def test_malformed_journals_do_not_prevent_startup_or_authorize_changes(self):
        self.file("a.pdf")
        before = self.tree()
        bad_id = "b" * 32
        path = self.store / "operations" / (bad_id + ".json")
        for data in ({"schema": 1, "id": bad_id}, {"schema": 1, "id": bad_id, "state": "applying"}, None, []):
            path.write_text(json.dumps(data))
            restarted = Organizer(self.store)
            self.assertEqual(restarted.history(), [])
            with self.assertRaises(OrganizerError):
                restarted.undo(bad_id)
        self.assertEqual(self.tree(), before)

    def test_undo_partial_is_persisted_and_can_be_retried(self):
        self.file("a.pdf", b"a")
        self.file("b.jpg", b"b")
        before = self.tree()
        operation = self.organizer.apply(self.preview()["id"])
        calls = 0

        def fail_second_rename(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Simulated permission change during undo")
            return _rename_exclusive(*args)

        with patch("organizer._rename_exclusive", side_effect=fail_second_rename):
            result = self.organizer.undo(operation["id"])
        self.assertEqual(result["state"], "undo_partial")
        self.assertEqual(result["moved"], 1)
        restarted = Organizer(self.store)
        self.assertEqual(restarted.undo(operation["id"])["state"], "undone")
        self.assertEqual(self.tree(), before)

    def test_undo_crash_after_atomic_move_recovers_complete_original_tree(self):
        self.file("a.pdf", b"a")
        operation = self.organizer.apply(self.preview()["id"])
        real_save = self.organizer._save_operation

        def crash_after_restore(value):
            if value["entries"][0]["state"] == "undone":
                raise KeyboardInterrupt("Simulated interruption after restore")
            return real_save(value)

        with patch.object(self.organizer, "_save_operation", side_effect=crash_after_restore), self.assertRaises(KeyboardInterrupt):
            self.organizer.undo(operation["id"])
        restarted = Organizer(self.store)
        self.assertEqual(restarted.history()[0]["state"], "undone")
        self.assertEqual((self.root / "a.pdf").read_bytes(), b"a")
        self.assertFalse((self.root / "Documenti").exists())

    def test_details_survives_restart(self):
        self.file("a.pdf", b"a")
        operation = self.organizer.apply(self.preview()["id"])
        restarted = Organizer(self.store)
        details = restarted.details(operation["id"])
        self.assertEqual(details["entries"][0]["source"], "a.pdf")
        self.assertEqual(details["entries"][0]["destination"], "Documenti/a.pdf")
        self.assertNotIn("digest", details["entries"][0])

    def test_new_file_in_generated_folder_survives_undo(self):
        self.file("a.pdf")
        operation = self.organizer.apply(self.preview()["id"])
        self.file("Documenti/user-added.txt", b"new")
        self.organizer.undo(operation["id"])
        self.assertEqual((self.root / "Documenti/user-added.txt").read_bytes(), b"new")

    def test_generated_folder_name_occupied_by_file_is_skipped(self):
        self.file("Documenti", b"keep")
        self.file("a.pdf")
        plan = self.preview()
        item = next(x for x in plan["files"] if x["source"] == "a.pdf")
        self.assertEqual(item["status"], "skipped")
        self.assertEqual((self.root / "Documenti").read_bytes(), b"keep")

    def test_root_symlink_and_system_root_rejected(self):
        alias = self.base / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        for root in (str(alias), "/"):
            with self.subTest(root=root), self.assertRaises(OrganizerError):
                self.organizer.preview(root, {})


if __name__ == "__main__":
    unittest.main()
