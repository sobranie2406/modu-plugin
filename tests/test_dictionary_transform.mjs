import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const source = await readFile(new URL('../packages/dictionary-transform/main.js', import.meta.url), 'utf8');
const run = new AsyncFunction('input', 'modu', source);
const candidates = async (word, settings = {}) => (await run({selection: word, settings}, new Proxy({}, {
  get() { throw new Error('No host calls belong in a dictionary transform'); },
}))).candidates;

for (const [word, first] of [
  ['apples', 'apple'], ['approves', 'approve'], ['studies', 'study'],
  ['stopped', 'stop'], ['running', 'run'], ['making', 'make'],
  ['dying', 'die'], ['happier', 'happy'], ['biggest', 'big'],
  ["s'leve", 'leve'], ['s’leve', 'leve'], ["l'epaule", 'epaule'],
  ['l’épaule', 'épaule'], ['qu’il', 'il'],
]) {
  test(`${word} first tries ${first}`, async () => {
    const result = await candidates(word);
    assert.equal(result[0], first);
    assert.ok(!result.includes(word));
    assert.ok(result.length <= 12);
  });
}

test('keeps alternative English candidates for actual dictionary resolution', async () => {
  assert.deepEqual((await candidates('apples')).slice(0, 2), ['apple', 'appl']);
  assert.deepEqual((await candidates('approves')).slice(0, 2), ['approve', 'approv']);
});

test('custom rules precede defaults and support captures', async () => {
  assert.deepEqual(await candidates('preApples', {english: false, french: false,
    rules: JSON.stringify([{pattern: '^pre(.+)s$', replacement: '$1', flags: ''}])}), ['Apple']);
  assert.equal((await candidates('apples', {rules: JSON.stringify([
    {pattern: '^apples$', replacement: 'fruit'},
  ])}))[0], 'fruit');
});

test('each regex transforms the original rather than overwriting later rules', async () => {
  assert.deepEqual(await candidates('unapples', {english: false, french: false,
    rules: JSON.stringify([
      {pattern: '^un', replacement: ''}, {pattern: 's$', replacement: ''},
    ])}), ['apples', 'unapple']);
});

test('individual defaults can be disabled', async () => {
  assert.deepEqual(await candidates('apples', {english: false}), []);
  assert.deepEqual(await candidates('l’épaule', {french: false}), []);
});

test('malformed rules do not suppress built-in candidates', async () => {
  for (const rules of ['{', 'null', '{}', '42']) {
    assert.equal((await candidates('apples', {rules}))[0], 'apple');
  }
  assert.deepEqual(await candidates('hello', {english: false, rules: JSON.stringify([
    {pattern: '[', replacement: 'bad'},
    {pattern: 'hello', replacement: 'bad', flags: 'ii'},
    {pattern: 'hello', replacement: 'bad', flags: 'y'},
    {pattern: 'hello', replacement: 'valid'},
  ])}), ['valid']);
});

test('bounds and deduplicates candidate text without changing accents', async () => {
  const rules = Array.from({length: 40}, (_, i) => ({pattern: 'word', replacement: `candidate${i}`}));
  assert.equal((await candidates('word', {rules: JSON.stringify(rules)})).length, 12);
  assert.deepEqual(await candidates('word', {rules: JSON.stringify([
    {pattern: 'word', replacement: 'same'},
    {pattern: 'word', replacement: 'same'},
    {pattern: 'word', replacement: '\n'},
    {pattern: 'word', replacement: 'a\nb'},
  ])}), ['same']);
  assert.deepEqual(await candidates('a'.repeat(257)), []);
  assert.deepEqual(await candidates(''), []);
  assert.equal((await candidates('l’épaule'))[0], 'épaule');
});
