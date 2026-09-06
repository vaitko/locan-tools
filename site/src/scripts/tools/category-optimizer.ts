import { apiFetch, ApiClientError, esc, $ } from '../api';
import type { BusinessSearch, BusinessSelectedDetail } from '../business-search';

interface Client {
  placeId: string | null;
  businessName: string | null;
  primaryCategory: string | null;
  allCategories: string[];
  reviewCount: number;
}
interface CompetitorCategory {
  category: string;
  count: number;
  outOf: number;
  sourceKeywords: string[];
}
interface Recommendation {
  category: string;
  action: 'add' | 'consider' | 'avoid' | 'keep' | string;
  score: number;
  reasons: string[];
}
interface Opportunity {
  missingCategoryCount: number;
  estimatedKeywordMatchGain: number;
  estimatedServiceSearchGain: number;
  estimatedLocalPackGapsClosed: number;
  headline: string;
}
interface Result {
  client: Client;
  competitorCategories: CompetitorCategory[];
  recommendations: Recommendation[];
  opportunity: Opportunity;
}

const form = $<HTMLFormElement>('catForm');
const search = form.querySelector<BusinessSearch & HTMLElement>('business-search')!;
const submit = $<HTMLButtonElement>('catSubmit');
const errorEl = $('catError');
const results = $('catResults');
const cityEl = $<HTMLInputElement>('catCity');
const keywordsEl = $<HTMLTextAreaElement>('catKeywords');
const servicesEl = $<HTMLTextAreaElement>('catServices');
const perKwEl = $<HTMLSelectElement>('catPerKw');

const ACTIONS: Record<string, { label: string; cls: string }> = {
  add: { label: 'Add', cls: 'bg-success-tint text-success' },
  consider: { label: 'Consider', cls: 'bg-warning-tint text-warning' },
  avoid: { label: 'Avoid', cls: 'bg-danger-tint text-danger' },
  keep: { label: 'Keep', cls: 'bg-surface text-muted border border-line' },
};

function setLoading(on: boolean) {
  submit.disabled = on;
  submit.querySelector('[data-spinner]')!.classList.toggle('hidden', !on);
  submit.querySelector<HTMLElement>('[data-label]')!.textContent = on ? 'Analyzing…' : 'Analyze categories';
}

function showError(msg: string) {
  errorEl.textContent = msg;
  errorEl.classList.remove('hidden');
}

function parseKeywords(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(/\r?\n|,/)) {
    const kw = raw.trim();
    if (kw && !out.some((k) => k.toLowerCase() === kw.toLowerCase())) out.push(kw);
  }
  return out;
}

// Prefill the city with the address minus its last segment (the country), as the legacy tool did.
search.addEventListener('business:selected', (e) => {
  if (cityEl.value.trim()) return;
  const { address } = (e as CustomEvent<BusinessSelectedDetail>).detail;
  const cut = address.lastIndexOf(',');
  cityEl.value = (cut > 0 ? address.slice(0, cut) : address).trim();
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.classList.add('hidden');
  const placeId = search.value?.placeId ?? '';
  const businessName = search.text;
  const city = cityEl.value.trim();
  const keywords = parseKeywords(keywordsEl.value);
  const servicesText = servicesEl.value.trim();
  const perKw = Number(perKwEl.value) || 5;

  if (!placeId && !businessName) {
    showError('Type your business name and pick it from the list.');
    return;
  }
  if (!city) {
    showError('Enter the city or service area you want to rank in.');
    return;
  }
  if (keywords.length === 0) {
    showError('Enter at least one keyword customers use to find you.');
    return;
  }
  if (keywords.length > 10) {
    showError('Please limit the list to 10 keywords.');
    return;
  }

  setLoading(true);
  try {
    const data = await apiFetch<Result>('/tools/category-optimizer', {
      method: 'POST',
      body: {
        businessName,
        city,
        placeId: placeId || null,
        keywords,
        competitorsPerKeyword: perKw,
        regionCode: null,
        languageCode: 'en',
        servicesText: servicesText || null,
      },
    });
    render(data);
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'gbp-category-optimizer' });
  } catch (err) {
    showError(err instanceof ApiClientError ? err.message : 'Something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
});

$('catReset').addEventListener('click', () => {
  results.classList.add('hidden');
  form.reset();
  search.reset();
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function actionBadge(action: string): string {
  const a = ACTIONS[action] ?? { label: action, cls: 'bg-surface text-muted border border-line' };
  return `<span class="inline-flex rounded-md px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${a.cls}">${esc(a.label)}</span>`;
}

function scoreClass(score: number): string {
  return score >= 70 ? 'text-success' : score >= 40 ? 'text-warning' : 'text-danger';
}

function render(d: Result) {
  results.classList.remove('hidden');

  const opp = d.opportunity;
  $('catHeadline').textContent = opp?.headline || 'Category opportunity';
  $('catOppKw').textContent = String(opp?.estimatedKeywordMatchGain ?? 0);
  $('catOppSvc').textContent = String(opp?.estimatedServiceSearchGain ?? 0);
  $('catOppPack').textContent = String(opp?.estimatedLocalPackGapsClosed ?? 0);

  const c = d.client;
  $('catClientName').textContent = c?.businessName ?? '';
  $('catPrimary').textContent = c?.primaryCategory || '—';
  $('catAllCats').innerHTML =
    (c?.allCategories ?? []).map((cat) => `<span class="tag">${esc(cat)}</span>`).join('') ||
    '<span class="text-sm text-muted">No categories are visible on this profile.</span>';
  $('catClientMeta').textContent = c?.reviewCount != null ? `${c.reviewCount} Google reviews were scanned for service mentions.` : '';

  const recs = d.recommendations ?? [];
  $('catRecs').innerHTML = recs.length
    ? recs
        .map((r) => {
          const score = Number.isFinite(r.score) ? Math.round(r.score) : 0;
          return `
      <li class="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2.5">
              ${actionBadge(r.action)}
              <span class="text-lg font-bold">${esc(r.category)}</span>
            </div>
            ${
              r.reasons?.length
                ? `<ul class="mt-2 list-disc space-y-0.5 pl-5 text-sm text-muted">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`
                : ''
            }
          </div>
          <div class="shrink-0 text-right">
            <div class="text-3xl font-extrabold leading-none ${scoreClass(score)}">${score}</div>
            <div class="mt-1 text-xs text-muted">score / 100</div>
          </div>
        </div>
      </li>`;
        })
        .join('')
    : '<li class="text-muted">No category gaps found — your profile already covers what the top competitors use.</li>';

  const comps = d.competitorCategories ?? [];
  $('catCompetitors').innerHTML = comps.length
    ? comps
        .map((cc) => {
          const pct = cc.outOf ? Math.min(100, Math.round((cc.count / cc.outOf) * 100)) : 0;
          return `
      <tr class="border-b border-line last:border-0">
        <td class="py-3 pr-4 font-semibold">${esc(cc.category)}</td>
        <td class="py-3 pr-4">
          <div class="flex items-center gap-3">
            <div class="h-2 w-32 overflow-hidden rounded-full bg-line"><div class="h-full rounded-full bg-primary" style="width:${pct}%"></div></div>
            <span class="whitespace-nowrap text-xs text-muted">${esc(cc.count)}/${esc(cc.outOf)}</span>
          </div>
        </td>
        <td class="py-3 text-xs text-muted">${(cc.sourceKeywords ?? []).map((k) => esc(k)).join(', ')}</td>
      </tr>`;
        })
        .join('')
    : '<tr><td colspan="3" class="py-3 text-muted">No competitor categories were found for these keywords.</td></tr>';

  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
