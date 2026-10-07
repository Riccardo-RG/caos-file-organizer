"""The folder picker lists paths without changing their contents."""
import os
from pathlib import Path
import tempfile
import unittest

from organizer import Organizer
from server import list_folders


class FolderPickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'files'
        self.root.mkdir()
        self.organizer = Organizer(self.base / 'state')

    def test_lists_only_eligible_directories_in_order(self):
        for name in ('zeta', 'Alpha', '.hidden', 'Photos.photoslibrary', 'Example.app'):
            (self.root / name).mkdir()
        (self.root / 'readme.txt').write_text('unchanged')
        (self.root / 'shortcut').symlink_to(self.root / 'Alpha')
        before = sorted(p.name for p in self.root.iterdir())
        result = list_folders(self.organizer, str(self.root))
        self.assertEqual([p['name'] for p in result['folders']], ['Alpha', 'zeta'])
        self.assertEqual(result['path'], str(self.root))
        self.assertEqual(result['parent'], str(self.base))
        self.assertTrue(result['can_select'])
        self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))
        self.assertEqual((self.root / 'readme.txt').read_text(), 'unchanged')

    def test_package_and_app_data_cannot_be_selected_or_browsed(self):
        package = self.root / 'Personal.photoslibrary'
        package.mkdir()
        (package / 'database').mkdir()
        for path in (package, self.organizer.data_dir):
            with self.subTest(path=path):
                result = list_folders(self.organizer, str(path))
                self.assertFalse(result['can_select'])
                self.assertTrue(result['reason'])
                self.assertEqual(result['folders'], [])

    def test_filesystem_root_can_be_navigated_but_not_selected(self):
        result = list_folders(self.organizer, '/')
        self.assertFalse(result['can_select'])
        self.assertIsNone(result['parent'])
        self.assertNotIn('System', [p['name'] for p in result['folders']])

    def test_empty_folder_is_selectable_and_names_are_preserved(self):
        special = self.root / 'Foto & viaggi <2026>'
        special.mkdir()
        result = list_folders(self.organizer, str(self.root))
        self.assertEqual(result['folders'][0], {'name': special.name, 'path': str(special)})
        result = list_folders(self.organizer, str(special))
        self.assertTrue(result['can_select'])
        self.assertEqual(result['folders'], [])

    def test_invalid_paths_are_rejected(self):
        file = self.root / 'file.txt'
        file.write_text('keep')
        for value in ('', 'relative', '\x00', str(file)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                list_folders(self.organizer, value)
        with self.assertRaises(FileNotFoundError):
            list_folders(self.organizer, str(self.root / 'missing'))


if __name__ == '__main__':
    unittest.main()
