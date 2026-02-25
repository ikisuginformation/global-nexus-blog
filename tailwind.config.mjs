/** @type {import('tailwindcss').Config} */
export default {
	content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
	theme: {
		extend: {
			// ここに将来的な「現代アート」用のカスタム設定を追加していきます
			fontFamily: {
				// 将来的にGoogle Fontsなどを導入する際の準備
				sans: ['Inter', 'sans-serif'],
			},
		},
	},
	plugins: [
		// テキストのグラデーションやカードのホバー効果などに必須の公式プラグイン
		require('@tailwindcss/typography'),
	],
}