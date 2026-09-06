// @ts-check
import { defineConfig } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://locan.ai',
  trailingSlash: 'always',
  compressHTML: true,
  build: { format: 'directory' },
  integrations: [
    mdx(),
    sitemap({
      filter: (page) => !page.includes('/404'),
      serialize(item) {
        const url = new URL(item.url);
        if (url.pathname === '/') item.priority = 1.0;
        else if (url.pathname.startsWith('/tools/')) item.priority = 0.9;
        else if (url.pathname.startsWith('/guides/')) item.priority = 0.8;
        else item.priority = 0.5;
        return item;
      },
    }),
  ],
  vite: { plugins: [tailwindcss()] },
});
