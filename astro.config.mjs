// astro.config.mjs
import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://globalnexus.io',
  output: 'static',  // Cloudflare Pages static deploy
  compressHTML: true,
  build: {
    inlineStylesheets: 'auto',
  },
});
