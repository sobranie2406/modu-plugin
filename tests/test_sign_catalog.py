import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sign_catalog as SIGN


class CatalogSignatureTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="modu-signature-test-")
        self.addCleanup(temporary.cleanup)
        self.temporary = Path(temporary.name)
        self.root = self.temporary / "repository"
        self.root.mkdir()
        for name in ("packages", "dist"):
            shutil.copytree(ROOT / name, self.root / name)
        for name in ("catalog.source.json", "LICENSE"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.key = self.temporary / "test-only-key.pem"
        subprocess.run([SIGN.OPENSSL, "genpkey", "-algorithm", "ED25519", "-out", str(self.key)],
                       check=True, capture_output=True)
        self.key.chmod(0o600)
        self.public = subprocess.run([SIGN.OPENSSL, "pkey", "-in", str(self.key), "-pubout", "-outform", "DER"],
                                     check=True, capture_output=True).stdout
        self.assertEqual(self.public[:12], SIGN.SPKI_PREFIX)
        self.assertEqual(len(self.public), 44)
        patch = mock.patch.object(SIGN, "PUBLIC_KEY_BASE64", base64.b64encode(self.public[12:]).decode())
        patch.start()
        self.addCleanup(patch.stop)

    def sign(self):
        return SIGN.sign_catalog(self.key, root=self.root)

    def change_catalog(self, change):
        source = self.root / "catalog.source.json"
        value = json.loads(source.read_bytes())
        change(value)
        source.write_text(json.dumps(value, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")

    def test_exact_bytes_sign_and_verify_with_openssl_without_altering_source(self):
        original = (self.root / "catalog.source.json").read_bytes()
        envelope = self.sign()
        self.assertEqual(set(envelope), {"schemaVersion", "algorithm", "keyId", "payload", "signature"})
        self.assertEqual(envelope["algorithm"], "Ed25519")
        self.assertEqual(envelope["keyId"], SIGN.KEY_ID)
        self.assertEqual(base64.b64decode(envelope["payload"], validate=True), original)
        self.assertEqual((self.root / "catalog.source.json").read_bytes(), original)
        payload, signature, public = [self.temporary / name for name in ("payload", "signature", "public.der")]
        payload.write_bytes(original)
        signature.write_bytes(base64.b64decode(envelope["signature"], validate=True))
        public.write_bytes(self.public)
        self.assertEqual(signature.stat().st_size, 64)
        subprocess.run([SIGN.OPENSSL, "pkeyutl", "-verify", "-rawin", "-pubin", "-keyform", "DER",
                        "-inkey", str(public), "-in", str(payload), "-sigfile", str(signature)],
                       check=True, capture_output=True)
        self.assertEqual(json.loads((self.root / "catalog.json").read_bytes()), envelope)

    def test_changed_source_is_not_automatically_reviewed_or_signed(self):
        self.sign()
        original = (self.root / "catalog.json").read_bytes()
        script = self.root / "packages/text-tools/main.js"
        script.write_bytes(script.read_bytes() + b"\n// unreviewed edit\n")
        with self.assertRaises(ValueError):
            self.sign()
        self.assertEqual((self.root / "catalog.json").read_bytes(), original)

    def test_extra_source_file_is_not_silently_added_to_review_inventory(self):
        (self.root / "packages/text-tools/extra.js").write_text("unknown")
        with self.assertRaises(ValueError):
            self.sign()
        self.assertFalse((self.root / "catalog.json").exists())

    def test_changed_dist_package_is_rejected(self):
        package = self.root / "dist/com.modu.text-tools-1.0.1.moduplugin"
        package.write_bytes(package.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            self.sign()

    def test_submitted_entry_is_never_automatically_listed(self):
        self.change_catalog(lambda value: value["plugins"][0].update(status="submitted"))
        with self.assertRaises(ValueError):
            self.sign()
        self.assertFalse((self.root / "catalog.json").exists())

    def test_review_record_is_required(self):
        self.change_catalog(lambda value: value["plugins"][0].pop("review"))
        with self.assertRaises(ValueError):
            self.sign()

    def test_catalog_repository_identity_must_match_modu_plugin(self):
        self.change_catalog(lambda value: value.update(repository="https://example.com/unreviewed"))
        with self.assertRaises(ValueError):
            self.sign()
        self.assertFalse((self.root / "catalog.json").exists())

    def test_duplicate_source_fields_are_rejected(self):
        (self.root / "catalog.source.json").write_text('{"schemaVersion":1,"schemaVersion":1,"plugins":[]}')
        with self.assertRaises(ValueError):
            self.sign()

    def test_signing_key_must_match_pinned_public_key(self):
        with mock.patch.object(SIGN, "PUBLIC_KEY_BASE64", base64.b64encode(bytes(32)).decode()):
            with self.assertRaises(ValueError):
                self.sign()
        self.assertFalse((self.root / "catalog.json").exists())

    def test_signer_never_generates_a_missing_key_or_accepts_a_repository_key(self):
        missing = self.temporary / "missing.pem"
        with self.assertRaises(ValueError):
            SIGN.sign_catalog(missing, root=self.root)
        self.assertFalse(missing.exists())
        embedded = self.root / "signing.pem"
        shutil.copyfile(self.key, embedded)
        embedded.chmod(0o600)
        with self.assertRaises(ValueError):
            SIGN.sign_catalog(embedded, root=self.root)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_signer_rejects_a_key_readable_by_other_users(self):
        self.key.chmod(0o644)
        with self.assertRaises(ValueError):
            self.sign()


if __name__ == "__main__":
    unittest.main()
