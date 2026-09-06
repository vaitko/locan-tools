// Binds every `form[data-subscribe]` on the page (EmailCapture, after-use prompt) to POST /subscribe.
import { apiFetch, ApiClientError } from './api';

export function bindSubscribeForms(root: ParentNode = document): void {
  root.querySelectorAll<HTMLFormElement>('form[data-subscribe]').forEach((form) => {
    if (form.dataset.bound) return;
    form.dataset.bound = '1';
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = form.querySelector<HTMLInputElement>('input[type=email]')!;
      const ok = form.querySelector<HTMLElement>('[data-ok]')!;
      const err = form.querySelector<HTMLElement>('[data-err]')!;
      const btn = form.querySelector<HTMLButtonElement>('button[type=submit]')!;
      ok.classList.add('hidden');
      err.classList.add('hidden');
      if (!input.checkValidity()) {
        err.textContent = 'Please enter a valid email address.';
        err.classList.remove('hidden');
        return;
      }
      btn.disabled = true;
      const source = form.dataset.source ?? 'site';
      try {
        const res = await apiFetch<{ ok: boolean; status?: 'pending' | 'confirmed' }>('/subscribe', {
          method: 'POST',
          body: { email: input.value.trim(), source },
        });
        (window as any).gtag?.('event', 'subscribe', { source });
        ok.textContent =
          res.status === 'confirmed'
            ? 'You are already confirmed — updates are on.'
            : 'Check your inbox — click the confirmation link and you are set. One-click unsubscribe in every email.';
        ok.classList.remove('hidden');
        input.value = '';
      } catch (ex) {
        err.textContent = ex instanceof ApiClientError ? ex.message : 'Something went wrong. Please try again.';
        err.classList.remove('hidden');
      } finally {
        btn.disabled = false;
      }
    });
  });
}

bindSubscribeForms();
