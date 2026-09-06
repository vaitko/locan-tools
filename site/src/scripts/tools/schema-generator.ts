import { apiFetch, ApiClientError, esc, $, copyText, newSessionToken } from '../api';
import type { BusinessSelectedDetail } from '../business-search';

interface Details {
  placeId: string;
  name: string | null;
  address: string | null;
  addressComponents: {
    street: string | null;
    locality: string | null;
    region: string | null;
    postalCode: string | null;
    country: string | null;
  } | null;
  lat: number | null;
  lng: number | null;
  phone: string | null;
  internationalPhone: string | null;
  website: string | null;
  mapsUrl: string | null;
  primaryType: string | null;
  primaryTypeLabel: string | null;
  rating: number | null;
  reviewCount: number | null;
  /** day: 0 = Sunday … 6 = Saturday; close is null for 24-hour days */
  openingHours: { day: number; open: string; close: string | null }[] | null;
  weekdayDescriptions: string[] | null;
}

type Json = Record<string, unknown>;

interface HourRow {
  day: string;
  gday: number;
  closed: HTMLInputElement;
  open: HTMLInputElement;
  close: HTMLInputElement;
}

interface HoursSpec {
  '@type': 'OpeningHoursSpecification';
  dayOfWeek: string[];
  opens: string;
  closes: string;
}

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

/** Google Places primaryType → schema.org LocalBusiness subtype */
const TYPE_MAP: Record<string, string> = {
  plumber: 'Plumber',
  electrician: 'Electrician',
  dentist: 'Dentist',
  doctor: 'Physician',
  restaurant: 'Restaurant',
  cafe: 'CafeOrCoffeeShop',
  bakery: 'Bakery',
  bar: 'BarOrPub',
  hair_salon: 'HairSalon',
  hair_care: 'HairSalon',
  beauty_salon: 'BeautySalon',
  nail_salon: 'NailSalon',
  spa: 'DaySpa',
  lawyer: 'Attorney',
  accounting: 'AccountingService',
  insurance_agency: 'InsuranceAgency',
  real_estate_agency: 'RealEstateAgent',
  travel_agency: 'TravelAgency',
  hotel: 'Hotel',
  lodging: 'Hotel',
  pet_store: 'PetStore',
  veterinary_care: 'VeterinaryCare',
  gym: 'ExerciseGym',
  fitness_center: 'ExerciseGym',
  car_repair: 'AutoRepair',
  car_dealer: 'AutoDealer',
  car_wash: 'AutoWash',
  locksmith: 'Locksmith',
  moving_company: 'MovingCompany',
  roofing_contractor: 'RoofingContractor',
  general_contractor: 'GeneralContractor',
  florist: 'Florist',
  furniture_store: 'FurnitureStore',
  hardware_store: 'HardwareStore',
  jewelry_store: 'JewelryStore',
  clothing_store: 'ClothingStore',
  store: 'Store',
  school: 'School',
  child_care: 'ChildCare',
  physiotherapist: 'Physiotherapy',
  pharmacy: 'Pharmacy',
};

const form = $<HTMLFormElement>('schForm');
const typeSelect = $<HTMLSelectElement>('schType');
const hoursEl = $('schHours');
const jsonEl = $('schJson');
const codeEl = $('schCode');
const validationEl = $('schValidation');
const prefillStatus = $('schPrefillStatus');
const prefillError = $('schPrefillError');

const rows: HourRow[] = Array.from(hoursEl.querySelectorAll<HTMLElement>('[data-day]')).map((el) => ({
  day: el.dataset.day!,
  gday: Number(el.dataset.gday),
  closed: el.querySelector<HTMLInputElement>('[data-closed]')!,
  open: el.querySelector<HTMLInputElement>('[data-open]')!,
  close: el.querySelector<HTMLInputElement>('[data-close]')!,
}));

let currentJson = '{}';
let tracked = false;

const val = (id: string) => $<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(id).value.trim();

