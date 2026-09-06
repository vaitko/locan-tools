import { apiFetch, ApiClientError, esc, $ } from '../api';

/** The parts of <business-search> this module touches (see ../business-search). */
type SearchElement = HTMLElement & { readonly text: string; reset(): void };

interface Point {
  row: number;
  col: number;
  lat: number;
  lng: number;
  rank: number | null;
  error?: boolean;
}
interface Summary {
  averageRank: number | null;
  bestRank: number | null;
  worstRank: number | null;
  visibleShare: number;
  top3Share: number;
  pointsChecked: number;
}
interface Competitor {
  placeId: string;
  name: string;
  appearances: number;
  averageRank: number;
}
interface Result {
  business: { placeId: string; name: string | null; address: string | null; lat: number; lng: number };
  keyword: string;
  grid: { size: number; spacingKm: number; points: Point[] };
  summary: Summary;
  competitors: Competitor[];
}

type Band = 'top' | 'mid' | 'low' | 'none';

const CELL_CLASS: Record<Band, string> = {
  top: 'bg-success text-white',
  mid: 'bg-warning text-white',
  low: 'bg-[#F97316] text-white',
  none: 'bg-[#CBD5E1] text-ink/70',
};
const TEXT_CLASS: Record<Band, string> = {
  top: 'text-success',
  mid: 'text-warning',
  low: 'text-[#F97316]',
  none: 'text-muted',
};
const SUBMIT_LABEL = 'Check my local rankings';

const form = $<HTMLFormElement>('rankForm');
const search = form.querySelector<SearchElement>('business-search')!;
const submit = $<HTMLButtonElement>('rankSubmit');
const keywordInput = $<HTMLInputElement>('rankKeyword');
const errorEl = $('rankError');
const results = $('rankResults');

function band(rank: number | null): Band {
  if (rank == null) return 'none';
  if (rank <= 3) return 'top';
  if (rank <= 10) return 'mid';
  return 'low';
}

function pct(share: number): number {
  return Math.round((Number(share) || 0) * 100);
}

function setLoading(on: boolean, points = 0) {
  submit.disabled = on;
  submit.querySelector('[data-spinner]')!.classList.toggle('hidden', !on);
  submit.querySelector<HTMLElement>('[data-label]')!.textContent = on ? `Checking ${points} points…` : SUBMIT_LABEL;
}

function showError(msg: string) {
  errorEl.textContent = msg;
  errorEl.classList.remove('hidden');
}

function checked(name: string): string {
  return form.querySelector<HTMLInputElement>(`input[name="${name}"]:checked`)?.value ?? '';
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.classList.add('hidden');

  const placeId = (form.querySelector<HTMLInputElement>('input[name=biz_placeId]')?.value ?? '').trim();
  if (!placeId) {
    showError(search.text ? 'Pick your business from the suggestions so we know its exact location.' : 'Type your business name and pick it from the suggestions.');
    return;
  }
  const keyword = keywordInput.value.trim();
  if (keyword.length < 2) {
    showError('Enter a keyword to check (at least 2 characters).');
    keywordInput.focus();
    return;
  }
  const gridSize: 3 | 5 = checked('gridSize') === '5' ? 5 : 3;
  const spacingRaw = Number(checked('spacingKm'));
  const spacingKm: 0.5 | 1 | 2 = spacingRaw === 0.5 || spacingRaw === 2 ? spacingRaw : 1;

  setLoading(true, gridSize * gridSize);
  try {
    const data = await apiFetch<Result>('/tools/rank-checker', {
      method: 'POST',
      body: { placeId, keyword, gridSize, spacingKm, languageCode: 'en' },
      timeoutMs: 60_000,
    });
    render(data);
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'local-rank-checker' });
  } catch (err) {
    showError(err instanceof ApiClientError ? err.message : 'Something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
});

$('rankAnother').addEventListener('click', () => {
  results.classList.add('hidden');
  keywordInput.value = '';
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  keywordInput.focus({ preventScroll: true });
});

