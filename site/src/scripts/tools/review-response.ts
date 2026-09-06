import { apiFetch, ApiClientError, esc, $, copyText } from '../api';

type Tone = 'professional' | 'friendly' | 'empathetic' | 'concise';

interface Payload {
  businessName: string;
  reviewText: string;
  rating: number;
  tone: Tone;
  language: string;
  reviewerName?: string;
  signOff?: string;
  businessType?: string;
}
interface Reply {
  tone: string;
  text: string;
}
interface Result {
  responses: Reply[];
  tips: string[];
}

const TONES: readonly Tone[] = ['professional', 'friendly', 'empathetic', 'concise'];
const RATING_WORDS = ['Very negative', 'Negative', 'Mixed', 'Positive', 'Very positive'];
const MAX_REVIEW = 2000;
const LABELS = {
  form: { idle: 'Generate 3 replies', busy: 'Writing replies…' },
  regen: { idle: 'Regenerate', busy: 'Regenerating…' },
} as const;
type Trigger = keyof typeof LABELS;

const form = $<HTMLFormElement>('rrForm');
const submit = $<HTMLButtonElement>('rrSubmit');
const regen = $<HTMLButtonElement>('rrRegen');
const errorEl = $('rrError');
const resultsErrorEl = $('rrResultsError');
const results = $('rrResults');
const reviewText = $<HTMLTextAreaElement>('rrReviewText');
const counter = $('rrCount');
const languageSelect = $<HTMLSelectElement>('rrLanguage');
const languageOtherWrap = $('rrLanguageOtherWrap');
const languageOther = $<HTMLInputElement>('rrLanguageOther');
const starsWrap = $('rrStars');
const starIcons = Array.from(starsWrap.querySelectorAll<HTMLElement>('[data-star]'));
const ratingLabel = $('rrRatingLabel');

let lastPayload: Payload | null = null;
let lastResult: Result | null = null;

function value(id: string): string {
  return $<HTMLInputElement>(id).value.trim();
}

function checked(name: string): string {
  return form.querySelector<HTMLInputElement>(`input[name="${name}"]:checked`)?.value ?? '';
}

function selectedRating(): number {
  return Number(checked('rating')) || 0;
}

function paintStars(upTo: number) {
  starIcons.forEach((el, i) => {
    const on = i < upTo;
    el.classList.toggle('text-amber-400', on);
    el.classList.toggle('text-line', !on);
  });
}

starsWrap.addEventListener('change', () => {
  const n = selectedRating();
  paintStars(n);
  ratingLabel.textContent = n ? `${n} star${n === 1 ? '' : 's'} — ${RATING_WORDS[n - 1]}` : 'Pick a rating';
});
starsWrap.querySelectorAll<HTMLLabelElement>('label').forEach((label, i) => {
  label.addEventListener('mouseenter', () => paintStars(i + 1));
});
starsWrap.addEventListener('mouseleave', () => paintStars(selectedRating()));

function updateCounter() {
  const len = reviewText.value.length;
  counter.textContent = `${len} / ${MAX_REVIEW}`;
  counter.classList.toggle('text-warning', len > MAX_REVIEW - 100);
}
reviewText.addEventListener('input', updateCounter);
updateCounter();

function syncLanguageOther() {
  const other = languageSelect.value === 'other';
  languageOtherWrap.classList.toggle('hidden', !other);
  if (other) languageOther.focus();
}
languageSelect.addEventListener('change', syncLanguageOther);

function setLoading(trigger: Trigger, on: boolean) {
  const btn = trigger === 'form' ? submit : regen;
  btn.disabled = on;
  btn.querySelector('[data-spinner]')!.classList.toggle('hidden', !on);
  btn.querySelector<HTMLElement>('[data-label]')!.textContent = on ? LABELS[trigger].busy : LABELS[trigger].idle;
}

function showError(el: HTMLElement, msg: string) {
  el.textContent = msg;
  el.classList.remove('hidden');
}

