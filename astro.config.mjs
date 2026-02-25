import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import mdx from '@astrojs/mdx';

// https://astro.build/config
export default defineConfig({
  site: 'https://global-nexus-blog.pages.dev',
  integrations: [tailwind(), mdx()],
  // ▼▼ この3行を追加してツールバーを消す ▼▼
  devToolbar: {
    enabled: false
  }
});