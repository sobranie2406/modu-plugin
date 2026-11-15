import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pack_policy", ROOT / "scripts/pack.py")
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)


class PackagePolicyTest(unittest.TestCase):
    def test_all_seven_published_package_versions_remain_byte_exact(self):
        historical = {
            "com.modu.private-books-1.0.0.moduplugin": "ce459c352a302b3dc1b7e5b3fade872c5dec3ef53a533747674bb4b038b0eba4",
            "com.modu.private-books-1.1.0.moduplugin": "667b1b04aa0629c3344163656dd9398ba59c55fd0bb70e26d235a4eefcaacb68",
            "com.modu.text-tools-1.0.0.moduplugin": "19ec63c7ab15d2b9895ee48c5c46e1493247197e8d3cea29746d34beece0717e",
            "com.modu.dictionary-transform-1.0.0.moduplugin": "5e57cf9c2e6e988447bc0a7b7d2d446b41496a11eec98575dc7d3327747d8a7e",
            "com.modu.web-clipper-1.0.0.moduplugin": "4cf337b9f425b58bfc375fa43b64f86c5b2298d316a00e371e0866bb69e300f9",
            "com.modu.web-clipper-1.1.0.moduplugin": "a06f1a3424efddb62bdc12a5a7b2b85b0f216ddf6156609a96673b394e01abad",
            "com.example.prompt-pack-1.1.0.moduplugin": "d49736985b07b8e60c60982935a00dfbf7fe6708f35e2549dc593bba1e2ab45b",
        }
        for name, digest in historical.items():
            self.assertEqual(hashlib.sha256((ROOT / "dist" / name).read_bytes()).hexdigest(), digest, name)

    def test_certificates_credentials_and_local_configuration_are_rejected(self):
        for name in ("client.pem", "client.KEY", "certificate.crt", "certificate.cer", "certificate.der", "signing.p12", "keystore.jks", ".env", ".release-secrets/config.json", "key.properties", "settings.local.json", "plugin_config.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary)
                (source / "manifest.json").write_text(json.dumps({"id": "com.example.test", "version": "1.0.0", "contributes": []}))
                forbidden = source / name
                forbidden.parent.mkdir(parents=True, exist_ok=True)
                forbidden.write_text("test-only placeholder")
                with self.assertRaisesRegex(ValueError, "Private or local files"):
                    PACK.package_bytes(source)

    def test_all_five_package_sources_follow_packaging_safety_rules(self):
        sources = list((ROOT / "packages").iterdir())
        self.assertEqual(len(sources), 5)
        for source in sources:
            with self.subTest(source=source.name):
                PACK.package_bytes(source)


if __name__ == "__main__":
    unittest.main()
