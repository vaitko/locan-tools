import { apiFetch, ApiClientError, esc, $, copyText } from '../api';
import type { BusinessSearch } from '../business-search';

interface Check {
  name: string;
  pass: boolean;
  detail: string;
}
interface Place {
  name?: string;
  address?: string;
  website?: string;
  phone?: string;
  url?: string;
  rating?: number;
  reviews?: number;
  photos?: number;
}
interface Ai {
  optimizedDescription?: string | null;
  longTailKeywords: string[];
  googlePostIdeas: string[];
  localFAQ: { q: string; a: string }[];
  reviewReplyTemplates: string[];
  localCitationIdeas: string[];
}
interface Result {
  score: number;
  grade: string;
  summary: string;
  checks: Check[];
  recommendations: string[];
  place: Place | null;
  ai: Ai;
}

const form = $<HTMLFormElement>('gbpForm');
const search = form.querySelector<BusinessSearch & HTMLElement>('business-search')!;
const submit = $<HTMLButtonElement>('gbpSubmit');
const errorEl = $('gbpError');
const results = $('gbpResults');

function setLoading(on: boolean) {
  submit.disabled = on;
  submit.querySelector('[data-spinner]')!.classList.toggle('hidden', !on);
  submit.querySelector<HTMLElement>('[data-label]')!.textContent = on ? 'Analyzing…' : 'Analyze my profile';
}

function showError(msg: string) {
  errorEl.textContent = msg;
  errorEl.classList.remove('hidden');
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.classList.add('hidden');
  const placeId = (form.querySelector<HTMLInputElement>('input[name=biz_placeId]')?.value ?? '').trim();
  const businessName = search.text;
  const gbpUrl = $<HTMLInputElement>('gbpUrl').value.trim();
  if (!placeId && !businessName && !gbpUrl) {
    showError('Type your business name and pick it from the list, or paste a Google Maps link.');
    return;
  }
  setLoading(true);
  try {
    const data = await apiFetch<Result>('/tools/gbp-optimizer', {
      method: 'POST',
      body: { placeId: placeId || null, businessName: businessName || null, gbpUrl: gbpUrl || null },
    });
    render(data);
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'gbp-optimizer' });
  } catch (err) {
    showError(err instanceof ApiClientError ? err.message : 'Something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
});

$('gbpReset').addEventListener('click', () => {
  results.classList.add('hidden');
  search.reset();
  $<HTMLInputElement>('gbpUrl').value = '';
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

document.querySelectorAll<HTMLButtonElement>('[data-copy]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const target = document.querySelector<HTMLElement>(btn.dataset.copy!);
    if (target) copyText(target.textContent ?? '', btn);
  });
});

function list(el: HTMLElement, items: string[], empty: string, cls = '') {
  el.innerHTML = items.length
    ? items.map((t) => `<li class="${cls}">${esc(t.replace(/^\d+[.)]\s*/, ''))}</li>`).join('')
    : `<li class="text-muted">${esc(empty)}</li>`;
}

function render(d: Result) {
  results.classList.remove('hidden');
  const score = Number.isFinite(d.score) ? Math.round(d.score) : 0;
  $('gbpScore').textContent = String(score);
  $('gbpRing').style.setProperty('--pct', String(score));
  $('gbpGrade').textContent = d.grade ? `Grade ${d.grade}.` : '';
  $('gbpSummary').textContent = d.summary ?? '';

  const p = d.place;
  $('gbpName').textContent = p?.name ?? 'Business not found';
  $('gbpAddress').textContent = p?.address ?? '';
  const meta: string[] = [];
  if (p?.rating != null) meta.push(`<span class="tag">★ ${esc(Number(p.rating).toFixed(1))}${p.reviews != null ? ` · ${esc(p.reviews)} reviews` : ''}</span>`);
  if (p?.photos != null) meta.push(`<span class="tag">${esc(p.photos)} photos</span>`);
  if (p?.phone) meta.push(`<span class="tag">${esc(p.phone)}</span>`);
  if (p?.website) meta.push(`<a class="tag tag-primary" href="${esc(p.website)}" target="_blank" rel="nofollow noopener">Website</a>`);
  if (p?.url) meta.push(`<a class="tag tag-primary" href="${esc(p.url)}" target="_blank" rel="nofollow noopener">View on Google Maps</a>`);
  $('gbpMeta').innerHTML = meta.join('');

  $('gbpChecks').innerHTML = d.checks.length
    ? d.checks
        .map(
          (c) => `
      <li class="flex items-start gap-3">
        <span class="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full ${c.pass ? 'bg-success-tint text-success' : 'bg-danger-tint text-danger'}">
          ${c.pass ? '✓' : '✕'}
        </span>
        <span class="text-[15px]"><strong>${esc(c.name)}</strong> <span class="text-muted">— ${esc(c.detail)}</span></span>
      </li>`,
        )
        .join('')
    : '<li class="text-muted">No checks available for this profile.</li>';

  list($('gbpFixes'), d.recommendations ?? [], 'Nothing to fix — nice work.');

  const ai = d.ai;
  const hasAi =
    ai &&
    (ai.optimizedDescription || ai.googlePostIdeas?.length || ai.localFAQ?.length || ai.longTailKeywords?.length || ai.reviewReplyTemplates?.length);
  $('gbpAi').classList.toggle('hidden', !hasAi);
  if (hasAi) {
    $('gbpDescription').textContent = ai.optimizedDescription ?? '';
    list($('gbpPosts'), (ai.googlePostIdeas ?? []).slice(0, 10), 'No post ideas generated.', 'flex gap-2 before:content-["•"] before:text-primary');
    $('gbpKeywords').innerHTML = (ai.longTailKeywords ?? []).map((k) => `<span class="tag tag-primary">${esc(k)}</span>`).join('') || '<span class="text-muted text-sm">None generated.</span>';
    list($('gbpCitations'), (ai.localCitationIdeas ?? []).slice(0, 10), 'No citation ideas generated.');
    $('gbpFaqs').innerHTML =
      (ai.localFAQ ?? [])
        .slice(0, 8)
        .map((f) => `<div><p class="font-bold text-[15px]">${esc(f.q)}</p><p class="mt-1 text-[14.5px] text-muted">${esc(f.a)}</p></div>`)
        .join('') || '<p class="text-muted text-sm">None generated.</p>';
    $('gbpReplies').innerHTML =
      (ai.reviewReplyTemplates ?? [])
        .slice(0, 4)
        .map(
          (t, i) => `
        <div class="rounded-xl bg-surface p-3.5">
          <div class="flex items-start justify-between gap-3">
            <p class="text-[14.5px] leading-relaxed text-ink/90" id="gbpReply${i}">${esc(t)}</p>
            <button type="button" class="btn-ghost btn-sm shrink-0" data-copy-inline="gbpReply${i}">Copy</button>
          </div>
        </div>`,
        )
        .join('') || '<p class="text-muted text-sm">None generated.</p>';
    $('gbpReplies').querySelectorAll<HTMLButtonElement>('[data-copy-inline]').forEach((b) =>
      b.addEventListener('click', () => copyText(document.getElementById(b.dataset.copyInline!)?.textContent ?? '', b)),
    );
  }

  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
