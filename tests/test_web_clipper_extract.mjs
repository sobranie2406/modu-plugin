import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {article, english, sampleHtml} from './web_clipper_fixture.mjs';
import {runArticle} from './web_clipper_worker.mjs';

async function extract(input) {
  const value = await runArticle(input);
  assert.equal(value.error, undefined);
  assert.deepEqual(Object.keys(value.result).sort(), ['markdown','title']);
  assert.equal(value.calls, 0);
  assert.equal(value.evilExecuted, false);
  assert.equal(value.domAbsent, true);
  return value.result;
}

test('the self-contained article bundle fits its separate limit and needs no remote imports', async () => {
  const source = await readFile(new URL('../packages/web-clipper/extract.js', import.meta.url), 'utf8');
  assert.ok(Buffer.byteLength(source) > 128 * 1024);
  assert.ok(Buffer.byteLength(source) <= 512 * 1024);
  assert.doesNotMatch(source, /\bimport\s*\(|\bimportScripts\s*\(|\beval\s*\(|new Function\s*\(/);
});

test('offline extraction preserves structure and metadata with old WebView APIs absent', async () => {
  const {title, markdown} = await extract({html:sampleHtml});
  assert.equal(title, 'Night sky report');
  for (const pattern of [/## Research details/, /-\s+First observation/, /> Evidence comes first/, /```/, /const sky = "clear";/,
      /\| Year \| Count \|/, /\| --- \| --- \|/, /\| 2025 \| 12 \|/, /Alice Example/, /2026-11-15T12:00:00Z/]) assert.match(markdown,pattern);
  assert.match(markdown,/\[source records\]\(<https:\/\/example.org\/source\?part=2&signature=x%20y>\)/);
  assert.match(markdown,/\[图片：Night sky\]\(<https:\/\/example.org\/sky.png\?size=800>\)/);
  assert.doesNotMatch(markdown,/!\[|utm_source|ADVERTISING|RECOMMENDATIONS|COOKIE BANNER|AD PAID|PROMOTED STORIES|<script|evilExecuted/);
});

test('metadata and image settings independently disable their optional output', async () => {
  for (const settings of [{include_metadata:false},{include_images:false},{include_metadata:false,include_images:false}]) {
    const {markdown} = await extract({html:sampleHtml,settings});
    if (settings.include_metadata===false) assert.doesNotMatch(markdown,/Alice Example|2026-11-15/); else assert.match(markdown,/Alice Example/);
    if (settings.include_images===false) assert.doesNotMatch(markdown,/sky.png/); else assert.match(markdown,/sky.png/);
    assert.match(markdown,/Research details/);
  }
});

test('article header prose and sibling body sections remain readable in Chinese', async () => {
  const prose='这是一段关于夜空观测的正文。研究者记录数据，反复比较结果，并向读者解释证据的来源。';
  const html=`<html><head><title>观测记录</title></head><body><main><article><header><h1>观测记录</h1><p>HEADERPROSE 这里是正文的开篇说明，不能当成网站导航。</p></header><section><p>FIRSTSECTION ${prose.repeat(8)}</p></section><section><h2>第二节</h2><p>SIBLINGSECTION ${prose.repeat(8)}</p></section></article></main></body></html>`;
  const {markdown}=await extract({html});
  assert.match(markdown,/HEADERPROSE/); assert.match(markdown,/FIRSTSECTION/); assert.match(markdown,/SIBLINGSECTION/); assert.match(markdown,/## 第二节/);
  assert.doesNotMatch(markdown,/## 观测记录/);
});

test('JSON-LD is read only as metadata and cannot execute code', async () => {
  const head='<script type="application/ld+json">'+JSON.stringify({'@context':'https://schema.org','@type':'NewsArticle',headline:'Night sky report',author:{'@type':'Person',name:'李明'},datePublished:'2026-11-14'})+'</script>';
  const {markdown}=await extract({html:article('<p>JSONLD_BODY '+english.repeat(2)+'</p>',head)});
  assert.match(markdown,/李明/); assert.match(markdown,/2026-11-14/); assert.doesNotMatch(markdown,/@context|schema.org/);
});

test('unsafe links, tracking and placeholder images never become active image Markdown', async () => {
  const body='<p><a href="javascript:alert(1)">SAFELABEL</a> <a href="file:///secret">FILELABEL</a></p><img src="data:image/svg+xml,%3Csvg%3E"><img src="/pixel.gif"><img src="https://tracker.example/collect" width="1" height="1"><img src="http://127.0.0.1/local.png"><img src="/placeholder.gif" data-src="/real image.png"><img src="/ok.png" onerror="globalThis.evilExecuted=true">';
  const {markdown}=await extract({html:article(body)});
  assert.match(markdown,/SAFELABEL/); assert.match(markdown,/FILELABEL/); assert.match(markdown,/real%20image.png/); assert.match(markdown,/ok.png/);
  assert.equal((markdown.match(/\[图片：/g)||[]).length,2);
  assert.doesNotMatch(markdown,/javascript:|file:|data:|127.0.0.1|pixel.gif|tracker.example|placeholder.gif|!\[|onerror/);
});

test('a page base element cannot change the host-provided URL used to resolve links', async () => {
  const {markdown}=await extract({html:article('<p><a href="/reference">Reference</a></p>','<base href="https://attacker.example/">')});
  assert.match(markdown,/https:\/\/example.org\/reference/); assert.doesNotMatch(markdown,/attacker.example/);
});

test('linked news images become a single ordinary link rather than nested Markdown links', async () => {
  const {markdown}=await extract({html:article('<p><a href="/photo-full.jpg"><img src="/photo.jpg" alt="Photo"></a></p>')});
  assert.match(markdown,/\[图片：Photo\]\(<https:\/\/example.org\/photo.jpg>\)/);
  assert.doesNotMatch(markdown,/\[\[|photo-full.jpg|!\[/);
});

test('headerless and whitespace-formatted tables preserve all cells without raw HTML', async () => {
  const {markdown}=await extract({html:article('<table>\n<tr>\n<td>甲</td><td>乙</td>\n</tr><tr><td>丙</td><td>丁</td></tr></table>')});
  assert.match(markdown,/\|  \|  \|/); assert.match(markdown,/\| 甲 \| 乙 \|/); assert.match(markdown,/\| 丙 \| 丁 \|/); assert.doesNotMatch(markdown,/<table|<td/);
});

test('plain-text downloads use the same plugin entry without interpreting HTML', async () => {
  const {title,markdown}=await extract({html:'纯文本标题\n\n普通正文 <script>not executable</script>\n下一行',plainText:true});
  assert.equal(title,'纯文本标题'); assert.match(markdown,/普通正文 \\<script\\>not executable\\<\/script\\>/); assert.match(markdown,/下一行/);
});

// Migrated from the former native extractArticle tests; acquisition stays native.
const legacyParagraph='This is the article body, with enough useful text to distinguish it from navigation and menus.';
test('legacy semantic-container cleanup keeps the article and drops page furniture', async () => {
  const {title,markdown}=await extract({url:'https://example.com/news/story?article=1',html:`
    <title>Site title</title><meta property="og:title" content="An article"><nav><a href="/menu">Navigation</a></nav>
    <article><header><h1>An article</h1></header><p>${legacyParagraph}</p><script>alert('secret')</script><style>.x{}</style>
    <div class="advertisement">ADVERTISEMENT</div><aside>SIDEBAR</aside><div id="comments">COMMENT</div><div class="related">RECOMMENDED</div>
    <div hidden>HIDDEN</div><div style="display:none">INVISIBLE</div></article><footer>FOOTER</footer>`});
  assert.equal(title,'An article'); assert.match(markdown,/This is the article body/);
  assert.match(markdown,/\[来源\]\(<https:\/\/example.com\/news\/story\?article=1>\)/);
  assert.doesNotMatch(markdown,/Navigation|secret|ADVERTISEMENT|SIDEBAR|COMMENT|RECOMMENDED|HIDDEN|INVISIBLE|FOOTER|<script|<style/);
});

test('legacy paragraph-density fallback excludes a link-heavy menu', async () => {
  const links=Array.from({length:12},(_,i)=>`<a href="/${i}">Long navigation menu number ${i}</a>`).join('');
  const {markdown}=await extract({html:`<title>Report</title><div>${links}</div><section><p>${legacyParagraph}</p><p>${legacyParagraph}</p></section>`});
  assert.match(markdown,/This is the article body/); assert.doesNotMatch(markdown,/navigation menu/);
});

test('legacy Markdown structure handles nested lists and code containing backticks', async () => {
  const {markdown}=await extract({html:`<article><h1>Report</h1><p>${legacyParagraph}</p><h2>Section</h2><p><strong>Bold</strong> and <em>emphasis</em> with <code>a\`b</code>.</p>
    <ol start="3"><li>First<ul><li>Nested</li></ul></li><li>Second</li></ol><blockquote><p>A quotation.</p></blockquote>
    <pre><code>if (a &lt; b) {\n  print(\`\`\`);\n}</code></pre><table><tr><th>Name</th><th>Value</th></tr><tr><td>A | B</td><td>2</td></tr></table></article>`});
  assert.match(markdown,/## Section/); assert.match(markdown,/\*\*Bold\*\* and \*emphasis\*/); assert.match(markdown,/``\s*a`b\s*``/);
  assert.match(markdown,/3\.\s+First\n\s+-\s+Nested/); assert.match(markdown,/4\.\s+Second/); assert.match(markdown,/> A quotation\./);
  assert.match(markdown,/````\nif \(a < b\)/); assert.match(markdown,/\| Name \| Value \|\n\| --- \| --- \|\n\| A \\\| B \| 2 \|/);
});

test('legacy ordinary-link safety keeps query semantics and escapes literal Markdown images', async () => {
  const {markdown}=await extract({url:'https://example.com/news/story?article=1',html:`<article><p>${legacyParagraph}</p><p>
    <a href="../guide?id=2&amp;page=3">Guide</a><a href="javascript:alert(1)">Unsafe</a><a href="https://user:pass@example.com">Credentials</a>
    <img src="/photo.png" alt="A photo"><img src="data:image/png;base64,AAAA" alt="Inline"><a href="http://[broken">Malformed</a>
    &lt;script&gt;plain&lt;/script&gt; ![literal](https://example.com/extra.png)</p></article>`});
  assert.match(markdown,/\[Guide\]\(<https:\/\/example.com\/guide\?id=2&page=3>\)/); assert.match(markdown,/\[图片：A photo\]\(<https:\/\/example.com\/photo.png>\)/);
  assert.doesNotMatch(markdown,/!\[A photo\]|javascript:|user:pass|data:image/); assert.match(markdown,/\\<script\\>plain\\<\/script\\>/); assert.match(markdown,/!\\\[literal\\\]/);
});

test('legacy Chinese and plain-text paths preserve literal content rather than Markdown commands', async () => {
  const {title,markdown}=await extract({html:`<article><h1>中文标题</h1><p>${'这是一段用于稍后阅读的中文正文，保留文字内容。'.repeat(4)}</p></article>`});
  assert.equal(title,'中文标题'); assert.match(markdown,/用于稍后阅读/);
  const plain=await extract({html:legacyParagraph+'\n<script>raw</script>\n![remote](https://x.invalid/image)\n[x](javascript:alert(1))\n# false heading\n- false list\n1. false ordered list',plainText:true});
  assert.match(plain.markdown,/\\<script\\>raw\\<\/script\\>/); assert.match(plain.markdown,/!\\\[remote\\\]/);
  assert.match(plain.markdown,/\\\[x\\\]\(javascript:/); assert.match(plain.markdown,/\n\\# false heading/); assert.match(plain.markdown,/\n\\- false list/); assert.match(plain.markdown,/\n\\1\. false ordered list/);
});

test('legacy empty, link-only, large, deep and many-node documents fail in the worker', async () => {
  const inputs=['<p>Short</p>',`<main><a href="/">${legacyParagraph}</a></main>`,'x'.repeat(2*1024*1024+1),
    '<div>'.repeat(140)+legacyParagraph+'</div>'.repeat(140),'<article>'+'<span>x</span>'.repeat(20001)+'</article>',
    '<article><p>'+'x'.repeat(600*1024)+'</p></article>'];
  for (const html of inputs) { const value=await runArticle({html}); assert.match(value.error,/Error:/); assert.equal(value.calls,0); }
});

test('unknown actions and oversized input/output fail without any host access', async () => {
  for (const input of [{actionId:'capture',html:sampleHtml},{html:'x'.repeat(2*1024*1024+1)},{html:'正文'.repeat(100000),plainText:true},{html:''}]) {
    const value=await runArticle(input); assert.match(value.error,/Error:/); assert.equal(value.calls,0);
  }
});

test('the title is bounded without splitting a Unicode surrogate', async () => {
  const {title}=await extract({html:article('<p>'+english.repeat(2)+'</p>','', '星'.repeat(199)+'🌟more')});
  assert.ok(title.length<=200); assert.doesNotMatch(title,/[\ud800-\udbff]$/);
});
