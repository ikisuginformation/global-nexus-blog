import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
    site: 'https://global-nexus-blog.pages.dev',
    integrations: [
        tailwind(),
        mdx(),
        // Generates /sitemap-index.xml automatically on every build.
        // BaseHead already references this. Without this integration it 404s.
        sitemap({
            // Exclude utility pages from sitemap
            filter: (page) =>
                !page.includes('/404') &&
                !page.includes('/privacy') === false, // include privacy
        }),
    ],
    devToolbar: { enabled: false },
});