function put(obj: Json, key: string, value: string) {
  if (value) obj[key] = value;
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

function syncRow(r: HourRow) {
  r.open.disabled = r.close.disabled = r.closed.checked;
}

/* ---------- opening hours ---------- */

function readHours(warnings: string[]): { day: string; opens: string; closes: string }[] {
  const out: { day: string; opens: string; closes: string }[] = [];
  for (const r of rows) {
    if (r.closed.checked) continue;
    const opens = r.open.value;
    const closes = r.close.value;
    if (!opens && !closes) continue;
    if (!opens || !closes) {
      warnings.push(`${r.day}: add both an opening and a closing time, or tick Closed.`);
      continue;
    }
    out.push({ day: r.day, opens, closes });
  }
  return out;
}

/** Consecutive days with identical hours collapse into one entry. */
function groupHours(entries: { day: string; opens: string; closes: string }[]): HoursSpec[] {
  const groups: HoursSpec[] = [];
  for (const e of entries) {
    const last = groups[groups.length - 1];
    const prevDay = last ? last.dayOfWeek[last.dayOfWeek.length - 1] : undefined;
    const consecutive = prevDay !== undefined && DAYS.indexOf(e.day) === DAYS.indexOf(prevDay) + 1;
    if (last && consecutive && last.opens === e.opens && last.closes === e.closes) {
      last.dayOfWeek.push(e.day);
    } else {
      groups.push({ '@type': 'OpeningHoursSpecification', dayOfWeek: [e.day], opens: e.opens, closes: e.closes });
    }
  }
  return groups;
}

/* ---------- build + render ---------- */

function build(): { data: Json; missing: string[]; warnings: string[] } {
  const missing: string[] = [];
  const warnings: string[] = [];

  const type = val('schType') || 'LocalBusiness';
  const name = val('schName');
  const url = val('schUrl');
  const telephone = val('schTelephone');
  const street = val('schStreet');
  const locality = val('schLocality');
  const country = val('schCountry').toUpperCase();
  const latStr = val('schLat');
  const lngStr = val('schLng');
  const ratingValue = val('schRatingValue');
  const reviewCount = val('schReviewCount');

  if (!name) missing.push('Business name');
  if (!telephone) missing.push('Telephone');
  if (!street) missing.push('Street address');
  if (!locality) missing.push('City / locality');
  if (!country) missing.push('Country code');

  const data: Json = { '@context': 'https://schema.org', '@type': type };
  if (url) data['@id'] = `${url}#localbusiness`;
  put(data, 'name', name);
  put(data, 'description', val('schDescription'));
  put(data, 'url', url);
  put(data, 'telephone', telephone);
  put(data, 'email', val('schEmail'));
  put(data, 'priceRange', val('schPriceRange'));
  put(data, 'image', val('schImage'));
  put(data, 'logo', val('schLogo'));

  const address: Json = { '@type': 'PostalAddress' };
  put(address, 'streetAddress', street);
  put(address, 'addressLocality', locality);
  put(address, 'addressRegion', val('schRegion'));
  put(address, 'postalCode', val('schPostalCode'));
  put(address, 'addressCountry', country);
  if (Object.keys(address).length > 1) data.address = address;

  const lat = Number(latStr);
  const lng = Number(lngStr);
  if (latStr && lngStr && Number.isFinite(lat) && Number.isFinite(lng)) {
    data.geo = { '@type': 'GeoCoordinates', latitude: lat, longitude: lng };
  }

  const hours = groupHours(readHours(warnings));
  if (hours.length) data.openingHoursSpecification = hours;

  const sameAs = val('schSameAs')
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
  if (sameAs.length) data.sameAs = sameAs;

  put(data, 'hasMap', val('schHasMap'));

  const areas = val('schAreaServed')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (areas.length) data.areaServed = areas.map((n) => ({ '@type': 'City', name: n }));

  put(data, 'paymentAccepted', val('schPayment'));

  if (ratingValue) {
    const rating: Json = { '@type': 'AggregateRating', ratingValue: Number(ratingValue) };
    if (reviewCount) rating.reviewCount = Number(reviewCount);
    data.aggregateRating = rating;
  }

  if (country && !/^[A-Z]{2}$/.test(country)) warnings.push('Country must be a 2-letter ISO code, e.g. US, GB, DE.');
  if (url && !/^https?:\/\//i.test(url)) warnings.push('Website URL should start with https://');
  if ((latStr && !lngStr) || (!latStr && lngStr)) warnings.push('Add both latitude and longitude, or leave both empty.');
  if (sameAs.some((u) => !/^https?:\/\//i.test(u))) warnings.push('Every sameAs entry must be a full URL starting with https://');
  if (ratingValue && !reviewCount) warnings.push('AggregateRating needs a reviewCount as well as a ratingValue.');
  if (ratingValue && (Number(ratingValue) < 1 || Number(ratingValue) > 5)) warnings.push('ratingValue must be between 1 and 5.');

  return { data, missing, warnings };
}

function item(kind: 'ok' | 'warn', html: string): string {
  const tone = kind === 'ok' ? 'bg-success-tint text-success' : 'bg-warning-tint text-warning';
  return `<li class="flex items-start gap-2.5">
    <span class="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-extrabold ${tone}" aria-hidden="true">${kind === 'ok' ? '✓' : '!'}</span>
    <span class="text-ink/85">${html}</span>
  </li>`;
}

function render() {
  const { data, missing, warnings } = build();
  currentJson = JSON.stringify(data, null, 2);
  // "</" inside a string would end the script tag on the user's page; JSON allows the escaped form.
  jsonEl.textContent = currentJson.replace(/<\//g, '<\\/');

  const items = missing.map((m) => item('warn', `<strong>${esc(m)}</strong> is required.`));
  if (!missing.length) {
    items.unshift(item('ok', '<strong class="text-success">Looks valid — now test it.</strong> Paste the block into Google’s Rich Results Test or the schema.org validator below.'));
  }
  items.push(...warnings.map((w) => item('warn', esc(w))));
  validationEl.innerHTML = items.join('');

  if (!missing.length && !tracked) {
    tracked = true;
    document.dispatchEvent(new CustomEvent('locan:tool-run')); (window as any).gtag?.('event', 'tool_run', { tool: 'local-business-schema-generator' });
  }
}

/* ---------- prefill from Google ---------- */

let regionCodes: Map<string, string> | null = null;

/** "United States" → "US" via Intl.DisplayNames; returns the input when no match is found. */
function countryCode(name: string | null | undefined): string {
  if (!name) return '';
  if (/^[A-Za-z]{2}$/.test(name)) return name.toUpperCase();
  if (!regionCodes) {
    regionCodes = new Map();
    try {
      const names = new Intl.DisplayNames(['en'], { type: 'region' });
      for (let i = 0; i < 26; i++) {
        for (let j = 0; j < 26; j++) {
          const code = String.fromCharCode(65 + i, 65 + j);
          // Skip deprecated aliases (FX→FR, DD→DE, UK→GB…): they carry the same label as the canonical code.
          if (new Intl.Locale(`und-${code}`).region !== code) continue;
          const label = names.of(code);
          if (label && label !== code) regionCodes.set(label.toLowerCase(), code);
        }
      }
    } catch {
      /* Intl.DisplayNames unavailable — user fixes the country manually */
    }
  }
  return regionCodes.get(name.toLowerCase()) ?? name;
}

function fillHours(periods: NonNullable<Details['openingHours']>) {
  for (const r of rows) {
    r.closed.checked = periods.length > 0;
    r.open.value = '';
    r.close.value = '';
  }
  for (const p of periods) {
    const row = rows.find((r) => r.gday === p.day);
    if (!row || !p.open) continue;
    // A period without a close time means open 24 hours.
    const opens = p.close ? p.open : '00:00';
    const closes = p.close ?? '23:59';
    row.closed.checked = false;
    if (!row.open.value || opens < row.open.value) row.open.value = opens;
    if (!row.close.value || closes > row.close.value) row.close.value = closes;
  }
  rows.forEach(syncRow);
}

function fill(d: Details) {
  const set = (id: string, v: unknown) => {
    $<HTMLInputElement>(id).value = v == null ? '' : String(v);
  };
  const mapped = TYPE_MAP[d.primaryType ?? ''] ?? 'LocalBusiness';
  typeSelect.value = mapped;
  if (typeSelect.value !== mapped) typeSelect.value = 'LocalBusiness';

  set('schName', d.name);
  set('schUrl', d.website);
  set('schTelephone', d.internationalPhone || d.phone);
  const a = d.addressComponents;
  set('schStreet', a?.street);
  set('schLocality', a?.locality);
  set('schRegion', a?.region);
  set('schPostalCode', a?.postalCode);
  set('schCountry', countryCode(a?.country));
  set('schLat', d.lat);
  set('schLng', d.lng);
  set('schHasMap', d.mapsUrl);
  fillHours(d.openingHours ?? []);
}

async function prefill(placeId: string) {
  prefillError.classList.add('hidden');
  prefillStatus.innerHTML = '<span class="spinner text-primary"></span> Fetching your profile from Google…';
  prefillStatus.classList.remove('hidden');
  try {
    const d = await apiFetch<Details>(`/places/details/${encodeURIComponent(placeId)}?session=${newSessionToken()}`, { timeoutMs: 20_000 });
    fill(d);
    render();
    prefillStatus.innerHTML =
      '<span class="font-bold text-success">Prefilled from Google.</span> Check every field — especially the hours and the schema type — before you copy the markup.';
  } catch (err) {
    prefillStatus.classList.add('hidden');
    prefillError.textContent = err instanceof ApiClientError ? err.message : 'Could not load that business. Fill in the form manually.';
    prefillError.classList.remove('hidden');
  }
}

/* ---------- wiring ---------- */

form.addEventListener('business:selected', (e) => {
  const { placeId } = (e as CustomEvent<BusinessSelectedDetail>).detail;
  void prefill(placeId);
});

form.addEventListener('input', render);
form.addEventListener('change', (e) => {
  const target = e.target as HTMLElement;
  if (target.matches('[data-closed]')) {
    const row = rows.find((r) => r.closed === target);
    if (row) syncRow(row);
  }
  render();
});

$('schCopyMonday').addEventListener('click', () => {
  const mon = rows[0];
  if (!mon) return;
  for (const r of rows.slice(1, 5)) {
    r.closed.checked = mon.closed.checked;
    r.open.value = mon.open.value;
    r.close.value = mon.close.value;
    syncRow(r);
  }
  render();
});

$('schCopy').addEventListener('click', (e) => {
  void copyText(codeEl.textContent ?? '', e.currentTarget as HTMLElement);
});

$('schDownload').addEventListener('click', () => {
  const blob = new Blob([currentJson], { type: 'application/ld+json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${slugify(val('schName')) || 'local-business'}-schema.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1_000);
});

rows.forEach(syncRow);
render();
