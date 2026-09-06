import { apiFetch, esc, newSessionToken } from './api';

export interface Suggestion {
  placeId: string;
  name: string;
  address: string;
}

export interface BusinessSelectedDetail extends Suggestion {}

/**
 * <business-search name="place" placeholder="…" required>
 * Server-proxied Google Places autocomplete. Emits `business:selected` with {placeId,name,address}
 * and fills hidden inputs `<name>_placeId`, `<name>_name`, `<name>_address`.
 */
class BusinessSearch extends HTMLElement {
  private input!: HTMLInputElement;
  private list!: HTMLUListElement;
  private status!: HTMLElement;
  private hidden: Record<'placeId' | 'name' | 'address', HTMLInputElement> = {} as any;
  private items: Suggestion[] = [];
  private active = -1;
  private timer: number | undefined;
  private session = newSessionToken();
  private abort?: AbortController;
  private selected: Suggestion | null = null;

  connectedCallback() {
    const name = this.getAttribute('name') ?? 'place';
    const placeholder = this.getAttribute('placeholder') ?? 'Type your business name…';
    const required = this.hasAttribute('required');
    const listId = `${name}-listbox`;

    this.innerHTML = `
      <div class="relative">
        <span class="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        </span>
        <input type="text" class="field pl-11 pr-10" role="combobox" aria-autocomplete="list" aria-expanded="false"
               aria-controls="${listId}" autocomplete="off" spellcheck="false" placeholder="${esc(placeholder)}" ${required ? 'required' : ''} />
        <span class="absolute right-3 top-1/2 hidden -translate-y-1/2 text-primary" data-spinner><span class="spinner"></span></span>
        <ul id="${listId}" role="listbox" class="card absolute left-0 right-0 top-full z-30 mt-1 hidden max-h-80 overflow-auto p-1"></ul>
        <input type="hidden" name="${name}_placeId" />
        <input type="hidden" name="${name}_name" />
        <input type="hidden" name="${name}_address" />
        <p class="sr-only" aria-live="polite" data-status></p>
      </div>`;

    this.input = this.querySelector('input[type=text]')!;
    this.list = this.querySelector('ul')!;
    this.status = this.querySelector('[data-status]')!;
    this.hidden.placeId = this.querySelector(`input[name="${name}_placeId"]`)!;
    this.hidden.name = this.querySelector(`input[name="${name}_name"]`)!;
    this.hidden.address = this.querySelector(`input[name="${name}_address"]`)!;

    this.input.addEventListener('input', () => this.onInput());
    this.input.addEventListener('keydown', (e) => this.onKey(e));
    this.input.addEventListener('blur', () => setTimeout(() => this.close(), 120));
    this.input.addEventListener('focus', () => this.items.length && this.open());
  }

  get value(): Suggestion | null {
    return this.selected;
  }

  get text(): string {
    return this.input.value.trim();
  }

  set text(v: string) {
    this.input.value = v;
  }

  reset() {
    this.selected = null;
    this.input.value = '';
    this.hidden.placeId.value = this.hidden.name.value = this.hidden.address.value = '';
    this.session = newSessionToken();
    this.close();
  }

  private onInput() {
    if (this.selected) {
      this.selected = null;
      this.hidden.placeId.value = this.hidden.name.value = this.hidden.address.value = '';
      this.dispatchEvent(new CustomEvent('business:cleared', { bubbles: true }));
    }
    const q = this.input.value.trim();
    window.clearTimeout(this.timer);
    if (q.length < 2) {
      this.items = [];
      this.close();
      return;
    }
    this.timer = window.setTimeout(() => this.search(q), 250);
  }

