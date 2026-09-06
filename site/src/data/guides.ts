// Guide lookups that tolerate an empty collection (the open-source mirror ships without the guide content).
import { getCollection } from 'astro:content';

const all = await getCollection('guides', ({ data }) => !data.draft);
const bySlug = new Map(all.map((g) => [g.id, g]));

export const GUIDES = all;
export const hasGuide = (slug: string): boolean => bySlug.has(slug);
export const getGuide = (slug: string) => bySlug.get(slug);
