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
        self.assertEqual({path.name for path in sources}, {
            "private-books", "text-tools", "prompt-pack", "dictionary-transform", "web-clipper"
        })
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

    def test_catalog_covers_five_reviewed_packages_and_preserves_existing_bytes(self):
        packages = dict(PACK.reviewed_packages(ROOT))
        self.assertEqual(len(packages), 5)
        self.assertEqual(set(packages), {
            "com.modu.private-books-1.2.0.moduplugin", "com.modu.text-tools-1.0.1.moduplugin",
            "com.modu.dictionary-transform-1.0.1.moduplugin", "com.modu.web-clipper-1.1.1.moduplugin",
            "com.example.prompt-pack-1.1.1.moduplugin",
        })
        for name, data in packages.items():
            self.assertEqual(data, (ROOT / "dist" / name).read_bytes())
        self.assertEqual(hashlib.sha256((ROOT / "dist" / "com.modu.private-books-1.0.0.moduplugin").read_bytes()).hexdigest(),
                         "ce459c352a302b3dc1b7e5b3fade872c5dec3ef53a533747674bb4b038b0eba4")
        self.assertEqual(hashlib.sha256((ROOT / "dist" / "com.modu.web-clipper-1.0.0.moduplugin").read_bytes()).hexdigest(),
                         "4cf337b9f425b58bfc375fa43b64f86c5b2298d316a00e371e0866bb69e300f9")
        with zipfile.ZipFile(ROOT / "dist/com.example.prompt-pack-1.1.0.moduplugin") as archive:
            original = {
                "manifest.json": "405941bfa8f15fef6a5fa7b6d6628da357733f84faa919c6676699bdcc730fbe",
                "README.md": "dc7a53ee926b20a087fb1240db0051af274a7aa46650223e1ef2db54335fb729",
                "LICENSE": "1b8f0b15266cbeba35ed28401ffbf7e9e4438e302e1431462342b8d0ed3d6a63",
            }
            self.assertEqual({name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}, original)

    def test_private_books_declare_device_preferences_import_and_generic_menu_controls(self):
        name, data = PACK.package_bytes(ROOT / "packages" / "private-books")
        self.assertEqual(name, "com.modu.private-books-1.2.0.moduplugin")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(set(manifest["capabilities"]), {"script:run", "library:private", "ui:book-action", "library:private-control", "library:private-policy", "settings:device"})
            scripts = [action for action in manifest["contributes"] if action["kind"] == "scriptAction"]
            self.assertEqual([(action["id"], action["entry"]) for action in scripts], [("open", "main.js"), ("lock", "main.js"), ("add", "main.js"), ("remove", "main.js"), ("import-policy", "import.js")])
            self.assertEqual([(setting["key"], setting["storage"], setting["defaultValue"]) for setting in manifest["settings"]],
                             [("private_only", "device", False), ("auto_import", "device", False), ("lock_after_hide", "device", True)])
            self.assertEqual([(action["id"], action["command"], action["private"], action["when"]) for action in manifest["contributes"] if action["kind"] == "bookAction"],
                             [("hide", "privateLibrary.setPrivate", True, "public"), ("restore", "privateLibrary.setPrivate", False, "private")])

    def test_web_clipper_keeps_its_small_launcher_and_bundles_scoped_offline_extraction(self):
        name, data = PACK.package_bytes(ROOT / "packages" / "web-clipper")
        self.assertEqual(name, "com.modu.web-clipper-1.1.1.moduplugin")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(set(archive.namelist()), {"LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "main.js", "extract.js", "manifest.json"})
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(set(manifest["capabilities"]), {"script:run", "article:capture", "article:extract"})
            self.assertEqual([(action["id"], action["entry"], action["surface"]) for action in manifest["contributes"]],
                             [("capture", "main.js", "library"), ("extract", "extract.js", "article")])
            self.assertEqual(manifest["contributes"][1]["scope"], "selection")
            self.assertEqual([(setting["key"], setting["type"], setting["defaultValue"]) for setting in manifest["settings"]],
                             [("include_metadata", "toggle", True), ("include_images", "toggle", True)])
            self.assertEqual(hashlib.sha256(archive.read("main.js")).hexdigest(), "8a0f90e13534bb2c27b8bcae4a68b9598661a657ee759fef2bf717342fe33d34")
            self.assertGreater(len(archive.read("extract.js")), 128 * 1024)
            self.assertLessEqual(len(archive.read("extract.js")), 512 * 1024)
            notices = archive.read("THIRD_PARTY_NOTICES.md").decode()
            for text in ("Apache License", "ISC License", "MIT License", "Readability", "LinkeDOM", "Turndown", "Luc Thevenard"):
                self.assertIn(text, notices)

    def test_article_entry_needs_its_capability_scope_and_separate_size_limit(self):
        for change in ("capability", "scope", "duplicate", "schema", "oversized_article", "oversized_launcher"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "web-clipper"
                shutil.copytree(ROOT / "packages" / "web-clipper", source)
                path = source / "manifest.json"
                manifest = json.loads(path.read_bytes())
                if change == "capability": manifest["capabilities"].remove("article:extract")
                if change == "scope": manifest["contributes"][1]["scope"] = "context"
                if change == "duplicate": manifest["contributes"].append(manifest["contributes"][1])
                if change == "schema": manifest["contributes"][1]["schema"] = True
                if change == "oversized_article": (source / "extract.js").write_bytes(b" " * (512 * 1024 + 1))
                if change == "oversized_launcher": (source / "main.js").write_bytes(b" " * (128 * 1024 + 1))
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError): PACK.package_bytes(source)

    def test_setting_keys_match_host_format_and_are_unique(self):
        for key in ("includeMetadata", "_bad", "7bad", "bad-key", "a" * 41, 1, None, "include_images"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "web-clipper"
                shutil.copytree(ROOT / "packages" / "web-clipper", source)
                path = source / "manifest.json"
                manifest = json.loads(path.read_bytes())
                manifest["settings"][0]["key"] = key
                path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "setting key"):
                    PACK.package_bytes(source)

    def test_book_action_rejects_executable_fields_unknown_commands_and_missing_grants(self):
        changes = [
            ("schema", value) for value in (0, 2, True, 1.0, "1")
        ] + [
            ("command", "privateLibrary.delete"), ("command", None),
            ("entry", "main.js"), ("arguments", {"id": 1}),
            ("id", "../hide"), ("id", ""),
            ("name", ""), ("name", []), ("name", {}), ("name", {"en": "x" * 41}),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "private-books"
                shutil.copytree(ROOT / "packages" / "private-books", source)
                path = source / "manifest.json"
                manifest = json.loads(path.read_bytes())
                manifest["contributes"][-1][field] = value
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    PACK.package_bytes(source)
        for capabilities in (["script:run", "library:private"], ["script:run", "ui:book-action"], "library:private", [None]):
            with self.subTest(capabilities=capabilities), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "private-books"
                shutil.copytree(ROOT / "packages" / "private-books", source)
                path = source / "manifest.json"
                manifest = json.loads(path.read_bytes())
                manifest["capabilities"] = capabilities
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    PACK.package_bytes(source)

    def test_duplicate_book_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private-books"
            shutil.copytree(ROOT / "packages" / "private-books", source)
            path = source / "manifest.json"
            manifest = json.loads(path.read_bytes())
            manifest["contributes"].append(manifest["contributes"][-1])
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                PACK.package_bytes(source)

    def test_source_submission_is_not_listing_and_reviewed_source_cannot_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "packages", root / "packages")
            catalog = json.loads((ROOT / "catalog.source.json").read_text())
            catalog["plugins"][0]["status"] = "submitted"
            (root / "catalog.source.json").write_text(json.dumps(catalog))
            self.assertEqual(len(PACK.reviewed_packages(root)), 4)
            (root / "packages" / "text-tools" / "main.js").write_text("return {text: 'changed'};")
            with self.assertRaises(ValueError):
                PACK.reviewed_packages(root)


if __name__ == "__main__":
    unittest.main()
