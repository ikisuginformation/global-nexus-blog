@echo off
chcp 65001
echo ========================================================
echo   Nexus Engine: Auto-Deploy Sequence Initiated
echo ========================================================

:: 1. 作業ディレクトリへ移動
cd /d D:\app

:: 2. AIによる多言語記事の生成（第1層）
echo [Step 1] Generating multilingual content with AI...
python nexus_generator_pro.py

:: 3. 生成された記事をAstro要塞へ装填（第2層）
echo [Step 2] Transferring content to Astro fortress...
:: ※パスは環境に合わせて調整してください
xcopy /s /e /y "content\seo_pages\*" "global-nexus-blog\src\content\blog\"

:: 4. GitHubへ発射 -> Cloudflareが自動検知して公開（第3層）
cd global-nexus-blog
echo [Step 3] Pushing to GitHub for global deployment...
git add .
git commit -m "Auto-update: New AI content generated"
git push origin main

echo ========================================================
echo   MISSION COMPLETE: Site update triggered.
echo   Cloudflare is now building and deploying your site.
echo ========================================================
pause