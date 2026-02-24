import { defineCollection, z } from 'astro:content';

const blog = defineCollection({
	type: 'content',
	schema: z.object({
		title: z.string(),
		description: z.string(),
		// ここを z.string() から z.coerce.date() に変更！ これで自動変換されます
		date: z.coerce.date(),
		language: z.string().optional(),
		tags: z.array(z.string()).optional(),
	}),
});

export const collections = { blog };