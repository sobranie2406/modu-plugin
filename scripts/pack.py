#!/usr/bin/env python3
"""Build deterministic .moduplugin packages using only Python's standard library."""

import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der", ".jks", ".keystore", ".mobileprovision"}
LOCAL_NAMES = {"key.properties", "local.properties", "credentials.json", "secrets.json", "config.local.json", "settings.local.json", "plugin-config.json", "plugin_config.json"}


def package_bytes(source: Path) -> tuple[str, bytes]:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    settings = manifest.get("settings", [])
    if not isinstance(settings, list):
        raise ValueError("Settings must be a list")
    capabilities = manifest.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(value, str) for value in capabilities):
        raise ValueError("Capabilities must be a string list")
    capabilities = set(capabilities)
    if capabilities.intersection({"library:private-control", "library:private-policy"}) and "library:private" not in capabilities:
        raise ValueError("Private controls require library:private")
    setting_keys = set()
    setting_types = {}
    bindings = set()
    for setting in settings:
        key = setting.get("key") if isinstance(setting, dict) else None
        if (not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key) or key in setting_keys):
            raise ValueError("Invalid or duplicate setting key")
        setting_keys.add(key)
        setting_types[key] = setting.get("type")
        storage = setting.get("storage", "sync")
        binding = setting.get("binding")
        if not isinstance(storage, str) or storage not in {"sync", "device"}:
            raise ValueError("Unsupported setting storage")
        if storage == "device" and "settings:device" not in capabilities:
            raise ValueError("Device settings require settings:device")
        if binding is not None:
            if (not isinstance(binding, str) or binding not in {"privateLibrary.privateOnly", "privateLibrary.autoImport", "privateLibrary.lockAfterHide"}
                    or binding in bindings or storage != "device" or setting.get("type") != "toggle"
                    or not {"library:private", "library:private-control"}.issubset(capabilities)):
                raise ValueError("Invalid private setting binding")
            bindings.add(binding)
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError("Package files cannot be symbolic links")
        if path.is_file():
            relative = path.relative_to(source)
            if (any(part.startswith(".") for part in relative.parts) or path.suffix.lower() in PRIVATE_SUFFIXES
                    or path.name.lower() in LOCAL_NAMES):
                raise ValueError("Private or local files cannot be packaged")
            files.append((relative.as_posix(), path.read_bytes()))
    file_map = dict(files)
    book_action_ids = set()
    article_actions = 0
    import_actions = 0
    for action in manifest["contributes"]:
        if action["kind"] == "scriptAction":
            article = action.get("surface") == "article"
            if article:
                article_actions += 1
                if (article_actions > 1 or type(action.get("schema")) is not int or action["schema"] != 1 or
                        action.get("scope") != "selection" or "article:extract" not in capabilities):
                    raise ValueError("Article extraction requires one scoped action and its capability")
            book_import = action.get("surface") == "bookImport"
            if book_import:
                import_actions += 1
                if (import_actions > 1 or type(action.get("schema")) is not int or action["schema"] != 1
                        or action.get("scope") != "selection"
                        or not {"script:run", "library:private", "library:private-policy"}.issubset(capabilities)):
                    raise ValueError("Import policy requires one scoped action and its capabilities")
            if "enabledSetting" in action:
                if not book_import or not isinstance(action["enabledSetting"], str) or setting_types.get(action["enabledSetting"]) != "toggle":
                    raise ValueError("Import policy requires a declared toggle")
            entry = action["entry"]
            limit = (512 if article else 128) * 1024
            if entry not in file_map or len(file_map[entry]) > limit:
                raise ValueError("Missing or oversized JavaScript entry")
        elif action["kind"] == "bookAction":
            fields = {"kind", "schema", "id", "name", "command"}
            command = action.get("command")
            if (type(action.get("schema")) is not int or action["schema"] != 1 or
                    not isinstance(command, str) or command not in {"privateLibrary.hide", "privateLibrary.setPrivate"}):
                raise ValueError("Unsupported declarative book action")
            if command == "privateLibrary.setPrivate":
                fields |= {"private", "lockAfter", "lockAfterSetting", "when"}
                if (type(action.get("private")) is not bool
                        or ("lockAfter" in action and type(action["lockAfter"]) is not bool)
                        or ("lockAfter" in action and "lockAfterSetting" in action)
                        or not isinstance(action.get("when", "any"), str) or action.get("when", "any") not in {"public", "private", "any"}
                        or ("lockAfterSetting" in action and (not isinstance(action["lockAfterSetting"], str) or setting_types.get(action["lockAfterSetting"]) != "toggle"))
                        or "library:private-control" not in capabilities):
                    raise ValueError("Invalid private book action options")
            if not {"kind", "schema", "id", "name", "command"}.issubset(action) or not set(action).issubset(fields):
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
            if not {"ui:book-action", "library:private"}.issubset(capabilities):
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
