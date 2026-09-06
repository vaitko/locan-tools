// Verifies every internal href/src in dist/**/*.html resolves to a built file. Exit 1 on any miss.
import { readdirSync, statSync, existsSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const DIST = new URL('../dist/', import.meta.url).pathname;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (name.endsWith('.html')) out.push(p);
  }
  return out;
}

function resolves(href) {
  const clean = href.split('#')[0].split('?')[0];
  if (!clean || clean === '/') return existsSync(join(DIST, 'index.html'));
  const p = join(DIST, decodeURIComponent(clean));
  if (existsSync(p)) return statSync(p).isDirectory() ? existsSync(join(p, 'index.html')) : true;
  return existsSync(`${p}.html`) || existsSync(join(`${p}`, 'index.html'));
}

const files = walk(DIST);
const missing = new Map();
let checked = 0;
for (const file of files) {
  const html = readFileSync(file, 'utf8');
  for (const m of html.matchAll(/\b(?:href|src|content)="(\/[^"]*)"/g)) {
    const url = m[1];
    if (url.startsWith('//')) continue;
    checked++;
    if (!resolves(url)) {
      if (!missing.has(url)) missing.set(url, new Set());
      missing.get(url).add(relative(DIST, file));
    }
  }
}

console.log(`Checked ${checked} internal references across ${files.length} pages.`);
if (missing.size) {
  console.error(`\n${missing.size} broken internal link target(s):`);
  for (const [url, pages] of missing) console.error(`  ${url}\n    ← ${[...pages].slice(0, 4).join(', ')}${pages.size > 4 ? ` (+${pages.size - 4})` : ''}`);
  process.exit(1);
}
console.log('All internal links resolve.');
