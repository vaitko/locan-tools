export class ApiClientError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

const BASE = (import.meta.env.PUBLIC_API_BASE as string | undefined)?.replace(/\/$/, '') ?? 'https://api.locan.ai/api';

export const API_BASE = BASE;

interface Init {
  method?: 'GET' | 'POST';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}

const FRIENDLY: Record<string, string> = {
  quota_exceeded: "You've reached today's free limit for this tool. Try again tomorrow.",
  place_not_found: "We couldn't find that business on Google Maps. Try picking it from the suggestions.",
  places_upstream: 'Google Places is not responding right now. Please try again in a moment.',
  llm_upstream: 'The AI service is busy. Please try again in a moment.',
  llm_busy: 'The AI service is busy right now. Please try again in a minute.',
  llm_timeout: 'The AI took too long to answer. Please try again.',
  llm_bad_json: 'The AI returned something we could not read. Please try again.',
  forbidden: 'This request was blocked. Please reload the page and try again.',
};

export async function apiFetch<T>(path: string, init: Init = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), init.timeoutMs ?? 90_000);
  init.signal?.addEventListener('abort', () => controller.abort());
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: init.method ?? 'GET',
      headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      signal: controller.signal,
    });
    const text = await res.text();
    let data: any = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }
    if (!res.ok) {
      const code = data?.code ?? `http_${res.status}`;
      const message = FRIENDLY[code] ?? data?.error ?? `Request failed (${res.status}). Please try again.`;
      throw new ApiClientError(res.status, code, message);
    }
    return data as T;
  } catch (err) {
    if (err instanceof ApiClientError) throw err;
    if ((err as Error).name === 'AbortError') {
      throw new ApiClientError(0, 'timeout', 'This is taking longer than usual. Please try again.');
    }
    throw new ApiClientError(0, 'network', 'Could not reach the Locan API. Check your connection and try again.');
  } finally {
    clearTimeout(timer);
  }
}

export function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function $<T extends HTMLElement = HTMLElement>(id: string): T {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element #${id}`);
  return el as T;
}

export async function copyText(text: string, button?: HTMLElement): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    if (button) {
      const original = button.textContent;
      button.textContent = 'Copied!';
      setTimeout(() => (button.textContent = original), 1500);
    }
  } catch {
    window.prompt('Copy to clipboard:', text);
  }
}

export function newSessionToken(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
