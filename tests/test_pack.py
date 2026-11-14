import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pack", ROOT / "scripts" / "pack.py")
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)


class PackageTest(unittest.TestCase):
    def test_repeatable_packages_include_license_and_entries(self):
        for source in sorted((ROOT / "packages").iterdir()):
            first = PACK.package_bytes(source)
            self.assertEqual(first, PACK.package_bytes(source))
            with zipfile.ZipFile(io.BytesIO(first[1])) as archive:
                self.assertIn("LICENSE", archive.namelist())
                self.assertIn("main.js", archive.namelist())
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                self.assertTrue(all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_missing_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "manifest.json").write_text('{"contributes":[{"kind":"scriptAction","entry":"missing.js"}]}')
            with self.assertRaises(ValueError):
                PACK.package_bytes(source)


if __name__ == "__main__":
    unittest.main()
