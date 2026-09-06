import { apiFetch, ApiClientError, esc, $ } from '../api';
import type { BusinessSearch, BusinessSelectedDetail } from '../business-search';

type EngineKey = 'chatgpt' | 'gemini' | 'perplexity' | 'googleai';

interface Engine {
  mentions: number;
  queries: number;
  confidence: string;
  avgPosition: number | null;
}
interface Query {
  text: string;
  mentioned: boolean;
  engine: string;
}
interface Competitor {
  name: string;
  score: number;
  reasons: string[];
}
interface Action {
  title: string;
  desc: string;
}
interface Result {
  score: number;
  scoreLabel: string;
  totalMentions: number;
  totalQueries: number;
  failedQueries?: number;
  visibilityRate: number;
  category: string;
  engines: Partial<Record<EngineKey, Engine>>;
  queries: Query[];
  competitors: Competitor[];
  missing: string[];
  actions: Action[];
}
interface ChatReply {
  reply: string;
}
interface Context {
  data: Result;
  businessName: string;
  city: string;
}

const ENGINES: { key: EngineKey; name: string }[] = [
  { key: 'chatgpt', name: 'ChatGPT' },
  { key: 'gemini', name: 'Gemini' },
  { key: 'perplexity', name: 'Perplexity' },
  { key: 'googleai', name: 'Google AI' },
];
const ENGINE_NAME: Record<string, string> = Object.fromEntries(ENGINES.map((e) => [e.key, e.name]));

const LOAD_STEPS = [
  'Identifying business profile…',
  'Detecting category & location…',
  'Generating buyer queries with AI…',
  'Running ChatGPT analysis…',
  'Running Gemini analysis…',
  'Running Perplexity analysis…',
  'Running Google AI analysis…',
  'Analyzing competitor landscape…',
  'Calculating visibility score…',
];
// Legacy pacing ×3 so the steps span ~25 s, roughly how long the analysis takes.
const STEP_DURATIONS = [700, 900, 1000, 1100, 1100, 1000, 1000, 900, 700].map((ms) => ms * 3);

const form = $<HTMLFormElement>('visForm');
const search = form.querySelector<BusinessSearch & HTMLElement>('business-search')!;
const cityEl = $<HTMLInputElement>('visCity');
const submit = $<HTMLButtonElement>('visSubmit');
const errorEl = $('visError');
const loading = $('visLoading');
const results = $('visResults');
const chatMessages = $('visChatMessages');
const chatForm = $<HTMLFormElement>('visChatForm');
const chatInput = $<HTMLInputElement>('visChatInput');
const chatSend = $<HTMLButtonElement>('visChatSend');
const chatError = $('visChatError');

let current: Context | null = null;
let chatPending = false;

function setLoading(on: boolean) {
  submit.disabled = on;
  submit.querySelector('[data-spinner]')!.classList.toggle('hidden', !on);
  submit.querySelector<HTMLElement>('[data-label]')!.textContent = on ? 'Analyzing…' : 'Run free AI visibility check';
}

function showError(msg: string) {
  errorEl.textContent = msg;
  errorEl.classList.remove('hidden');
}

function cityFromAddress(address: string): string {
  const parts = address.split(',').map((p) => p.trim());
  if (parts.length < 2) return '';
  return (parts[parts.length - 2] ?? '').replace(/\s*\d+/g, '').trim();
}

search.addEventListener('business:selected', (e) => {
  const { address } = (e as CustomEvent<BusinessSelectedDetail>).detail;
  const city = cityFromAddress(address);
  if (city) cityEl.value = city;
});

