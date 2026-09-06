import QRCode from 'qrcode';
import { $, copyText } from '../api';
import type { BusinessSelectedDetail } from '../business-search';

/** The parts of <business-search> this module touches (see ../business-search). */
type SearchElement = HTMLElement & { readonly text: string; reset(): void };

const REVIEW_BASE = 'https://search.google.com/local/writereview?placeid=';
const PLACE_ID_RE = /^[A-Za-z0-9_\-+/=]{10,}$/;
const STAR = '#F59E0B';
const FALLBACK_ACCENT = '#3E50F7';

const form = $<HTMLFormElement>('qrForm');
const search = form.querySelector<SearchElement>('business-search')!;
const placeIdInput = $<HTMLInputElement>('qrPlaceId');
const errorEl = $('qrError');
const results = $('qrResults');
const linkInput = $<HTMLInputElement>('qrLink');
const openLink = $<HTMLAnchorElement>('qrOpen');
const qrCanvas = $<HTMLCanvasElement>('qrCanvas');
const poster = $('poster');
const posterQr = $<HTMLImageElement>('pvQr');
const headlineInput = $<HTMLInputElement>('pvHeadlineInput');
const sublineInput = $<HTMLInputElement>('pvSublineInput');
const nameInput = $<HTMLInputElement>('pvNameInput');

let link = '';
let bizName = '';
let tracked = false;

const pageStyle = document.createElement('style');
document.head.appendChild(pageStyle);

/* ---------- helpers ---------- */

function checked(name: string): string {
  return document.querySelector<HTMLInputElement>(`input[name="${name}"]:checked`)?.value ?? FALLBACK_ACCENT;
}

function posterStyle(): 'a4' | 'a6' {
  return checked('posterStyle') === 'a6' ? 'a6' : 'a4';
}

function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
}

function fileSlug(): string {
  return slugify(nameInput.value || bizName) || 'business';
}

function download(href: string, filename: string, revoke = false) {
  const a = document.createElement('a');
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  if (revoke) setTimeout(() => URL.revokeObjectURL(href), 1_000);
}

function showError(msg: string) {
  errorEl.textContent = msg;
  errorEl.classList.remove('hidden');
}

async function qrToCanvas(text: string, width: number, dark: string, canvas = document.createElement('canvas')): Promise<HTMLCanvasElement> {
  await QRCode.toCanvas(canvas, text, { width, margin: 1, color: { dark, light: '#ffffff' } });
  return canvas;
}

/* ---------- QR card ---------- */

async function renderQr() {
  await qrToCanvas(link, 560, checked('qrColor'), qrCanvas);
  // The renderer sets inline width/height to the render size; show it at 280 css px (crisp on retina).
  qrCanvas.style.width = qrCanvas.style.height = '280px';
}

/* ---------- poster preview ---------- */

async function renderPosterQr() {
  const c = await qrToCanvas(link, 512, checked('posterColor'));
  posterQr.src = c.toDataURL('image/png');
}

function updatePosterText() {
  $('pvHeadline').textContent = headlineInput.value.trim();
  $('pvSubline').textContent = sublineInput.value.trim();
  $('pvName').textContent = nameInput.value.trim();
  poster.dataset.style = posterStyle();
  poster.style.setProperty('--accent', checked('posterColor'));
}

/* ---------- poster canvas (1240 × 1754, A-series ratio) ---------- */

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = '';
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (!line || ctx.measureText(test).width <= maxWidth) {
      line = test;
    } else {
      lines.push(line);
      line = w;
    }
  }
  if (line) lines.push(line);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    kept[maxLines - 1] = `${kept[maxLines - 1].replace(/\s*\S*$/, '')}…`;
    return kept;
  }
  return lines;
}

function drawLines(ctx: CanvasRenderingContext2D, lines: string[], x: number, top: number, lineHeight: number) {
  lines.forEach((l, i) => ctx.fillText(l, x, top + (i + 0.5) * lineHeight));
}

function drawStar(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const radius = i % 2 === 0 ? r : r * 0.45;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
}

function roundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  if (typeof ctx.roundRect === 'function') ctx.roundRect(x, y, w, h, r);
  else ctx.rect(x, y, w, h);
}

