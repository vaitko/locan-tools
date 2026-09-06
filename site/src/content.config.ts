import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const pillarIds = ['gbp', 'rankings', 'reviews', 'website', 'ai'] as const;

const guides = defineCollection({
  loader: glob({ pattern: '**/*.mdx', base: './src/content/guides' }),
  schema: z.object({
    title: z.string().min(10).max(120),
    description: z.string().min(50).max(200),
    pillar: z.enum(pillarIds),
    published: z.coerce.date(),
    updated: z.coerce.date(),
    author: z.string().default('Locan Team'),
    /** tool slugs — the first one is the primary CTA */
    relatedTools: z.array(z.string()).default([]),
    /** guide slugs to feature in "Related guides" */
    relatedGuides: z.array(z.string()).default([]),
    faq: z.array(z.object({ q: z.string(), a: z.string() })).default([]),
    /** short label shown on cards, e.g. "Beginner", "Checklist" */
    level: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { guides };