  private async search(q: string) {
    this.abort?.abort();
    this.abort = new AbortController();
    this.toggleSpinner(true);
    try {
      const params = new URLSearchParams({ q, session: this.session, lang: document.documentElement.lang || 'en' });
      const data = await apiFetch<{ suggestions: Suggestion[] }>(`/places/autocomplete?${params}`, { signal: this.abort.signal, timeoutMs: 12_000 });
      this.items = data.suggestions ?? [];
      this.render();
      this.status.textContent = this.items.length ? `${this.items.length} suggestions available` : 'No matching businesses';
    } catch (err: any) {
      if (err?.code === 'timeout' || err?.name === 'AbortError') return;
      this.items = [];
      this.renderMessage(err?.message ?? 'Search failed. Please try again.');
    } finally {
      this.toggleSpinner(false);
    }
  }

  private render() {
    if (!this.items.length) {
      this.renderMessage('No businesses found. Try adding the city.');
      return;
    }
    this.active = -1;
    this.list.innerHTML = this.items
      .map(
        (s, i) => `
        <li role="option" id="${this.list.id}-opt-${i}" data-index="${i}" aria-selected="false"
            class="flex cursor-pointer items-start gap-3 rounded-lg px-3 py-2.5 hover:bg-surface">
          <span class="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-primary-tint text-primary">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 21s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/></svg>
          </span>
          <span class="min-w-0">
            <span class="block truncate text-[15px] font-bold text-ink">${esc(s.name)}</span>
            <span class="block truncate text-[13px] text-muted">${esc(s.address)}</span>
          </span>
        </li>`,
      )
      .join('');
    this.list.querySelectorAll<HTMLLIElement>('li[data-index]').forEach((li) => {
      li.addEventListener('mousedown', (e) => {
        e.preventDefault();
        this.choose(Number(li.dataset.index));
      });
    });
    this.open();
  }

  private renderMessage(msg: string) {
    this.list.innerHTML = `<li class="px-3 py-2.5 text-sm text-muted">${esc(msg)}</li>`;
    this.open();
  }

  private choose(i: number) {
    const s = this.items[i];
    if (!s) return;
    this.selected = s;
    this.input.value = s.name;
    this.hidden.placeId.value = s.placeId;
    this.hidden.name.value = s.name;
    this.hidden.address.value = s.address;
    this.close();
    this.dispatchEvent(new CustomEvent<BusinessSelectedDetail>('business:selected', { detail: s, bubbles: true }));
    // A new billing session starts after a selection.
    this.session = newSessionToken();
  }

  private onKey(e: KeyboardEvent) {
    const isOpen = !this.list.classList.contains('hidden');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!this.items.length) return;
      e.preventDefault();
      if (!isOpen) this.open();
      this.active = e.key === 'ArrowDown' ? Math.min(this.active + 1, this.items.length - 1) : Math.max(this.active - 1, 0);
      this.list.querySelectorAll<HTMLLIElement>('li[data-index]').forEach((li, i) => {
        const on = i === this.active;
        li.setAttribute('aria-selected', String(on));
        li.classList.toggle('bg-surface', on);
        if (on) li.scrollIntoView({ block: 'nearest' });
      });
      this.input.setAttribute('aria-activedescendant', `${this.list.id}-opt-${this.active}`);
    } else if (e.key === 'Enter') {
      if (isOpen && this.active >= 0) {
        e.preventDefault();
        this.choose(this.active);
      } else if (isOpen && this.items.length === 1) {
        e.preventDefault();
        this.choose(0);
      } else if (isOpen) {
        e.preventDefault();
      }
    } else if (e.key === 'Escape') {
      this.close();
    }
  }

  private open() {
    this.list.classList.remove('hidden');
    this.input.setAttribute('aria-expanded', 'true');
  }

  private close() {
    this.list.classList.add('hidden');
    this.input.setAttribute('aria-expanded', 'false');
    this.input.removeAttribute('aria-activedescendant');
    this.active = -1;
  }

  private toggleSpinner(on: boolean) {
    this.querySelector('[data-spinner]')?.classList.toggle('hidden', !on);
  }
}

if (!customElements.get('business-search')) customElements.define('business-search', BusinessSearch);

export type { BusinessSearch };
