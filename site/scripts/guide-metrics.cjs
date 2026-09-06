// Guide metrics: body words (excl. frontmatter + ManualTodo), meta description length, links, blockquote char counts.
const fs = require('fs');
for (const f of process.argv.slice(2)) {
  const s = fs.readFileSync(f, 'utf8');
  const fm = s.match(/^---\n([\s\S]*?)\n---\n/);
  const desc = fm[1].match(/^description: "(.*)"$/m)[1];
  const body = s.slice(fm[0].length).replace(/<ManualTodo>[\s\S]*?<\/ManualTodo>/g, '').replace(/^import .*$/m, '');
  const words = body.split(/\s+/).filter(Boolean).length;
  console.log('==', f.split('/').pop());
  console.log('meta description chars:', desc.length);
  console.log('body words:', words);
  console.log('ManualTodo blocks:', (s.match(/<ManualTodo>/g) || []).length);
  console.log('faq items:', (fm[1].match(/^  - q:/gm) || []).length);
  const links = body.match(/\]\(\/(tools|guides)\/[^)]*\)/g) || [];
  console.log('internal links:', links.length, [...new Set(links.map((l) => l.slice(2, -1)))]);
  console.log('official urls:', body.match(/https:\/\/[^\s)]*/g) || []);
  body.split('\n').filter((l) => l.startsWith('> ')).forEach((q, i) => console.log('blockquote', i + 1, 'chars:', q.slice(2).length));
}
