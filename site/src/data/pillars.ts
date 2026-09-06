export type PillarId = 'gbp' | 'rankings' | 'reviews' | 'website' | 'ai';

export interface Pillar {
  id: PillarId;
  title: string;
  short: string;
  description: string;
  /** slug of the pillar (hub) guide */
  pillarGuide: string;
  /** tool slugs that belong to this pillar */
  tools: string[];
}

export const PILLARS: Record<PillarId, Pillar> = {
  gbp: {
    id: 'gbp',
    title: 'Google Business Profile optimization',
    short: 'Google Business Profile',
    description:
      'Everything that lives on your profile: categories, description, attributes, photos, posts, products and the audit process that ties them together.',
    pillarGuide: 'how-to-optimize-google-business-profile',
    tools: ['google-business-profile-optimizer', 'gbp-category-optimizer'],
  },
  rankings: {
    id: 'rankings',
    title: 'Local rankings & Google Maps',
    short: 'Local rankings',
    description:
      'How the local algorithm ranks businesses, why results change street by street, and how to measure and move your Maps positions.',
    pillarGuide: 'how-to-rank-on-google-maps',
    tools: ['local-rank-checker', 'gbp-category-optimizer'],
  },
  reviews: {
    id: 'reviews',
    title: 'Reviews & reputation',
    short: 'Reviews',
    description:
      'Earning more Google reviews, making it effortless to leave one, and replying in a way that wins the next customer.',
    pillarGuide: 'google-business-profile-reviews',
    tools: ['google-review-qr-code-generator', 'ai-review-response-generator'],
  },
  website: {
    id: 'website',
    title: 'Website & schema markup',
    short: 'Website & schema',
    description:
      'The on-site side of local SEO: LocalBusiness structured data, NAP consistency and the technical checklist that supports your profile.',
    pillarGuide: 'local-business-schema-markup',
    tools: ['local-business-schema-generator'],
  },
  ai: {
    id: 'ai',
    title: 'AI answers visibility',
    short: 'AI visibility',
    description:
      'How ChatGPT, Gemini, Perplexity and Google AI decide which local businesses to recommend — and how to become one of them.',
    pillarGuide: 'ai-search-optimization-local-business',
    tools: ['local-business-ai-visibility-tool'],
  },
};

export const PILLAR_ORDER: PillarId[] = ['gbp', 'rankings', 'reviews', 'website', 'ai'];
