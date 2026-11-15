import { DOMParser } from 'linkedom/worker';
import { Readability } from '@mozilla/readability';
import TurndownService from 'turndown';

const encoder = new TextEncoder();
const maxHtmlBytes = 2 * 1024 * 1024;
const maxMarkdownBytes = 512 * 1024;
const trackingKey = /^(?:utm_.+|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|_hsenc|_hsmi)$/i;
const unwantedToken = /(?:^|[\s_-])(?:ads?|advert(?:s|isement|ising)?|adsbygoogle|cookie(?:s|banner)?|consent|newsletter|social-share|share-tools|related-posts?|recommended|recommendations|comments?|sidebar)(?:$|[\s_-])/i;
const metadataSelector = '[rel="author"], [itemprop="author"], [itemprop="datePublished"], .byline, .dateline, .post-meta, .entry-meta, .article-meta, header time';

function cleanText(value, limit) {
  return String(value || '').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '')
    .replace(/\s+/g, ' ').trim().slice(0, limit).replace(/[\ud800-\udbff]$/, '');
}

function escapeText(value) {
  return value.replace(/([\\`*_[\]<>])/g, '\\$1');
}

function escapePlain(value) {
  return value.replace(/([\\`*_[\]<>#~|])/g, '\\$1')
    .replace(/^(\s*)([-+]|\d+\.)\s/gm, (_, indent, marker) => indent + '\\' + marker + ' ');
}

function checkDocumentSize(document) {
  const pending = [[document, 0]];
  let count = 0;
  while (pending.length) {
    const [node, depth] = pending.pop();
    if (++count > 20000 || depth > 128) throw new Error('Article document is too large');
    for (let child = node.lastChild; child; child = child.previousSibling) pending.push([child, depth + 1]);
  }
}

function safeUrl(value, base, image = false) {
  if (typeof value !== 'string' || !value.trim() || /[\u0000-\u001f\u007f]/.test(value.trim())) return null;
  try {
    const url = new URL(value.trim(), base);
    if (!/^https?:$/.test(url.protocol) || url.username || url.password) return null;
    const host = url.hostname.toLowerCase();
    if (host === 'localhost' || /\.(?:localhost|local|internal)$/.test(host) ||
        /^\[(?:::|::1|f[cd]|fe[89ab])/i.test(host) ||
        /^(?:0|10|127)\.|^169\.254\.|^192\.168\.|^172\.(?:1[6-9]|2\d|3[01])\./.test(host)) return null;
    if (image && /(?:^|[\/_.-])(?:spacer|transparent|pixel|tracking|placeholder|blank|loading)(?:[\/_.-]|$)/i.test(url.pathname)) return null;
    const query = url.search.slice(1).split('&').filter(part => {
      try { return !trackingKey.test(decodeURIComponent(part.split('=')[0].replace(/\+/g, ' '))); }
      catch (_) { return true; }
    }).join('&');
    url.search = query ? '?' + query : '';
    return url.href.replace(/</g, '%3C').replace(/>/g, '%3E');
  } catch (_) {
    return null;
  }
}

function removeNoise(document) {
  document.querySelectorAll('style, link, base, noscript, template, iframe, frame, frameset, object, embed, form, input, button, select, textarea, nav, aside, [hidden], [aria-hidden="true"], [role="navigation"], [role="complementary"], [data-ad-client], [data-ad-slot]')
    .forEach(node => node.remove());
  document.querySelectorAll('script').forEach(node => {
    // Readability consumes JSON-LD as data before removing all scripts.
    if (node.getAttribute('type') !== 'application/ld+json') node.remove();
  });
  document.querySelectorAll('body *').forEach(node => {
    const marker = `${node.id || ''} ${node.getAttribute('class') || ''}`.replace(/([a-z])([A-Z])/g, '$1-$2');
    const style = node.getAttribute('style') || '';
    if ((!/^(?:ARTICLE|MAIN|BODY)$/.test(node.nodeName) && unwantedToken.test(marker)) ||
        /(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)/i.test(style)) node.remove();
  });
}

function imageUrl(node, base) {
  const width = Number(node.getAttribute('width'));
  const height = Number(node.getAttribute('height'));
  if ((width > 0 && width <= 2) || (height > 0 && height <= 2)) return null;
  for (const value of [node.getAttribute('data-src'), node.getAttribute('data-original'), node.getAttribute('data-lazy-src'), node.getAttribute('src')]) {
    const url = safeUrl(value, base, true);
    if (url) return url;
  }
  const srcset = node.getAttribute('data-srcset') || node.getAttribute('srcset') || '';
  for (const candidate of srcset.split(',').reverse()) {
    const url = safeUrl(candidate.trim().split(/\s+/)[0], base, true);
    if (url) return url;
  }
  return null;
}

function markdownConverter(url, include_images) {
  const service = new TurndownService({headingStyle: 'atx', codeBlockStyle: 'fenced', bulletListMarker: '-', emDelimiter: '*'});
  const escape = service.escape;
  service.escape = text => escape(text).replace(/</g, '\\<');
  service.remove(['script', 'style', 'iframe', 'object', 'embed', 'input', 'form']);
  service.addRule('fencedCode', {
    filter: 'pre',
    replacement: (_, node) => {
      const code = node.textContent.replace(/\n$/, '');
      let length = 3, match;
      const ticks = /`+/g;
      while ((match = ticks.exec(code))) length = Math.max(length, match[0].length + 1);
      const fence = '`'.repeat(length);
      const language = (node.firstElementChild?.getAttribute('class') || '').match(/(?:^|\s)language-([a-z0-9_+-]{1,32})(?:\s|$)/i)?.[1] || '';
      return '\n\n' + fence + language + '\n' + code + '\n' + fence + '\n\n';
    },
  });
  service.addRule('safeLink', {
    filter: 'a',
    replacement: (content, node) => {
      // Image links are already ordinary links; Markdown cannot nest links.
      if (node.querySelector('img, a')) return content;
      const href = safeUrl(node.getAttribute('href'), url);
      return href && content.trim() ? `[${content}](<${href}>)` : content;
    },
  });
  service.addRule('imageLink', {
    filter: 'img',
    replacement: (_, node) => {
      const href = include_images ? imageUrl(node, url) : null;
      return href ? `[图片：${escapeText(cleanText(node.getAttribute('alt') || '查看图片', 160))}](<${href}>)` : '';
    },
  });
  service.addRule('table', {
    filter: 'table',
    replacement: (_, table) => {
      const rows = Array.from(table.querySelectorAll('tr')).filter(row => row.closest('table') === table);
      const cells = rows.map(row => Array.from(row.children).filter(cell => /^(TH|TD)$/.test(cell.nodeName))
        .map(cell => service.turndown(cell).trim().replace(/\n+/g, ' / ').replace(/\|/g, '\\|')));
      if (!cells.length || !cells.some(row => row.length)) return '';
      const width = Math.max(...cells.map(row => row.length));
      const lines = cells.map(row => '| ' + Array.from({length: width}, (_, i) => row[i] || '').join(' | ') + ' |');
      const heading = Array.from(rows[0].children).some(cell => cell.nodeName === 'TH');
      if (!heading) lines.unshift('| ' + Array(width).fill('').join(' | ') + ' |');
      lines.splice(1, 0, '| ' + Array(width).fill('---').join(' | ') + ' |');
      return '\n\n' + lines.join('\n') + '\n\n';
    },
  });
  return service;
}

export function extract(input) {
  if (!input || input.actionId !== 'extract' || typeof input.html !== 'string' ||
      typeof input.url !== 'string' || encoder.encode(input.html).length > maxHtmlBytes) throw new Error('Invalid article input');
  const source = safeUrl(input.url, input.url);
  if (!source) throw new Error('Invalid article input');
  const settings = input.settings || {};
  let title, body, metadata = '';
  if (input.plainText === true) {
    const text = input.html.replace(/\r\n?/g, '\n').replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '').trim();
    title = cleanText(text.split('\n').find(line => line.trim()) || '网页正文', 200);
    body = escapePlain(text);
  } else {
    const parser = new DOMParser();
    let document = parser.parseFromString(input.html, 'text/html');
    if (document.documentElement?.nodeName !== 'HTML') {
      document = parser.parseFromString('<html><head></head><body>' + input.html + '</body></html>', 'text/html');
      document.body.querySelectorAll('title, meta, base, link').forEach(node => document.head.appendChild(node));
    }
    Object.defineProperty(document, 'documentURI', {value: source});
    Object.defineProperty(document, 'baseURI', {value: source});
    checkDocumentSize(document);
    removeNoise(document);
    const documentHeading = cleanText(document.querySelector('article h1, main h1, h1')?.textContent, 200);
    const date = document.querySelector('article time[datetime], main time[datetime]')?.getAttribute('datetime');
    const article = new Readability(document, {
      maxElemsToParse: 20000,
      charThreshold: 80,
      serializer: element => element,
    }).parse();
    if (!article || !article.content || article.textContent.trim().length < 40) throw new Error('No article content');
    const linkText = Array.from(article.content.querySelectorAll('a')).reduce((length, node) => length + node.textContent.trim().length, 0);
    if (linkText > article.textContent.trim().length * 0.8) throw new Error('No article content');
    title = cleanText(article.title || document.title || documentHeading || '网页正文', 200);
    const heading = article.content.querySelector('h1, h2');
    if (heading && cleanText(heading.textContent, 201) === title) heading.remove();
    article.content.querySelectorAll(metadataSelector).forEach(node => node.remove());
    if (settings.include_metadata !== false) {
      metadata = [cleanText(article.byline, 300), cleanText(article.publishedTime || date, 80)].filter(Boolean).map(escapeText).join(' · ');
    }
    body = markdownConverter(source, settings.include_images !== false).turndown(article.content).trim();
  }
  if (!body || !title) throw new Error('No article content');
  const markdown = ['# ' + escapeText(title), metadata, body, `[来源](<${source}>)`].filter(Boolean).join('\n\n');
  if (encoder.encode(markdown).length > maxMarkdownBytes) throw new Error('Article output is too large');
  return {title, markdown};
}
