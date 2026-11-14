import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const load = async name => new AsyncFunction('input', 'modu', await readFile(
  new URL(`../packages/${name}/main.js`, import.meta.url), 'utf8'));

test('private library dispatches only declared open and lock actions', async () => {
  const run = await load('private-books');
  const calls = [];
  const modu = { privateLibrary: {
    open: async () => calls.push('open'), lock: async () => calls.push('lock'),
  }};
  assert.equal((await run({ actionId: 'open' }, modu)).text, '');
  assert.match((await run({ actionId: 'lock' }, modu)).text, /锁定/);
  await assert.rejects(run({ actionId: 'unknown' }, modu));
  assert.deepEqual(calls, ['open', 'lock']);
});

test('text cleanup uses selected text and declared settings', async () => {
  const run = await load('text-tools');
  assert.equal((await run({selection: '  a\t b \r\n  中文  ', settings: {}}, {})).text, 'a b\n中文');
  assert.equal((await run({selection: 'a \n  b', settings: {trim_lines: false}}, {})).text, 'a \n b');
});
