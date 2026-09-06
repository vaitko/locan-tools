// Aggregates every <ManualTodo> block from the guides into Markdown for docs/MANUAL-TODO.md.
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const DIR = new URL('../src/content/guides/', import.meta.url).pathname;
const files = readdirSync(DIR).filter((f) => f.endsWith('.mdx')).sort();

const strip = (html) =>
  html
    .replace(/<li>/g, '\n  - ')
    .replace(/<\/li>/g, '')
    .replace(/<\/?(ul|ol|p)>/g, '')
    .replace(/<strong>(.*?)<\/strong>/g, '**$1**')
    .replace(/<[^>]+>/g, '')
    .replace(/\n\s*\n/g, '\n')
    .trim();

let total = 0;
for (const f of files) {
  const src = readFileSync(join(DIR, f), 'utf8');
  const title = src.match(/^title:\s*"(.*)"/m)?.[1] ?? f;
  const blocks = [...src.matchAll(/<ManualTodo>([\s\S]*?)<\/ManualTodo>/g)];
  if (!blocks.length) continue;
  const slug = f.replace(/\.mdx$/, '');
  console.log(`\n### ${title}\n\n\`/guides/${slug}/\` — ${blocks.length} block(s)\n`);
  blocks.forEach((b, i) => {
    // find the nearest preceding heading for context
    const before = src.slice(0, b.index);
    const heading = [...before.matchAll(/^##+\s+(.*)$/gm)].pop()?.[1] ?? 'Intro';
    console.log(`- [ ] **Block ${i + 1} — under "${heading}"**${strip(b[1]).split('\n').map((l) => (l.trim() ? `\n  ${l}` : '')).join('')}`);
    total++;
  });
}
console.error(`\n${total} TODO blocks across ${files.length} guides.`);
