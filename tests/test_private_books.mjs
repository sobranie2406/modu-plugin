import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const load = async name => new AsyncFunction('input', 'modu', await readFile(
  new URL(`../packages/private-books/${name}.js`, import.meta.url), 'utf8'));
const manifest = JSON.parse(await readFile(new URL('../packages/private-books/manifest.json', import.meta.url)));

function library(selected = [{id: 3, title: 'Selected', private: false}]) {
  const calls = [];
  return {calls, modu: {privateLibrary: {
    selectBooks: async options => {calls.push(['select', options]); return selected;},
    setPrivate: async options => {calls.push(['set', options]); return {updated: options.bookIds.length};},
  }}};
}

test('private management only changes books authorized by the current picker', async () => {
  const run = await load('main');
  for (const [actionId, makePrivate] of [['add', true], ['remove', false]]) {
    const {calls, modu} = library([{id: 3}, {id: 8}, {id: 3}]);
    const result = await run({actionId, settings: {}}, modu);
    assert.match(result.text, makePrivate ? /加入/ : /移出/);
    assert.deepEqual(calls, [
      ['select', {private: !makePrivate}],
      ['set', {bookIds: [3, 8], private: makePrivate, lockAfter: makePrivate}],
    ]);
  }
});

test('lock-after-hide setting changes the management action without changing remove policy', async () => {
  const run = await load('main');
  for (const actionId of ['add', 'remove']) {
    const {calls, modu} = library();
    await run({actionId, settings: {lock_after_hide: false}}, modu);
    assert.equal(calls[1][1].lockAfter, false);
  }
});

test('cancelled picker does not modify books', async () => {
  const {calls, modu} = library([]);
  assert.equal((await (await load('main'))({actionId: 'add'}, modu)).text, '');
  assert.deepEqual(calls, [['select', {private: false}]]);
});

test('invalid picker records and failures never reach setPrivate', async () => {
  const run = await load('main');
  for (const selected of [null, {}, [{id: 0}], [{id: -1}], [{id: '3'}], [{id: 1.1}], [null], Array.from({length: 101}, (_, id) => ({id: id + 1}))]) {
    const {calls, modu} = library(selected);
    await assert.rejects(run({actionId: 'add'}, modu));
    assert.equal(calls.length, 1);
  }
  const {calls, modu} = library();
  modu.privateLibrary.selectBooks = async () => {throw new Error('cancelled');};
  await assert.rejects(run({actionId: 'add'}, modu), /cancelled/);
  assert.equal(calls.length, 0);
});

test('unknown management actions have no host calls', async () => {
  const run = await load('main');
  const modu = new Proxy({}, {get() {throw new Error('Unexpected host access');}});
  for (const actionId of ['hide', 'restore', 'import-policy', 'unknown', undefined]) {
    await assert.rejects(run({actionId}, modu), /Unknown private library action/);
  }
});

test('import policy is pure, defaults off and only a boolean true enables private import', async () => {
  const run = await load('import');
  const modu = new Proxy({}, {get() {throw new Error('Unexpected host access');}});
  for (const settings of [undefined, {}, {auto_import: false}, {auto_import: 'true'}, {auto_import: 1}, {auto_import: true}]) {
    assert.deepEqual(await run({actionId: 'import-policy', book: {id: 0, title: 'New', format: 'epub'}, settings}, modu),
      {private: settings?.auto_import === true});
  }
  await assert.rejects(run({actionId: 'add', settings: {auto_import: true}}, modu), /Unknown private import action/);
});

test('manifest binds device preferences and declares pure import and menu policies', () => {
  assert.deepEqual(manifest.settings.map(({key, storage, type, defaultValue, binding}) => ({key, storage, type, defaultValue, binding})), [
    {key: 'private_only', storage: 'device', type: 'toggle', defaultValue: false, binding: 'privateLibrary.privateOnly'},
    {key: 'auto_import', storage: 'device', type: 'toggle', defaultValue: false, binding: 'privateLibrary.autoImport'},
    {key: 'lock_after_hide', storage: 'device', type: 'toggle', defaultValue: true, binding: 'privateLibrary.lockAfterHide'},
  ]);
  assert.deepEqual(manifest.contributes.filter(action => action.surface === 'bookImport'), [{
    kind: 'scriptAction', schema: 1, id: 'import-policy', name: {'zh-CN': '私密导入规则', en: 'Private import policy'},
    entry: 'import.js', surface: 'bookImport', scope: 'selection', enabledSetting: 'auto_import',
  }]);
  assert.deepEqual(manifest.contributes.filter(action => action.kind === 'bookAction').map(({id, command, private: value, when, lockAfterSetting}) => ({id, command, private: value, when, lockAfterSetting})), [
    {id: 'hide', command: 'privateLibrary.setPrivate', private: true, when: 'public', lockAfterSetting: 'lock_after_hide'},
    {id: 'restore', command: 'privateLibrary.setPrivate', private: false, when: 'private', lockAfterSetting: undefined},
  ]);
});