function runLoadingAnim(): { done: Promise<void>; cancel: () => void } {
  const steps = $('visLoadSteps');
  const bar = $('visProgressBar');
  const progress = $('visProgress');
  steps.innerHTML = '';
  bar.style.width = '0%';
  progress.setAttribute('aria-valuenow', '0');
  const timers: number[] = [];
  const done = new Promise<void>((resolve) => {
    let elapsed = 0;
    LOAD_STEPS.forEach((step, i) => {
      elapsed += STEP_DURATIONS[i] ?? 0;
      timers.push(
        window.setTimeout(() => {
          const li = document.createElement('li');
          li.className = 'flex items-center gap-3 opacity-0 transition-opacity duration-300';
          li.innerHTML = `<span class="grid size-5 shrink-0 place-items-center rounded-full bg-success-tint text-[11px] font-bold text-success">✓</span><span class="text-ink/80">${esc(step)}</span>`;
          steps.appendChild(li);
          requestAnimationFrame(() => li.classList.remove('opacity-0'));
          const pct = Math.round(((i + 1) / LOAD_STEPS.length) * 100);
          bar.style.width = `${pct}%`;
          progress.setAttribute('aria-valuenow', String(pct));
          if (i === LOAD_STEPS.length - 1) timers.push(window.setTimeout(resolve, 500));
        }, elapsed),
      );
    });
  });
  return { done, cancel: () => timers.forEach((t) => window.clearTimeout(t)) };
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  errorEl.classList.add('hidden');
  const businessName = ((search.value?.name || search.text).split(',')[0] ?? '').trim();
  const city = cityEl.value.trim();
  if (!businessName) {
    showError('Type your business name and pick it from the list.');
    return;
  }
  if (!city) {
    showError('Enter the city your customers search in.');
    return;
  }

  setLoading(true);
  results.classList.add('hidden');
  loading.classList.remove('hidden');
  $('visLoadTitle').textContent = `Analyzing “${businessName}” in ${city}…`;
  $('visLoadSub').textContent = 'Detecting category · Running AI queries across 4 engines';
  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const anim = runLoadingAnim();
  let pending = true;
  anim.done.then(() => {
    if (pending) $('visLoadSub').textContent = 'Almost there — waiting for the last engine to answer…';
  });
  try {
    const [data] = await Promise.all([
      apiFetch<Result>('/tools/ai-visibility', { method: 'POST', body: { businessName, city, category: '' }, timeoutMs: 90_000 }),
      anim.done,
    ]);
    pending = false;
    current = { data, businessName, city };
    render(data, businessName);
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'local-business-ai-visibility-tool' });
  } catch (err) {
    pending = false;
    anim.cancel();
    loading.classList.add('hidden');
    showError(err instanceof ApiClientError ? err.message : 'Something went wrong. Please try again.');
    document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } finally {
    setLoading(false);
  }
});