async function drawPoster(): Promise<HTMLCanvasElement> {
  const W = 1240;
  const H = 1754;
  const a6 = posterStyle() === 'a6';
  const accent = checked('posterColor');
  const headline = headlineInput.value.trim();
  const subline = sublineInput.value.trim();
  const name = nameInput.value.trim();

  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;
  await document.fonts.ready;
  const font = (weight: number, px: number) => `${weight} ${px}px "Nunito Variable", Nunito, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`;

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, W, H);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  // Accent band with the headline.
  const bandH = Math.round(H * 0.25);
  ctx.fillStyle = accent;
  ctx.fillRect(0, 0, W, bandH);
  if (headline) {
    const px = a6 ? 108 : 94;
    ctx.font = font(800, px);
    ctx.fillStyle = '#ffffff';
    const lines = wrapText(ctx, headline, W - 180, 3);
    drawLines(ctx, lines, W / 2, bandH / 2 - (lines.length * px * 1.12) / 2, px * 1.12);
  }

  // Stars.
  let y = bandH + (a6 ? 130 : 120);
  const starR = a6 ? 44 : 38;
  ctx.fillStyle = STAR;
  for (let i = 0; i < 5; i++) drawStar(ctx, W / 2 + (i - 2) * starR * 2.4, y, starR);
  y += starR + (a6 ? 70 : 60);

  // Subline.
  if (subline) {
    const px = a6 ? 58 : 50;
    ctx.font = font(600, px);
    ctx.fillStyle = '#475569';
    const lines = wrapText(ctx, subline, W - 200, 2);
    drawLines(ctx, lines, W / 2, y, px * 1.3);
    y += lines.length * px * 1.3;
  }
  const bodyTop = y;

  // Footer and business name are anchored to the bottom; the QR fills the space between.
  const footerY = H - 96;
  ctx.font = font(600, a6 ? 38 : 34);
  ctx.fillStyle = '#64748B';
  ctx.fillText('Powered by Google reviews', W / 2, footerY);

  let nameTop = footerY - 70;
  if (name) {
    const px = a6 ? 66 : 58;
    ctx.font = font(800, px);
    ctx.fillStyle = '#0F172A';
    const lines = wrapText(ctx, name, W - 200, 2);
    nameTop = footerY - 70 - lines.length * px * 1.2;
    drawLines(ctx, lines, W / 2, nameTop, px * 1.2);
  }

  // QR code in a soft frame.
  const pad = 44;
  const avail = nameTop - bodyTop;
  const qrSize = Math.max(200, Math.min(a6 ? 640 : 600, avail - pad * 2 - 100));
  const qx = (W - qrSize) / 2;
  const qy = bodyTop + (avail - qrSize) / 2;
  ctx.fillStyle = '#ffffff';
  ctx.strokeStyle = '#E6E8F0';
  ctx.lineWidth = 4;
  roundedRect(ctx, qx - pad, qy - pad, qrSize + pad * 2, qrSize + pad * 2, 40);
  ctx.fill();
  ctx.stroke();
  const qr = await qrToCanvas(link, qrSize, accent);
  ctx.drawImage(qr, qx, qy, qrSize, qrSize);

  return canvas;
}

/* ---------- templates ---------- */

function updateTemplates() {
  const who = bizName || 'us';
  let sms = `Thanks for choosing ${bizName}! A quick Google review would mean a lot: ${link}`;
  if (!bizName || sms.length > 160) sms = `Thanks for your visit! A quick Google review would mean a lot: ${link}`;
  $('qrSms').textContent = sms;
  const count = $('qrSmsCount');
  count.textContent = `${sms.length} / 160`;
  count.classList.toggle('text-danger', sms.length > 160);
  count.classList.toggle('text-muted', sms.length <= 160);

  $('qrEmailSubject').textContent = bizName ? `How was your experience with ${bizName}?` : 'How was your experience with us?';
  $('qrEmailBody').textContent =
    `Hi [Name],\n\nThank you for choosing ${who}. Would you take 30 seconds to leave us a Google review? It helps other people find us and tells us what to keep doing.\n\n${link}\n\nThank you,\n${bizName || 'The team'}`;

  $('qrWhatsapp').textContent = `Hi [Name], thanks for choosing ${who}! If you have 30 seconds, we would really appreciate a Google review: ${link} — thank you!`;
}

/* ---------- generate ---------- */

