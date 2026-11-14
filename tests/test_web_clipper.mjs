import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../packages/web-clipper/main.js', import.meta.url), 'utf8');
const run = new Function('input', 'modu', `return (async () => {${source}\n})();`);

test('the library action opens the native capture page once', async () => {
  const calls = [];
  const result = await run({actionId: 'capture'}, {articles: {capture: async (input) => { calls.push(input); return {opened: true}; }}});
  assert.deepEqual(calls, [{}]);
  assert.deepEqual(result, {title: '网页稍后阅读', text: ''});
});

test('unknown actions never open the capture page', async () => {
  let calls = 0;
  await assert.rejects(() => run({actionId: 'other'}, {articles: {capture: async () => { calls++; }}}));
  assert.equal(calls, 0);
});
