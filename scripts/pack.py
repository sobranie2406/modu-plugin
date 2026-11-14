#!/usr/bin/env python3
"""Build deterministic .moduplugin packages using only Python's standard library."""

import hashlib
import io
import json
from pathlib import Path
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
    for action in manifest["contributes"]:
        if action["kind"] == "scriptAction":
            entry = action["entry"]
            if entry not in file_map or len(file_map[entry]) > 128 * 1024:
                raise ValueError("Missing or oversized JavaScript entry")
    if "LICENSE" not in file_map:
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


def main() -> None:
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    sums = []
    for source in sorted((ROOT / "packages").iterdir()):
        if not source.is_dir():
            continue
        name, data = package_bytes(source)
        (destination / name).write_bytes(data)
        sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}\n")
        print(name)
    (destination / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")


if __name__ == "__main__":
    main()
