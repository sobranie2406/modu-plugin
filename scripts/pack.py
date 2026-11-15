#!/usr/bin/env python3
"""Build deterministic .moduplugin packages using only Python's standard library."""

import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def package_bytes(source: Path) -> tuple[str, bytes]:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Package files cannot be symbolic links")
        if path.is_file():
            files.append((path.relative_to(source).as_posix(), path.read_bytes()))
    file_map = dict(files)
    book_action_ids = set()
    for action in manifest["contributes"]:
        if action["kind"] == "scriptAction":
            entry = action["entry"]
            if entry not in file_map or len(file_map[entry]) > 128 * 1024:
                raise ValueError("Missing or oversized JavaScript entry")
        elif action["kind"] == "bookAction":
            if (set(action) != {"kind", "schema", "id", "name", "command"} or
                    type(action.get("schema")) is not int or action["schema"] != 1 or
                    action.get("command") != "privateLibrary.hide"):
                raise ValueError("Unsupported declarative book action")
            identity = action.get("id")
            if (not isinstance(identity, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,62}", identity)
                    or identity in book_action_ids):
                raise ValueError("Invalid or duplicate book action id")
            book_action_ids.add(identity)
            name = action["name"]
            labels = [name] if isinstance(name, str) else list(name.values()) if isinstance(name, dict) else []
            if (not labels or any(not isinstance(label, str) or not label.strip() or len(label) > 40 for label in labels)):
                raise ValueError("Invalid book action label")
            capabilities = manifest.get("capabilities")
            if (not isinstance(capabilities, list) or any(not isinstance(capability, str) for capability in capabilities)
                    or not {"ui:book-action", "library:private"}.issubset(capabilities)):
                raise ValueError("Book action requires explicit menu and private-library capabilities")
    if "LICENSE" not in file_map:
        # Preserve a package's original license bytes when it supplies one.
        files.append(("LICENSE", (ROOT / "LICENSE").read_bytes()))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    return f"{manifest['id']}-{manifest['version']}.moduplugin", output.getvalue()


def reviewed_packages(root: Path) -> list[tuple[str, bytes]]:
    catalog = json.loads((root / "catalog.source.json").read_text(encoding="utf-8"))
    if catalog["schemaVersion"] != 1:
        raise ValueError("Unsupported catalog schema")
    packages = []
    seen = set()
    for entry in catalog["plugins"]:
        if entry["status"] != "reviewed":
            continue
        identity = (entry["id"], entry["version"])
        if identity in seen:
            raise ValueError("Duplicate catalog version")
        seen.add(identity)
        source = (root / entry["sourcePath"]).resolve()
        if not source.is_relative_to((root / "packages").resolve()):
            raise ValueError("Catalog source must be inside packages")
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if any(manifest[key] != entry[key] for key in ("id", "version", "minAppVersion")):
            raise ValueError("Catalog identity differs from manifest")
        if manifest.get("hostApi", 1) != entry["hostApi"] or set(manifest["capabilities"]) != set(entry["capabilities"]):
            raise ValueError("Catalog API or capabilities differ from manifest")
        name, data = package_bytes(source)
        if (entry["package"]["path"] != f"dist/{name}" or
                entry["package"]["sha256"] != hashlib.sha256(data).hexdigest()):
            raise ValueError("Package differs from reviewed catalog")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
        if files != entry["files"]:
            raise ValueError("File inventory differs from reviewed catalog")
        packages.append((name, data))
    return packages


def main() -> None:
    packages = reviewed_packages(ROOT)
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    sums = []
    for name, data in packages:
        (destination / name).write_bytes(data)
        sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
        print(name)
    (destination / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")


if __name__ == "__main__":
    main()
