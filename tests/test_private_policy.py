import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pack_private_policy', ROOT / 'scripts/pack.py')
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)


class PrivatePolicyPackageTest(unittest.TestCase):
    def reject(self, mutate):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'private-books'
            shutil.copytree(ROOT / 'packages/private-books', source)
            path = source / 'manifest.json'
            manifest = json.loads(path.read_bytes())
            mutate(manifest)
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                PACK.package_bytes(source)

    def test_private_capabilities_cannot_be_omitted(self):
        for capability in ('settings:device', 'library:private', 'library:private-control', 'library:private-policy', 'script:run', 'ui:book-action'):
            with self.subTest(capability=capability):
                self.reject(lambda manifest: manifest['capabilities'].remove(capability))

    def test_device_binding_is_known_unique_boolean_and_local(self):
        for field, value in [('storage', 'sync'), ('storage', 'cloud'), ('binding', 'privateLibrary.unknown'), ('type', 'text')]:
            with self.subTest(field=field, value=value):
                self.reject(lambda manifest: manifest['settings'][0].update({field: value}))
        self.reject(lambda manifest: manifest['settings'][1].update(binding='privateLibrary.privateOnly'))

    def test_import_policy_is_single_scoped_and_references_a_toggle(self):
        for field, value in [('scope', 'context'), ('schema', True), ('enabledSetting', 'missing')]:
            with self.subTest(field=field, value=value):
                self.reject(lambda manifest: next(action for action in manifest['contributes'] if action.get('surface') == 'bookImport').update({field: value}))
        self.reject(lambda manifest: manifest['contributes'].append(next(action for action in manifest['contributes'] if action.get('surface') == 'bookImport')))
        self.reject(lambda manifest: manifest['contributes'][0].update(enabledSetting='auto_import'))
        self.reject(lambda manifest: manifest['settings'][1].update(type='text'))

    def test_declarative_action_rejects_wrong_options_and_preserves_legacy_command(self):
        for field, value in [('private', 'true'), ('private', 1), ('when', 'unknown'), ('lockAfterSetting', 'missing'), ('lockAfter', 'false')]:
            with self.subTest(field=field, value=value):
                self.reject(lambda manifest: manifest['contributes'][-1].update({field: value}))
        self.reject(lambda manifest: manifest['contributes'][-2].update(lockAfter=True))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'manifest.json').write_text(json.dumps({'id': 'com.example.legacy', 'version': '1.0.0', 'capabilities': ['ui:book-action', 'library:private'], 'contributes': [
                {'kind': 'bookAction', 'schema': 1, 'id': 'hide', 'name': 'Hide', 'command': 'privateLibrary.hide'}]}))
            self.assertEqual(PACK.package_bytes(source)[0], 'com.example.legacy-1.0.0.moduplugin')
            manifest = json.loads((source / 'manifest.json').read_bytes())
            manifest['contributes'][0]['private'] = True
            (source / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): PACK.package_bytes(source)


if __name__ == '__main__':
    unittest.main()
