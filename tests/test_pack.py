import importlib.util
import io
import hashlib
import json
import shutil
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
        sources = sorted((ROOT / "packages").iterdir())
        self.assertEqual({path.name for path in sources}, {"private-books", "text-tools", "prompt-pack"})
        for source in sources:
            first = PACK.package_bytes(source)
            self.assertEqual(first, PACK.package_bytes(source))
            with zipfile.ZipFile(io.BytesIO(first[1])) as archive:
                self.assertIn("LICENSE", archive.namelist())
                manifest = json.loads(archive.read("manifest.json"))
                for action in manifest["contributes"]:
                    if action["kind"] == "scriptAction":
                        self.assertIn(action["entry"], archive.namelist())
                self.assertEqual(archive.namelist(), sorted(archive.namelist()))
                self.assertTrue(all(info.date_time == (2020, 1, 1, 0, 0, 0) for info in archive.infolist()))

    def test_missing_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "manifest.json").write_text('{"contributes":[{"kind":"scriptAction","entry":"missing.js"}]}')
            with self.assertRaises(ValueError):
                PACK.package_bytes(source)

    def test_catalog_covers_three_reviewed_packages_and_preserves_existing_bytes(self):
        packages = dict(PACK.reviewed_packages(ROOT))
        self.assertEqual(len(packages), 3)
        expected = {
            "com.modu.private-books-1.0.0.moduplugin": "ce459c352a302b3dc1b7e5b3fade872c5dec3ef53a533747674bb4b038b0eba4",
            "com.modu.text-tools-1.0.0.moduplugin": "19ec63c7ab15d2b9895ee48c5c46e1493247197e8d3cea29746d34beece0717e",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256(packages[name]).hexdigest(), digest)
        with zipfile.ZipFile(io.BytesIO(packages["com.example.prompt-pack-1.1.0.moduplugin"])) as archive:
            original = {
                "manifest.json": "405941bfa8f15fef6a5fa7b6d6628da357733f84faa919c6676699bdcc730fbe",
                "README.md": "dc7a53ee926b20a087fb1240db0051af274a7aa46650223e1ef2db54335fb729",
                "LICENSE": "1b8f0b15266cbeba35ed28401ffbf7e9e4438e302e1431462342b8d0ed3d6a63",
            }
            self.assertEqual({name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}, original)

    def test_source_submission_is_not_listing_and_reviewed_source_cannot_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "packages", root / "packages")
            catalog = json.loads((ROOT / "catalog.source.json").read_text())
            catalog["plugins"][0]["status"] = "submitted"
            (root / "catalog.source.json").write_text(json.dumps(catalog))
            self.assertEqual(len(PACK.reviewed_packages(root)), 2)
            (root / "packages" / "text-tools" / "main.js").write_text("return {text: 'changed'};")
            with self.assertRaises(ValueError):
                PACK.reviewed_packages(root)


if __name__ == "__main__":
    unittest.main()