function buildPayload(): Payload | string {
  const businessName = value('rrBusinessName');
  if (!businessName) return 'Enter your business name.';
  const rating = selectedRating();
  if (!rating) return 'Pick the star rating the reviewer gave.';
  const text = reviewText.value.trim();
  if (text.length < 5) return 'Paste the review text (at least 5 characters).';
  if (text.length > MAX_REVIEW) return `The review is too long — keep it under ${MAX_REVIEW} characters.`;
  const toneRaw = checked('tone') as Tone;
  const tone: Tone = TONES.includes(toneRaw) ? toneRaw : 'professional';
  let language = languageSelect.value || 'auto';
  if (language === 'other') {
    language = languageOther.value.trim();
    if (!language) return 'Type the language you want the reply written in.';
  }
  const payload: Payload = { businessName, reviewText: text, rating, tone, language };
  const reviewerName = value('rrReviewerName');
  const signOff = value('rrSignOff');
  const businessType = value('rrBusinessType');
  if (reviewerName) payload.reviewerName = reviewerName;
  if (signOff) payload.signOff = signOff;
  if (businessType) payload.businessType = businessType;
  return payload;
}

async function generate(payload: Payload, trigger: Trigger) {
  const errTarget = trigger === 'form' ? errorEl : resultsErrorEl;
  errorEl.classList.add('hidden');
  resultsErrorEl.classList.add('hidden');
  setLoading(trigger, true);
  regen.disabled = true;
  try {
    const data = await apiFetch<Result>('/tools/review-response', { method: 'POST', body: payload, timeoutMs: 45_000 });
    lastPayload = payload;
    lastResult = data;
    render(data, payload);
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'ai-review-response-generator' });
  } catch (err) {
    showError(errTarget, err instanceof ApiClientError ? err.message : 'Something went wrong. Please try again.');
  } finally {
    setLoading(trigger, false);
    regen.disabled = false;
  }
}

form.addEventListener('submit', (e) => {
  e.preventDefault();
  errorEl.classList.add('hidden');
  const payload = buildPayload();
  if (typeof payload === 'string') {
    showError(errorEl, payload);
    return;
  }
  void generate(payload, 'form');
});

regen.addEventListener('click', () => {
  if (lastPayload) void generate(lastPayload, 'regen');
});

$('rrReset').addEventListener('click', () => {
  results.classList.add('hidden');
  form.reset();
  lastPayload = null;
  lastResult = null;
  paintStars(0);
  ratingLabel.textContent = 'Pick a rating';
  updateCounter();
  syncLanguageOther();
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function render(d: Result, p: Payload) {
  results.classList.remove('hidden');
  const langNote = p.language === 'auto' ? 'in the language of the review' : `in ${p.language}`;
  $('rrContext').textContent = `${p.tone.charAt(0).toUpperCase()}${p.tone.slice(1)} tone, ${p.rating}-star review of ${p.businessName}, written ${langNote}.`;

  const replies = (d.responses ?? []).slice(0, 3);
  $('rrCards').innerHTML = replies.length
    ? replies
        .map(
          (r, i) => `
      <div class="card flex flex-col p-6">
        <div class="flex items-start justify-between gap-3">
          <span class="tag tag-primary">${esc(r.tone)}</span>
          <button type="button" class="btn-secondary btn-sm shrink-0" data-copy-reply="${i}">Copy</button>
        </div>
        <p class="mt-4 flex-1 whitespace-pre-line text-[15.5px] leading-relaxed text-ink/90">${esc(r.text)}</p>
        <p class="mt-4 text-xs font-semibold text-muted">${esc(wordCount(r.text))} words</p>
      </div>`,
        )
        .join('')
    : '<p class="text-muted lg:col-span-3">No replies were generated. Try regenerating.</p>';
  $('rrCards')
    .querySelectorAll<HTMLButtonElement>('[data-copy-reply]')
    .forEach((btn) =>
      btn.addEventListener('click', () => {
        const reply = lastResult?.responses?.[Number(btn.dataset.copyReply)];
        if (reply) copyText(reply.text, btn);
      }),
    );

  const tips = (d.tips ?? []).filter((t) => typeof t === 'string' && t.trim());
  $('rrTips').innerHTML = tips.length
    ? tips.map((t) => `<li class="flex gap-2 before:text-primary before:content-['•']">${esc(t)}</li>`).join('')
    : '<li class="text-muted">No extra tips for this one — the replies say it all.</li>';

  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