$('visReset').addEventListener('click', () => {
  current = null;
  results.classList.add('hidden');
  loading.classList.add('hidden');
  form.reset();
  search.reset();
  resetChat();
  $('visScore').textContent = '–';
  $('visRing').style.setProperty('--pct', '0');
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function toneTag(score: number): string {
  return score >= 60
    ? 'border-transparent bg-success-tint text-success'
    : score >= 40
      ? 'border-transparent bg-warning-tint text-warning'
      : 'border-transparent bg-danger-tint text-danger';
}

function toneText(score: number): string {
  return score >= 60 ? 'text-success' : score >= 40 ? 'text-warning' : 'text-danger';
}

function joinList(items: string[]): string {
  return items.length <= 1 ? (items[0] ?? '') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

function render(d: Result, businessName: string) {
  loading.classList.add('hidden');
  results.classList.remove('hidden');

  const score = Number.isFinite(d.score) ? Math.max(0, Math.min(100, Math.round(d.score))) : 0;
  const total = d.totalQueries || 12;
  const mentions = d.totalMentions ?? 0;

  $('visTitle').textContent = `AI Visibility Report for ${businessName}`;
  const failed = d.failedQueries ?? 0;
  $('visSubline').textContent =
    `Based on ${total} simulated buyer conversations across 4 AI engines` +
    (failed ? ` (${failed} of ${total + failed} could not be completed and were left out)` : '');
  $('visScore').textContent = String(score);
  $('visRing').style.setProperty('--pct', String(score));
  const label = $('visLabel');
  label.textContent = d.scoreLabel || (score >= 60 ? 'Good' : score >= 40 ? 'Below average' : 'Poor');
  label.className = `tag ${toneTag(score)}`;
  $('visScoreDesc').textContent = `Your business was mentioned in ${mentions} of ${total} answers.`;
  $('visMentions').textContent = String(mentions);
  $('visQueriesCount').textContent = String(total);
  const rate = $('visRate');
  rate.textContent = `${d.visibilityRate ?? Math.round((mentions / total) * 100)}%`;
  rate.className = `text-xl font-extrabold ${toneText(score)}`;

  $('visEngines').innerHTML = ENGINES.map(({ key, name }) => {
    const e: Engine = d.engines?.[key] ?? { mentions: 0, queries: 3, confidence: 'Low', avgPosition: null };
    const hit = e.mentions > 0;
    return `
      <div class="rounded-xl border p-4 ${hit ? 'border-success/30 bg-success-tint/60' : 'border-line bg-surface'}">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-bold">${esc(name)}</span>
          <span class="grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold ${hit ? 'bg-success text-white' : 'bg-line text-muted'}">${hit ? '✓' : '✕'}</span>
        </div>
        <div class="mt-3 text-2xl font-extrabold leading-none ${hit ? 'text-success' : 'text-ink'}">${esc(e.mentions)}<span class="text-sm font-semibold text-muted">/${esc(e.queries)}</span></div>
        <div class="mt-1 text-xs text-muted">${hit ? `Mentioned · avg. position #${esc(e.avgPosition ?? '?')}` : 'Not mentioned'}</div>
        <div class="mt-2 text-xs text-muted">Confidence: <span class="font-semibold text-ink/80">${esc(e.confidence)}</span></div>
      </div>`;
  }).join('');

  const missing = d.missing ?? [];
  $('visMissing').innerHTML = missing.length
    ? missing
        .map(
          (m) =>
            `<li class="flex items-start gap-3"><span class="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-warning-tint text-xs font-bold text-warning">!</span><span>${esc(m)}</span></li>`,
        )
        .join('')
    : '<li class="text-muted">No obvious gaps — the assistants named you consistently.</li>';

  const competitors = d.competitors ?? [];
  $('visCompetitors').innerHTML = competitors.length
    ? competitors
        .map((c) => {
          const pct = Math.max(0, Math.min(100, Math.round(Number(c.score) || 0)));
          return `
      <div class="rounded-xl border border-line bg-surface p-4">
        <div class="flex items-center justify-between gap-3">
          <span class="truncate text-[15px] font-bold">${esc(c.name)}</span>
          <span class="shrink-0 text-sm font-extrabold text-primary">${pct}%</span>
        </div>
        <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-line"><div class="h-full rounded-full bg-primary" style="width:${pct}%"></div></div>
        ${
          c.reasons?.length
            ? `<ul class="mt-3 space-y-1.5 text-xs text-muted">${c.reasons.map((r) => `<li class="flex gap-2"><span class="text-success">✓</span><span>${esc(r)}</span></li>`).join('')}</ul>`
            : ''
        }
      </div>`;
        })
        .join('')
    : '<p class="text-muted sm:col-span-2">No competitor data was found for this location.</p>';

  const actions = d.actions ?? [];
  $('visActions').innerHTML = actions.length
    ? actions
        .map(
          (a, i) => `
      <li class="flex gap-4 rounded-xl border border-line bg-surface p-4">
        <span class="grid size-7 shrink-0 place-items-center rounded-full bg-primary text-xs font-extrabold text-white">${i + 1}</span>
        <div>
          <p class="text-[15px] font-bold">${esc(a.title)}</p>
          ${a.desc ? `<p class="mt-0.5 text-sm text-muted">${esc(a.desc)}</p>` : ''}
        </div>
      </li>`,
        )
        .join('')
    : '<li class="text-muted">No actions were generated.</li>';

  const queries = d.queries ?? [];
  $('visQueries').innerHTML = queries.length
    ? queries
        .map(
          (q) => `
      <li class="flex items-center justify-between gap-3 py-2.5">
        <span class="flex items-start gap-3 text-[15px]">
          <span class="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-bold ${q.mentioned ? 'bg-success-tint text-success' : 'bg-danger-tint text-danger'}">${q.mentioned ? '✓' : '✕'}</span>
          <span class="${q.mentioned ? '' : 'text-ink/75'}">${esc(q.text)}</span>
        </span>
        <span class="tag shrink-0">${esc(ENGINE_NAME[q.engine] ?? q.engine)}</span>
      </li>`,
        )
        .join('')
    : '<li class="py-2 text-muted">No queries available.</li>';

  resetChat();
  const named = ENGINES.filter((e) => (d.engines?.[e.key]?.mentions ?? 0) > 0).map((e) => e.name);
  const silent = ENGINES.filter((e) => (d.engines?.[e.key]?.mentions ?? 0) === 0).map((e) => e.name);
  let intro: string;
  if (mentions === 0) {
    intro = `Analysis done. Score: ${score}/100. None of the four assistants named your business for the questions we tested. Want me to explain the main reasons?`;
  } else if (named.length && silent.length) {
    intro = `Analysis done. Score: ${score}/100. You appear on ${joinList(named)}, but ${joinList(silent)} ${silent.length > 1 ? "don't" : "doesn't"} mention you. Want me to explain why?`;
  } else {
    intro = `Analysis complete. Score: ${score}/100. You appeared in ${mentions} of ${total} answers. Ask me anything about the results.`;
  }
  addBubble('assistant', intro);

  const topCompetitor = competitors[0]?.name;
  const suggestions = [
    topCompetitor ? `Why does ${topCompetitor} outrank me?` : 'Why am I not appearing in AI answers?',
    'What pages should I create first?',
    'What review keywords am I missing?',
    'How do I rank for "near me" searches?',
  ];
  const qs = $('visChatQs');
  qs.innerHTML = suggestions
    .map((q) => `<button type="button" class="tag cursor-pointer hover:border-primary hover:text-primary" data-q="${esc(q)}">${esc(q)}</button>`)
    .join('');
  qs.querySelectorAll<HTMLButtonElement>('button[data-q]').forEach((b) =>
    b.addEventListener('click', () => {
      b.remove();
      void sendChat(b.dataset.q ?? '');
    }),
  );

  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function addBubble(role: 'user' | 'assistant', text: string): HTMLElement {
  const div = document.createElement('div');
  div.className =
    role === 'user'
      ? 'ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[14.5px] text-white'
      : 'mr-auto max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-bl-md border border-line bg-white px-4 py-2.5 text-[14.5px] leading-relaxed text-ink/90';
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function resetChat() {
  chatMessages.innerHTML = '';
  $('visChatQs').innerHTML = '';
  chatError.classList.add('hidden');
  chatInput.value = '';
}

async function sendChat(message: string) {
  const text = message.trim();
  if (!text || chatPending || !current) return;
  chatError.classList.add('hidden');
  chatPending = true;
  chatSend.disabled = true;
  chatMessages.setAttribute('aria-busy', 'true');
  addBubble('user', text);
  const typing = addBubble('assistant', '…');
  typing.classList.add('animate-pulse', 'text-muted');

  const { data, businessName, city } = current;
  try {
    const res = await apiFetch<ChatReply>('/tools/ai-visibility/chat', {
      method: 'POST',
      body: {
        message: text,
        businessName,
        city,
        category: data.category ?? '',
        score: Math.round(data.score ?? 0),
        topCompetitor: data.competitors?.[0]?.name ?? '',
        missing: (data.missing ?? []).slice(0, 10),
        actions: (data.actions ?? []).slice(0, 10),
      },
      timeoutMs: 60_000,
    });
    typing.remove();
    addBubble('assistant', res.reply || 'I could not process that. Please try again.');
  } catch (err) {
    typing.remove();
    chatError.textContent = err instanceof ApiClientError ? err.message : 'Chat is unavailable right now. Please try again.';
    chatError.classList.remove('hidden');
  } finally {
    chatPending = false;
    chatSend.disabled = false;
    chatMessages.removeAttribute('aria-busy');
  }
}

chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = chatInput.value;
  chatInput.value = '';
  void sendChat(text);
});