async function generate(placeId: string, name: string) {
  link = REVIEW_BASE + encodeURIComponent(placeId);
  bizName = name.trim();
  linkInput.value = link;
  openLink.href = link;
  if (bizName) nameInput.value = bizName;
  try {
    await Promise.all([renderQr(), renderPosterQr()]);
  } catch {
    showError('Could not draw the QR code in this browser. Try a current version of Chrome, Safari or Firefox.');
    return;
  }
  updatePosterText();
  updateTemplates();
  results.classList.remove('hidden');
  if (!tracked) {
    tracked = true;
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'google-review-qr-code-generator' });
  }
  document.getElementById('tool-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

form.addEventListener('business:selected', (e) => {
  const d = (e as CustomEvent<BusinessSelectedDetail>).detail;
  errorEl.classList.add('hidden');
  placeIdInput.value = '';
  void generate(d.placeId, d.name);
});

form.addEventListener('submit', (e) => {
  e.preventDefault();
  errorEl.classList.add('hidden');
  const manual = placeIdInput.value.trim();
  const selected = form.querySelector<HTMLInputElement>('input[name=biz_placeId]')?.value.trim() ?? '';
  if (manual) {
    if (!PLACE_ID_RE.test(manual)) {
      showError('That does not look like a Google Place ID. Most start with "ChIJ" and contain only letters, digits, "_" and "-".');
      return;
    }
    void generate(manual, search.text);
    return;
  }
  if (selected) {
    void generate(selected, form.querySelector<HTMLInputElement>('input[name=biz_name]')?.value ?? search.text);
    return;
  }
  showError('Pick your business from the suggestions, or paste a Google Place ID.');
});

/* ---------- results wiring ---------- */

results.addEventListener('change', (e) => {
  const t = e.target as HTMLInputElement;
  if (t.name === 'qrColor') void renderQr();
  if (t.name === 'posterColor') {
    updatePosterText();
    void renderPosterQr();
  }
  if (t.name === 'posterStyle') updatePosterText();
});
[headlineInput, sublineInput, nameInput].forEach((el) => el.addEventListener('input', updatePosterText));

results.querySelectorAll<HTMLButtonElement>('[data-copy]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const target = document.querySelector<HTMLElement>(btn.dataset.copy!);
    if (!target) return;
    const text = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement ? target.value : (target.textContent ?? '');
    void copyText(text, btn);
  });
});

$('qrCopyEmail').addEventListener('click', (e) => {
  void copyText(`Subject: ${$('qrEmailSubject').textContent ?? ''}\n\n${$('qrEmailBody').textContent ?? ''}`, e.currentTarget as HTMLElement);
});

linkInput.addEventListener('focus', () => linkInput.select());

$('qrPng').addEventListener('click', async () => {
  const c = await qrToCanvas(link, 1024, checked('qrColor'));
  download(c.toDataURL('image/png'), `google-review-qr-${fileSlug()}.png`);
});

$('qrSvg').addEventListener('click', async () => {
  const svg = await QRCode.toString(link, { type: 'svg', margin: 1, color: { dark: checked('qrColor') } });
  const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
  download(URL.createObjectURL(blob), `google-review-qr-${fileSlug()}.svg`, true);
});

$('qrPosterPng').addEventListener('click', async (e) => {
  const btn = e.currentTarget as HTMLButtonElement;
  btn.disabled = true;
  try {
    const c = await drawPoster();
    download(c.toDataURL('image/png'), `google-review-poster-${posterStyle()}-${fileSlug()}.png`);
  } finally {
    btn.disabled = false;
  }
});

$('qrPrint').addEventListener('click', () => {
  pageStyle.textContent = `@page { size: ${posterStyle() === 'a6' ? 'A6' : 'A4'} portrait; margin: 8mm; }`;
  const holder = document.createElement('div');
  holder.id = 'posterPrint';
  const clone = poster.cloneNode(true) as HTMLElement;
  clone.removeAttribute('id');
  holder.appendChild(clone);
  document.body.appendChild(holder);
  document.documentElement.classList.add('print-poster');
  const cleanup = () => {
    holder.remove();
    document.documentElement.classList.remove('print-poster');
    pageStyle.textContent = '';
    window.removeEventListener('afterprint', cleanup);
  };
  window.addEventListener('afterprint', cleanup);
  window.print();
  // The clone is display:none on screen, so a late cleanup is invisible; this covers browsers without afterprint.
  setTimeout(cleanup, 3_000);
});

$('qrReset').addEventListener('click', () => {
  results.classList.add('hidden');
  search.reset();
  placeIdInput.value = '';
  errorEl.classList.add('hidden');
  document.getElementById('tool')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