$('rankReset').addEventListener('click', () => {
  results.classList.add('hidden');
  form.reset();
  search.reset();
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function renderGrid(grid: Result['grid']) {
  const el = $('rankGrid');
  const size = Number(grid.size) || 3;
  const centre = Math.floor(size / 2);
  el.style.gridTemplateColumns = `repeat(${size}, minmax(0, 1fr))`;
  const numCls = size === 3 ? 'text-3xl' : 'text-xl sm:text-2xl';
  const points = [...(grid.points ?? [])].sort((a, b) => a.row - b.row || a.col - b.col);

  el.innerHTML = points
    .map((p) => {
      const isCentre = p.row === centre && p.col === centre;
      const failed = Boolean(p.error);
      const label = failed ? '—' : p.rank == null ? '20+' : String(p.rank);
      const cls = failed ? 'bg-line text-muted' : CELL_CLASS[band(p.rank)];
      const status = failed ? 'check failed' : p.rank == null ? 'not in the top 20' : `rank ${p.rank}`;
      const title = `${isCentre ? 'Your location · ' : ''}Row ${p.row + 1}, column ${p.col + 1} · ${Number(p.lat).toFixed(5)}, ${Number(p.lng).toFixed(5)} · ${status}`;
      return `
      <div class="relative grid aspect-square place-items-center rounded-lg ${cls} ${numCls} font-extrabold leading-none ${isCentre ? 'z-10 ring-4 ring-ink' : ''}" title="${esc(title)}">
        ${esc(label)}
        ${isCentre ? '<span class="absolute bottom-1 left-1/2 -translate-x-1/2 rounded-full bg-ink px-1.5 text-[10px] font-bold leading-4 text-white">You</span>' : ''}
      </div>`;
    })
    .join('');
}

function tile(value: string, label: string, cls = 'text-ink'): string {
  return `
    <div class="rounded-xl border border-line bg-white px-3 py-4 text-center">
      <div class="text-3xl font-extrabold ${cls}">${esc(value)}</div>
      <div class="mt-1 text-xs font-semibold leading-snug text-muted">${esc(label)}</div>
    </div>`;
}

function shareClass(share: number): string {
  return share >= 0.75 ? 'text-success' : share >= 0.4 ? 'text-warning' : 'text-danger';
}

function renderSummary(s: Summary) {
  const rankTile = (rank: number | null, label: string, decimals = 0) =>
    tile(rank == null ? '—' : `#${Number(rank).toFixed(decimals)}`, label, TEXT_CLASS[band(rank)]);
  $('rankSummary').innerHTML = [
    rankTile(s.averageRank, 'Average rank', 1),
    rankTile(s.bestRank, 'Best rank'),
    rankTile(s.worstRank, 'Worst rank'),
    tile(`${pct(s.visibleShare)}%`, 'Visible at this share of points', shareClass(s.visibleShare)),
    tile(`${pct(s.top3Share)}%`, 'Top 3 at this share of points', shareClass(s.top3Share)),
    tile(String(s.pointsChecked ?? 0), 'Points checked'),
  ].join('');
}

function renderVerdict(s: Summary) {
  const top3 = pct(s.top3Share);
  let tone: string;
  let title: string;
  let text: string;
  if (s.top3Share >= 0.75) {
    tone = 'border-success/30 bg-success-tint';
    title = 'Strong local dominance';
    text = `You hold a top-3 position at ${top3}% of the points on this grid — proximity and relevance are both working for you. Protect it with steady new reviews and fresh photos, then re-run with 2 km spacing to find the edge of your reach.`;
  } else if (s.top3Share >= 0.4) {
    tone = 'border-warning/30 bg-warning-tint';
    title = 'You own your immediate area but fade further out';
    text = `Top 3 at ${top3}% of points. Proximity is winning: the further the searcher is from you, the more a closer competitor takes your place. You cannot move your building, so work on relevance and prominence — categories, services, review velocity and mentions across the web.`;
  } else {
    tone = 'border-danger/30 bg-danger-tint';
    title = 'You are mostly invisible for this keyword';
    text = `Top 3 at only ${top3}% of points. Either the keyword does not match your categories, or the profile is missing signals Google needs. Check your categories and profile completeness first, then re-run.`;
  }
  const el = $('rankVerdict');
  el.className = `rounded-2xl border p-6 ${tone}`;
  el.innerHTML = `
    <p class="eyebrow">What this means</p>
    <h2 class="mt-1 text-lg font-extrabold">${esc(title)}</h2>
    <p class="mt-2 text-[15px] leading-relaxed text-ink/85">${esc(text)}</p>
    <p class="mt-3 text-[15px] text-ink/85">Fix relevance with the <a href="/tools/gbp-category-optimizer/" class="link">Category Optimizer</a>, then completeness with the <a href="/tools/google-business-profile-optimizer/" class="link">GBP Optimizer</a>.</p>`;
}

function renderCompetitors(list: Competitor[], pointsChecked: number) {
  $('rankCompetitors').innerHTML = list.length
    ? list
        .map(
          (c, i) => `
      <tr class="border-t border-line">
        <td class="py-2.5 pr-3 font-bold text-muted">${i + 1}</td>
        <td class="py-2.5 pr-3 font-bold text-ink">${esc(c.name || 'Unknown business')}</td>
        <td class="py-2.5 pr-3 text-muted">${esc(c.appearances)}<span class="text-muted/70">/${esc(pointsChecked)}</span></td>
        <td class="py-2.5 text-muted">#${esc(Number(c.averageRank).toFixed(1))}</td>
      </tr>`,
        )
        .join('')
    : '<tr class="border-t border-line"><td colspan="4" class="py-3 text-muted">No other businesses appeared in these results.</td></tr>';
}

function render(d: Result) {
  results.classList.remove('hidden');
  $('rankBizName').textContent = d.business?.name || 'Your business';
  $('rankBizAddress').textContent = d.business?.address ?? '';
  $('rankKeywordTag').textContent = `“${d.keyword}”`;
  const size = Number(d.grid?.size) || 3;
  $('rankGridTag').textContent = `Grid: ${size}×${size} · ${Number(d.grid?.spacingKm) || 1} km spacing`;

  renderGrid(d.grid);
  renderSummary(d.summary);
  renderVerdict(d.summary);
  renderCompetitors(d.competitors ?? [], d.summary?.pointsChecked ?? d.grid?.points?.length ?? 0);

  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
