export const SITE = {
  name: 'Locan',
  domain: 'locan.ai',
  url: 'https://locan.ai',
  tagline: 'Free Local SEO Tools for Google Search and AI Answers Visibility',
  description:
    'Free local SEO tools for Google Business Profile optimization, local rank checking, schema markup, review links and AI answers visibility. No account, no card, free forever.',
  gaId: 'G-6C881V3KTY',
  hotjarId: 6552436,
  posthog: {
    token: 'phc_pq9uGQYgCBqYALFgKQwfL5KVZKG5QK37q6TgYHEVkaW7',
    apiHost: 'https://b.scrollytelling.ai',
    uiHost: 'https://us.posthog.com',
  },
  social: { x: 'https://x.com/locan_ai' },
  contactEmail: 'hello@locan.ai',
  /** Public repository of the tools (AGPL-3.0). Empty string hides the footer link. */
  sourceUrl: 'https://github.com/vaitko/locan-tools',
  logo: '/images/logo-dark.png',
  ogImage: '/images/og-default.png',
  apiBase: import.meta.env.PUBLIC_API_BASE ?? 'https://api.locan.ai/api',
  showTodos: import.meta.env.PUBLIC_SHOW_TODOS === 'true',
  selfHosted: import.meta.env.PUBLIC_SELF_HOSTED === 'true',
} as const;

export const TRUST_TAGS = [
  'Free forever',
  'No card required. Never.',
  'No account needed',
  'Built by local SEO specialists',
] as const;

export function absUrl(path: string): string {
  return new URL(path, SITE.url).toString();
}
