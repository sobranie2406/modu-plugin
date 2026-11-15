import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

const manifest = JSON.parse(await readFile(new URL('../packages/prompt-pack/manifest.json',import.meta.url),'utf8'));

test('all prompt contributions use the three real declared settings', () => {
  assert.equal(manifest.version,'1.1.1');
  assert.deepEqual(manifest.settings.map(setting=>setting.key),['tone','quote_original','max_words']);
  for (const contribution of manifest.contributes) {
    const keys=Array.from(contribution.prompt.matchAll(/\{setting\.([a-z][a-z0-9_]{0,39})\}/g),match=>match[1]);
    assert.deepEqual(keys.sort(),['max_words','quote_original','tone']);
    assert.match(contribution.prompt,/concise/);
    assert.match(contribution.prompt,/detailed/);
    assert.match(contribution.prompt,/true/);
    assert.match(contribution.prompt,/false/);
  }
});

test('prompt-only contributions keep their identities, selection scope and defaults', () => {
  assert.deepEqual(manifest.contributes.map(({kind,id})=>[kind,id]),[
    ['aiSkill','deep-summary'],['aiSkill','socratic-questions'],['selectionAction','explain-selection']
  ]);
  assert.deepEqual(manifest.settings.map(setting=>setting.defaultValue),['concise',false,300]);
  const selection=manifest.contributes.find(contribution=>contribution.kind==='selectionAction');
  assert.equal(selection.scope,'context');
  assert.match(selection.prompt,/\{selection\}/);
  assert.deepEqual(manifest.capabilities,['ai:prompt-pack','ui:selection-action']);
  assert.ok(manifest.contributes.every(contribution=>!('entry' in contribution)));
});
