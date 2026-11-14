#!/usr/bin/env python3
"""Sign an explicitly reviewed catalog; never updates review hashes or status."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from pack import reviewed_packages


ROOT = Path(__file__).resolve().parents[1]
KEY_ID = "modu-plugins-2026-01"
PUBLIC_KEY_BASE64 = "t8p8Y8jV/yr7BDJCUeqpSdrRmRDec/spYO8V8FktTWM="
SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")
MAX_PAYLOAD_BYTES = 192 * 1024
MAX_ENVELOPE_BYTES = 256 * 1024
OPENSSL = "/opt/homebrew/opt/openssl@3/bin/openssl" if Path("/opt/homebrew/opt/openssl@3/bin/openssl").exists() else "openssl"


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Catalog contains duplicate fields")
        value[key] = item
    return value


def reviewed_payload(root: Path) -> bytes:
    source = root / "catalog.source.json"
    if source.is_symlink() or not source.is_file():
        raise ValueError("Readable catalog source is required")
    payload = source.read_bytes()
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("Catalog source exceeds the payload limit")
    catalog = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    if (not isinstance(catalog, dict) or type(catalog.get("schemaVersion")) is not int or
            catalog["schemaVersion"] != 1 or not isinstance(catalog.get("plugins"), list)):
        raise ValueError("Unsupported catalog source")
    for entry in catalog["plugins"]:
        if not isinstance(entry, dict) or entry.get("status") != "reviewed":
            raise ValueError("Only explicitly reviewed entries can be signed")
        review = entry.get("review")
        if (not isinstance(review, dict) or
                any(not isinstance(review.get(key), str) or not review[key].strip()
                    for key in ("kind", "reviewer", "reviewedAt")) or
                not isinstance(review.get("checks"), list) or not review["checks"] or
                any(not isinstance(check, str) or not check.strip() for check in review["checks"])):
            raise ValueError("Every entry requires an explicit review record")
    if (root / "packages").is_symlink() or (root / "dist").is_symlink():
        raise ValueError("Package directories cannot be symbolic links")
    # Rebuild in memory against recorded SHA-256s. No source, status or digest is
    # repaired automatically; unreviewed changes fail instead of getting listed.
    packages = reviewed_packages(root)
    if len(packages) != len(catalog["plugins"]):
        raise ValueError("Catalog contains entries that were not reviewed")
    for name, expected in packages:
        package = root / "dist" / name
        if (package.is_symlink() or not package.is_file() or
                not package.resolve().is_relative_to((root / "dist").resolve())):
            raise ValueError("Reviewed package is missing or outside dist")
        if (package.stat().st_size != len(expected) or
                hashlib.sha256(package.read_bytes()).digest() != hashlib.sha256(expected).digest()):
            raise ValueError("Published package differs from the reviewed source")
    if source.read_bytes() != payload:
        raise ValueError("Catalog source changed during verification")
    return payload


def sign_catalog(private_key: Path, *, root: Path = ROOT, output: Path | None = None,
                 openssl: str = OPENSSL) -> dict:
    output = output or root / "catalog.json"
    if (private_key.is_symlink() or not private_key.is_file() or
            private_key.resolve().is_relative_to(root.resolve()) or
            private_key.resolve() in (output.resolve(), (root / "catalog.source.json").resolve())):
        raise ValueError("An external signing key is required")
    if private_key.stat().st_mode & 0o077:
        raise ValueError("Signing key must be readable only by its owner")
    payload = reviewed_payload(root)
    public = subprocess.run([openssl, "pkey", "-in", str(private_key), "-pubout", "-outform", "DER"],
                            check=True, capture_output=True).stdout
    if (len(public) != 44 or public[:12] != SPKI_PREFIX or
            base64.b64encode(public[12:]).decode("ascii") != PUBLIC_KEY_BASE64):
        raise ValueError("Signing key does not match the catalog public key")
    # A file input is portable to OpenSSL's Ed25519 one-shot implementation.
    with tempfile.TemporaryDirectory(prefix="modu-catalog-sign-") as temporary:
        data = Path(temporary) / "catalog.payload"
        data.write_bytes(payload)
        signature = subprocess.run([openssl, "pkeyutl", "-sign", "-rawin", "-inkey", str(private_key),
                                    "-in", str(data)], check=True, capture_output=True).stdout
    if len(signature) != 64:
        raise ValueError("Invalid Ed25519 signature length")
    envelope = {"schemaVersion": 1, "algorithm": "Ed25519", "keyId": KEY_ID,
                "payload": base64.b64encode(payload).decode("ascii"),
                "signature": base64.b64encode(signature).decode("ascii")}
    encoded = (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise ValueError("Signed catalog exceeds the envelope limit")
    if (root / "catalog.source.json").read_bytes() != payload:
        raise ValueError("Catalog source changed during signing")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".catalog-", delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(encoded)
        temporary_path.chmod(0o644)
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return envelope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True, type=Path,
                        help="External owner-only Ed25519 PEM; never created by this command")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--openssl", default=OPENSSL)
    args = parser.parse_args()
    try:
        sign_catalog(args.private_key, root=args.root, output=args.output, openssl=args.openssl)
    except (ValueError, OSError, subprocess.SubprocessError):
        parser.exit(1, "Catalog signing failed; check the reviewed source, packages and signing key.\n")
    print("Signed reviewed catalog with " + KEY_ID)


if __name__ == "__main__":
    main()
