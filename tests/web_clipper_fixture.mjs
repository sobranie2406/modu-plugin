export const english = 'The observatory has studied the night sky for decades. Its researchers compare old records with new measurements, preserve clear explanations, and publish detailed evidence for readers. ';
export function article(body, head = '', title = 'Night sky report') {
  return `<!doctype html><html><head><title>${title}</title>${head}</head><body><nav>ADVERTISING NAVIGATION <a href="/ads">subscribe</a></nav><article><header><h1>${title}</h1></header><p>${english.repeat(3)}</p>${body}<p>${english.repeat(3)}</p></article><aside>RELATED RECOMMENDATIONS</aside><footer class="cookie-banner">COOKIE BANNER</footer></body></html>`;
}
export const sampleHtml = article(`
  <h2>Research details</h2><p>Read the <a href="/source?part=2&utm_source=newsletter&signature=x%20y">source records</a>.</p>
  <ul><li>First observation</li><li>Second observation</li></ul><blockquote>Evidence comes first.</blockquote>
  <pre><code class="language-js">const sky = "clear";</code></pre>
  <table><thead><tr><th>Year</th><th>Count</th></tr></thead><tbody><tr><td>2025</td><td>12</td></tr></tbody></table>
  <figure><img src="/sky.png?size=800&utm_source=tracker" alt="Night sky"><figcaption>The observatory</figcaption></figure>
  <div class="advertisement">AD PAID PLACEMENT</div><div class="related-posts">PROMOTED STORIES</div>
  <script>globalThis.evilExecuted = true; fetch('https://example.org/evil');</script>
`, '<meta name="author" content="Alice Example"><meta property="article:published_time" content="2026-11-15T12:00:00Z">');
