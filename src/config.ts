// src/content/config.ts
import { defineCollection, z } from 'astro:content';

const posts = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string(),
    description: z.string().max(160),
    pubDate: z.string(),
    updatedDate: z.string().optional(),
    category: z.string(),
    categorySlug: z.string(),
    articleId: z.string(),
    readingMinutes: z.number(),
    hook: z.string(),
    heroImage: z.string().optional(),
    affiliateDisclosure: z.boolean().default(false),
    verdict: z.object({
      tool: z.string(),
      verdict: z.enum(['recommended', 'conditional', 'avoid']),
      summary: z.string(),
      pros: z.array(z.string()),
      cons: z.array(z.string()),
      price: z.string(),
      affiliateSlug: z.string(),
      affiliateLabel: z.string(),
    }).optional(),
    relatedTools: z.array(z.object({
      name: z.string(),
      slug: z.string(),
      label: z.string(),
      category: z.string(),
    })).default([]),
    tags: z.array(z.string()).default([]),
  }),
});

export const collections = { posts };
