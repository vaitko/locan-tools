import type { PillarId } from './pillars';

export type ToolIcon = 'audit' | 'category' | 'sparkle' | 'grid' | 'code' | 'qr' | 'reply';

export interface ToolFaq {
  q: string;
  a: string;
}

export interface Tool {
  slug: string;
  name: string;
  shortName: string;
  /** one-line value proposition used on cards */
  tagline: string;
  /** meta description (≤160 chars, contains "local SEO") */
  description: string;
  /** hero sub-heading on the tool page */
  intro: string;
  icon: ToolIcon;
  pillar: PillarId;
  /** search intents this page owns */
  keywords: string[];
  /** what a user gets back, shown on cards and the tools index */
  outputs: string[];
  input: string;
  time: string;
  primaryGuide: string;
  relatedGuides: string[];
  relatedTools: string[];
  howItWorks: { title: string; text: string }[];
  limitations: string[];
  faq: ToolFaq[];
  /** true when the tool never calls the API (pure browser) */
  clientOnly?: boolean;
}

export const TOOLS: Tool[] = [
  {
    slug: 'google-business-profile-optimizer',
    name: 'Google Business Profile Optimizer',
    shortName: 'GBP Optimizer',
    tagline: 'Audit your profile in seconds and get a prioritised fix list.',
    description:
      'Free Google Business Profile optimizer: audit your GBP, get a score out of 100 and AI-written fixes. A free local SEO tool — no account, no card.',
    intro:
      'Type your business name, pick it from Google, and get a scored audit of the public profile: website, hours, phone, photos, reviews and category — plus AI suggestions for your description, posts, FAQs and review replies.',
    icon: 'audit',
    pillar: 'gbp',
    keywords: ['gmb optimization tool', 'google business profile optimizer', 'gbp audit tool', 'google business profile audit'],
    outputs: ['Score /100 and grade', 'Pass/fail checks with fixes', 'AI description, post ideas, FAQs, review reply templates'],
    input: 'Business name (or Maps link)',
    time: '~15 seconds',
    primaryGuide: 'how-to-optimize-google-business-profile',
    relatedGuides: [
      'google-business-profile-audit',
      'google-business-profile-checklist',
      'google-business-profile-description',
      'google-business-profile-photos',
      'gmb-ranking-factors',
    ],
    relatedTools: ['gbp-category-optimizer', 'local-rank-checker', 'local-business-ai-visibility-tool'],
    howItWorks: [
      { title: 'Find your profile', text: 'Start typing your business name and pick it from the Google suggestions. No login needed — we read only the public profile.' },
      { title: 'We score the essentials', text: 'Six weighted checks (website, hours, phone, photos, reviews, category) produce a score and grade you can act on today.' },
      { title: 'AI writes the fixes', text: 'Get an optimised description, 10 post ideas, long-tail keywords, local FAQs, review reply templates and citation ideas — all specific to your business and city.' },
    ],
    limitations: [
      'We only see what Google exposes publicly through the Places API; owner-only data (insights, Q&A, services) is not audited.',
      'Photo and review counts are as reported by Google and can lag behind your dashboard.',
      'AI suggestions are drafts. Read them, edit them, and keep only what is true for your business.',
    ],
    faq: [
      { q: 'Is this Google Business Profile optimizer really free?', a: 'Yes — free forever, no account, no credit card. We built it because most GBP audit tools hide the useful part behind a trial.' },
      { q: 'Do I need to log in to Google?', a: 'No. The audit uses public profile data only. Nothing on your profile is changed.' },
      { q: 'What does the optimizer check?', a: 'Website link, opening hours, phone number, photo count, review count and category presence, weighted into a score out of 100, plus AI-written content suggestions.' },
      { q: 'How often should I run it?', a: 'After every meaningful change to your profile and at least once a quarter. Re-run it after adding photos or collecting new reviews to see the score move.' },
      { q: 'Does a better score mean higher rankings?', a: 'A complete profile is necessary but not sufficient. Pair the audit with the Local Rank Checker to see where you actually rank, and the Category Optimizer to fix relevance.' },
    ],
  },
  {
    slug: 'gbp-category-optimizer',
    name: 'GBP Category Optimizer',
    shortName: 'Category Optimizer',
    tagline: 'Find the categories top-ranking competitors use that you don’t.',
    description:
      'Free GBP category optimizer: compare your Google Business Profile categories with the businesses ranking for your keywords. A free local SEO tool.',
    intro:
      'We pull the categories of the businesses ranking for your keywords, compare them with your profile, and score every missing category so you know what to add, what to consider and what to leave alone.',
    icon: 'category',
    pillar: 'gbp',
    keywords: ['gbp category finder', 'gmb category finder tool', 'google business profile categories', 'primary category'],
    outputs: ['Your current categories', 'Competitor category frequency', 'Scored add / consider / avoid list'],
    input: 'Business, city, 2–10 keywords',
    time: '~20 seconds',
    primaryGuide: 'google-business-profile-categories',
    relatedGuides: ['how-to-optimize-google-business-profile', 'gmb-ranking-factors', 'local-pack-ranking', 'google-business-profile-attributes'],
    relatedTools: ['google-business-profile-optimizer', 'local-rank-checker'],
    howItWorks: [
      { title: 'Tell us who you compete with', text: 'Enter your business, your city and the keywords customers actually search for.' },
      { title: 'We read the winners', text: 'For each keyword we look at the businesses Google ranks and collect their primary and secondary categories.' },
      { title: 'Every category gets a score', text: 'Frequency among competitors, keyword match, your services and what customers say in reviews add up to a 0–100 score with an add / consider / avoid verdict.' },
    ],
    limitations: [
      'Google exposes place "types", which map closely — but not perfectly — to the categories you see in the GBP dashboard.',
      'Never add a category for a service you do not offer. The score tells you what competitors do, not what is right for your business.',
      'Results reflect the current results page; rankings shift, so re-run quarterly.',
    ],
    faq: [
      { q: 'Will this change my Google Business Profile?', a: 'No. The tool is read-only. You review the recommendations and apply the ones that are true for your business inside Google Business Profile.' },
      { q: 'How many categories should a profile have?', a: 'One primary category that describes your core service plus every secondary category you genuinely offer — most businesses land on three to six.' },
      { q: 'Why does it say "avoid" for a category competitors use?', a: 'Because we found no evidence in your services or reviews that you offer it, and few competitors use it. Adding categories you cannot back up dilutes relevance.' },
      { q: 'Is the GBP category optimizer free?', a: 'Yes, like every local SEO tool on Locan: free forever, no signup.' },
    ],
  },
  {
    slug: 'local-business-ai-visibility-tool',
    name: 'AI Visibility Checker',
    shortName: 'AI Visibility Checker',
    tagline: 'See whether ChatGPT, Gemini and Perplexity recommend your business.',
    description:
      'Free AI visibility checker for local businesses: find out if ChatGPT, Gemini, Perplexity and Google AI recommend you, who they recommend instead, and why. Free local SEO tool.',
    intro:
      'We simulate 12 real buyer questions across four AI engines and check whether your business is named. You get a visibility score, the competitors AI prefers, the evidence, and a plan to fix it.',
    icon: 'sparkle',
    pillar: 'ai',
    keywords: ['ai visibility checker', 'check if chatgpt recommends my business', 'chatgpt visibility checker', 'ai search visibility local business'],
    outputs: ['AI visibility score /100', 'Per-engine mentions', 'Competitors AI recommends and why', 'Action plan + follow-up chat'],
    input: 'Business name',
    time: '~30–45 seconds',
    primaryGuide: 'ai-search-optimization-local-business',
    relatedGuides: ['how-ai-assistants-recommend-local-businesses', 'google-business-profile-reviews', 'gmb-ranking-factors', 'local-business-schema-markup'],
    relatedTools: ['google-business-profile-optimizer', 'ai-review-response-generator', 'local-rank-checker'],
    howItWorks: [
      { title: 'Pick your business', text: 'We detect your category and city from the Google listing you select.' },
      { title: 'We ask like a customer', text: '12 buyer-intent questions ("best…", "emergency…", "near me", price, booking) are run through ChatGPT-, Gemini-, Perplexity- and Google-AI-style engines.' },
      { title: 'You get evidence, not vibes', text: 'A score, which engines mentioned you, who they recommended instead, and specific actions — then ask follow-up questions in the chat.' },
    ],
    limitations: [
      'Engines are simulated with one underlying model instructed to behave like each assistant, so treat results as a strong directional signal, not a live crawl of each product.',
      'AI answers change daily. Re-run monthly to see the trend.',
      'Scores compare you against the question set for your category and city — a different city or category gives different results.',
    ],
    faq: [
      { q: 'How do you know what ChatGPT recommends?', a: 'We generate realistic local buyer questions for your category and city, run them through AI engine personas, and check whether your business is named in the answers.' },
      { q: 'Why is my business missing from AI answers?', a: 'Usually a thin or inconsistent Google Business Profile, few recent reviews, weak mentions on the wider web, or competitors with clearer category and location signals. The report shows the specific evidence.' },
      { q: 'Is the AI visibility checker free?', a: 'Yes. Free forever, no account. Daily limits per visitor keep it free for everyone.' },
      { q: 'How is this different from a rank checker?', a: 'Rank checkers measure Google Maps positions at a point on the map. This tool measures whether conversational AI assistants name you at all.' },
    ],
  },
  {
    slug: 'local-rank-checker',
    name: 'Local Rank Checker',
    shortName: 'Local Rank Checker',
    tagline: 'A free heat map of your Google Maps ranking across your service area.',
    description:
      'Free local rank checker: see your Google Maps ranking for a keyword on a 3×3 or 5×5 grid around your business. A free local SEO heat map tool — no signup.',
    intro:
      'Local rankings change from street to street. Enter your business and a keyword and we check your position at every point of a grid around your location, so you see where you win, where you vanish, and who takes your place.',
    icon: 'grid',
    pillar: 'rankings',
    keywords: ['local rank checker', 'gmb rank checker free', 'free gmb heat map', 'local seo grid tool', 'local seo map checker', 'check gmb ranking'],
    outputs: ['Grid heat map of positions', 'Average / best / worst rank', 'Share of points in the top 3', 'Competitors that outrank you'],
    input: 'Business + one keyword',
    time: '~10–20 seconds',
    primaryGuide: 'how-to-check-google-maps-ranking',
    relatedGuides: ['how-to-rank-on-google-maps', 'gmb-ranking-factors', 'local-pack-ranking', 'google-business-profile-service-area-business'],
    relatedTools: ['gbp-category-optimizer', 'google-business-profile-optimizer', 'local-business-ai-visibility-tool'],
    howItWorks: [
      { title: 'Choose business, keyword and grid', text: 'Pick a 3×3 or 5×5 grid and how far apart the points are (0.5, 1 or 2 km).' },
      { title: 'We search from every point', text: 'Each grid point runs the keyword through Google Places with that location as the searcher’s position and records where you appear in the top 20.' },
      { title: 'Read the heat map', text: 'Green cells are top-3 positions, amber 4–10, orange 11–20, grey not found. The summary and competitor list tell you where to focus.' },
    ],
    limitations: [
      'Results come from Google Places Text Search with a location bias; they track Google Maps closely but are not a pixel-perfect copy of the Maps app, which also personalises results.',
      'Ranking beyond position 20 is reported as "not found".',
      'A 5×5 grid uses more of your daily free limit than a 3×3.',
    ],
    faq: [
      { q: 'Why do I rank #1 at my address but not 2 km away?', a: 'Proximity is the strongest local ranking signal. The further the searcher is from you (and the closer to a competitor), the harder it is to hold a top-3 spot. The heat map shows exactly where that boundary sits.' },
      { q: 'Is this a Google Maps rank tracker?', a: 'It is a free on-demand checker. Run it whenever you want a snapshot; it does not store history or send reports.' },
      { q: 'What keyword should I check?', a: 'Start with your primary service + city ("emergency plumber austin") and the generic head term ("plumber"). Then test the services you want to grow.' },
      { q: 'Is the local rank checker free?', a: 'Yes — free forever with a fair daily limit per visitor so everyone can use it.' },
    ],
  },
  {
    slug: 'local-business-schema-generator',
    name: 'LocalBusiness Schema Markup Generator',
    shortName: 'Schema Generator',
    tagline: 'Generate valid LocalBusiness JSON-LD — prefilled from your Google profile.',
    description:
      'Free LocalBusiness schema markup generator: create JSON-LD structured data for any local business type, prefilled from Google. Free local SEO tool, no signup.',
    intro:
      'Fill the form or prefill it from your Google Business Profile and get valid JSON-LD for the right schema.org type — address, geo, opening hours, sameAs and more — ready to paste into your site.',
    icon: 'code',
    pillar: 'website',
    keywords: ['local business schema generator', 'localbusiness schema markup', 'json-ld generator local business', 'schema markup generator'],
    outputs: ['Valid JSON-LD script tag', 'Correct LocalBusiness subtype', 'Copy, download and validate links'],
    input: 'Business details (or prefill)',
    time: '~2 minutes',
    primaryGuide: 'local-business-schema-markup',
    relatedGuides: ['how-to-add-schema-markup-to-your-website', 'nap-consistency-local-seo', 'local-seo-checklist', 'google-my-business-seo'],
    relatedTools: ['google-business-profile-optimizer', 'google-review-qr-code-generator'],
    howItWorks: [
      { title: 'Prefill or type', text: 'Search your business to import name, address, phone, website, coordinates and opening hours from Google, or fill the fields yourself.' },
      { title: 'Pick the precise type', text: 'Choose from 45+ schema.org LocalBusiness subtypes (Dentist, Plumber, Restaurant, HairSalon…). The more specific, the better search engines understand you.' },
      { title: 'Copy the JSON-LD', text: 'The preview updates live. Copy the script tag, download it, then validate it with Google’s Rich Results Test or the Schema.org validator.' },
    ],
    limitations: [
      'Structured data helps search engines understand your page; it is not a ranking switch and Google decides whether to show rich results.',
      'Only add an aggregateRating if the reviews are collected and shown on your own website — copying Google review counts violates Google’s guidelines.',
      'Keep the markup in sync when your hours, phone or address change.',
    ],
    faq: [
      { q: 'Where do I paste the schema markup?', a: 'Inside the <head> (or before </body>) of the page that represents your business — usually the homepage or contact page. Our guide covers WordPress, Wix, Squarespace, Shopify and Webflow.' },
      { q: 'Which schema type should I use?', a: 'The most specific LocalBusiness subtype that describes your core service. If none fits, use LocalBusiness itself.' },
      { q: 'Does schema markup improve local rankings?', a: 'Indirectly. It removes ambiguity about who you are and where you operate, supports NAP consistency and can unlock rich results — all of which help Google and AI assistants trust your business.' },
      { q: 'Is the schema generator free?', a: 'Yes. Everything runs in your browser; only the optional Google prefill calls our free API.' },
    ],
    clientOnly: true,
  },
  {
    slug: 'google-review-qr-code-generator',
    name: 'Google Review Link & QR Code Generator',
    shortName: 'Review QR Generator',
    tagline: 'Your direct “leave a review” link, QR code and printable poster in one minute.',
    description:
      'Free Google review link and QR code generator: get your direct review link, a QR code and a printable poster to collect more reviews. Free local SEO tool.',
    intro:
      'Search your business, get the direct Google review link, download a QR code and print a ready-made poster or counter card. No design skills, no account, no cost.',
    icon: 'qr',
    pillar: 'reviews',
    keywords: ['google review link generator', 'google review qr code', 'google review qr code generator', 'leave a review link'],
    outputs: ['Direct Google review URL', 'QR code (PNG / SVG)', 'Printable A4 poster', 'Ask-for-review message templates'],
    input: 'Business name',
    time: '~1 minute',
    primaryGuide: 'google-review-link-and-qr-code',
    relatedGuides: ['google-business-profile-reviews', 'how-to-respond-to-google-reviews', 'google-business-profile-checklist', 'local-seo-checklist'],
    relatedTools: ['ai-review-response-generator', 'google-business-profile-optimizer'],
    howItWorks: [
      { title: 'Find your business', text: 'We turn your Google place ID into the official review link that opens the rating box directly.' },
      { title: 'Style the poster', text: 'Choose a headline, colour and size. Preview updates instantly.' },
      { title: 'Download and print', text: 'Grab the QR as PNG or SVG, download the poster, or print straight from the browser. Copy the SMS / email templates to ask for reviews the right way.' },
    ],
    limitations: [
      'Google place IDs occasionally change (for example after a profile merge). Re-generate the link if a QR stops working.',
      'Google forbids incentivising reviews and "review gating" (only asking happy customers). Ask everyone, offer nothing in return.',
    ],
    faq: [
      { q: 'What is a Google review link?', a: 'A URL of the form search.google.com/local/writereview?placeid=… that opens the review form for your business directly, skipping the search step.' },
      { q: 'Where should I put the QR code?', a: 'Counters, receipts, invoices, table tents, packaging inserts, the back of business cards, thank-you emails and your website footer.' },
      { q: 'Can I ask customers for reviews?', a: 'Yes — Google encourages it. You may not offer incentives, pressure customers or filter who gets asked.' },
      { q: 'Is the QR code generator free?', a: 'Yes, and everything is generated in your browser. Nothing is stored.' },
    ],
    clientOnly: true,
  },
  {
    slug: 'ai-review-response-generator',
    name: 'AI Review Response Generator',
    shortName: 'Review Response Generator',
    tagline: 'Three on-brand replies to any Google review — including the angry ones.',
    description:
      'Free AI review response generator: paste a Google review and get three professional replies in your tone and language, plus handling tips. Free local SEO tool.',
    intro:
      'Paste the review, set the star rating and tone, and get three reply variants that thank, apologise or de-escalate without inventing facts — in the language the review was written in.',
    icon: 'reply',
    pillar: 'reviews',
    keywords: ['ai review response generator', 'google review reply generator', 'respond to negative review generator', 'review response templates'],
    outputs: ['3 reply variants (standard / short / with CTA)', 'Handling tips for this review', 'Any language'],
    input: 'Review text + star rating',
    time: '~5 seconds',
    primaryGuide: 'how-to-respond-to-google-reviews',
    relatedGuides: ['google-business-profile-reviews', 'google-review-link-and-qr-code', 'ai-search-optimization-local-business', 'google-business-profile-suspension'],
    relatedTools: ['google-review-qr-code-generator', 'local-business-ai-visibility-tool'],
    howItWorks: [
      { title: 'Paste the review', text: 'Add the star rating, the reviewer’s first name if you like, and pick a tone: professional, friendly, empathetic or concise.' },
      { title: 'AI drafts three replies', text: 'Each variant acknowledges specifics from the review, never promises what you did not offer, and keeps negative replies calm and offline-oriented.' },
      { title: 'Edit, copy, post', text: 'Copy the one you like into Google Business Profile. Add your own detail — a real reply always beats a perfect template.' },
    ],
    limitations: [
      'Replies are drafts written from the review text alone. Correct anything that does not match what actually happened.',
      'For legal, medical or safety complaints, keep replies short and take the conversation offline.',
    ],
    faq: [
      { q: 'Should I reply to every Google review?', a: 'Yes. Replies signal an active, trustworthy business to customers, to Google and to AI assistants that summarise your reputation.' },
      { q: 'How fast should I respond?', a: 'Within 24–48 hours. Negative reviews first.' },
      { q: 'What should I never write in a reply?', a: 'Never argue, never share private customer details, never offer refunds or discounts publicly, and never copy-paste the same reply to everyone.' },
      { q: 'Is the review response generator free?', a: 'Yes — free forever with a daily limit per visitor.' },
    ],
  },
];

export const TOOL_BY_SLUG: Record<string, Tool> = Object.fromEntries(TOOLS.map((t) => [t.slug, t]));

export function toolUrl(slug: string): string {
  return `/tools/${slug}/`;
}

export function guideUrl(slug: string): string {
  return `/guides/${slug}/`;
}

export function getTool(slug: string): Tool {
  const tool = TOOL_BY_SLUG[slug];
  if (!tool) throw new Error(`Unknown tool slug: ${slug}`);
  return tool;
}
