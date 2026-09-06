// Optional-email gate for every tool: intercepts the tool form's submit; if no email was given and the visitor
// hasn't already decided, asks once ("run without email?"). With an email, subscribes (double opt-in) and lets
// the run proceed. Decisions persist in localStorage so nobody is nagged twice.
import { apiFetch } from './api';

const KEY = 'locan-email-optin'; // { state: 'subscribed' | 'skipped', email?: string, at: number }
const TTL = 90 * 24 * 60 * 60 * 1000;

type State = 'subscribed' | 'skipped' | null;

function read(): { state: State; email?: string } {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { state: null };
    const v = JSON.parse(raw);
    if (!v?.at || Date.now() - v.at > TTL) return { state: null };
    return { state: v.state ?? null, email: v.email };
  } catch {
    return { state: null };
  }
}

function save(state: State, email?: string): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ state, email, at: Date.now() }));
  } catch {
    /* private mode */
  }
}

export function installEmailGate() {
  const box = document.querySelector<HTMLElement>('[data-email-optin]');
  const form = document.querySelector<HTMLFormElement>('#tool form');
  if (!box || !form) return { state: () => read().state };

  const input = box.querySelector<HTMLInputElement>('[data-optin-email]')!;
  const ok = box.querySelector<HTMLElement>('[data-optin-ok]')!;
  const gate = box.querySelector<HTMLElement>('[data-optin-gate]')!;
  const addBtn = box.querySelector<HTMLButtonElement>('[data-optin-add]')!;
  const skipBtn = box.querySelector<HTMLButtonElement>('[data-optin-skip]')!;
  const source = box.dataset.source ?? 'tool';

  const saved = read();
  if (saved.state === 'subscribed' && saved.email) {
    input.value = saved.email;
    ok.textContent = 'Updates for this email are on — check your inbox if you have not confirmed yet.';
    ok.classList.remove('hidden');
  }

  let allowNext = false; // set when the visitor confirmed "continue without email" (or subscribed)

  async function subscribe(email: string): Promise<void> {
    try {
      const res = await apiFetch<{ ok: boolean; status: 'pending' | 'confirmed' }>('/subscribe', {
        method: 'POST',
        body: { email, source },
      });
      ok.textContent =
        res.status === 'confirmed'
          ? 'You are already confirmed — updates are on.'
          : 'Check your inbox — click the confirmation link and you are set.';
      ok.classList.remove('hidden');
      save('subscribed', email);
      (window as any).gtag?.('event', 'subscribe', { source });
    } catch {
      // Never block the tool because the subscription failed.
    }
  }

  form.addEventListener(
    'submit',
    (e) => {
      if (allowNext) {
        allowNext = false;
        return; // let the tool's own handler run
      }
      const email = input.value.trim();
      if (email) {
        if (!input.checkValidity()) {
          e.preventDefault();
          e.stopImmediatePropagation();
          input.focus();
          input.reportValidity();
          return;
        }
        const current = read();
        if (!(current.state === 'subscribed' && current.email === email)) void subscribe(email);
        return; // proceed with the run
      }
      if (read().state === 'skipped') return; // decided earlier: run without email
      e.preventDefault();
      e.stopImmediatePropagation();
      gate.classList.remove('hidden');
      gate.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    },
    true,
  );

  addBtn.addEventListener('click', () => {
    gate.classList.add('hidden');
    input.focus();
  });
  skipBtn.addEventListener('click', () => {
    save('skipped');
    gate.classList.add('hidden');
    allowNext = true;
    form.requestSubmit();
  });
  input.addEventListener('input', () => {
    if (input.value.trim()) gate.classList.add('hidden');
  });

  return { state: () => read().state };
}
