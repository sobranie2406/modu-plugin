import {build} from 'esbuild';
import {createHash} from 'node:crypto';
import {readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const result = await build({
  absWorkingDir: root,
  entryPoints: ['src/web-clipper/extract.mjs'],
  bundle: true,
  write: false,
  platform: 'browser',
  target: ['chrome83'],
  format: 'iife',
  globalName: 'ModuArticle',
  minify: true,
  legalComments: 'eof',
  plugins: [{name: 'linkedom-worker83', setup(build) {
    build.onLoad({filter: /linkedom\/worker\.js$/}, async args => {
      const source = await readFile(args.path, 'utf8');
      // LinkeDOM 0.18.12 uses Array.at only for its two title lookups.
      if ((source.match(/\.at\(0\)/g) || []).length !== 2) throw new Error('Unexpected LinkeDOM source');
      return {contents: source.replaceAll('.at(0)', '[0]'), loader: 'js'};
    });
  }}],
});
const contents = result.outputFiles[0].text + '\nreturn ModuArticle.extract(input);\n';
if (Buffer.byteLength(contents) > 512 * 1024) throw new Error('Article script exceeds 512 KiB');
await writeFile(resolve(root, 'packages/web-clipper/extract.js'), contents);
console.log(JSON.stringify({bytes: Buffer.byteLength(contents), sha256: createHash('sha256').update(contents).digest('hex')}));
