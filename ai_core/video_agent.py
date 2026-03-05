# ai_core/video_agent.py
#
# VideoAgent — 記事から縦型ショート動画を自動生成
#
# 依存ライブラリのインストール:
#   pip install moviepy pillow numpy
#
# 生成される動画:
#   - 解像度: 1080x1920 (9:16 縦型)
#   - 長さ: 50〜58秒 (YouTube Shorts / TikTok 対応)
#   - 形式: MP4
#   - 構成: タイトルスライド → ポイント3〜5枚 → CTA スライド
#
# BGMについて:
#   - ai_core/assets/bgm.mp3 に著作権フリーのBGMを置く
#   - なければ無音で生成される
#   - フリーBGM推薦: https://pixabay.com/music/

import os
import json
import textwrap
import requests
from pathlib import Path
from .config import OLLAMA_HOST, OLLAMA_MODEL, BASE_DIR
from .models import ArticleState

# ── 動画設定 ──────────────────────────────────────────────
VIDEO_W = 1080
VIDEO_H = 1920
FPS = 30
SLIDE_DURATION = 4.5   # 各スライドの表示秒数
FADE_DURATION = 0.4    # フェードイン/アウト秒数
BGM_PATH = os.path.join(BASE_DIR, "ai_core", "assets", "bgm.mp3")
OUTPUT_DIR = os.path.join(BASE_DIR, "ai_core", "video_output")

# ── カラーパレット (Global Nexus ブランド) ────────────────
COLORS = {
    "bg":      (242, 237, 227),   # --paper
    "deep":    (28,  23,  16),    # --deep
    "moss":    (80,  104, 69),    # --moss
    "silt":    (120, 110, 95),    # --silt
    "pale":    (180, 168, 150),   # --pale
    "white":   (255, 255, 255),
}

# フォントパス (システムにある等幅・セリフフォントを使う)
# Windows: C:/Windows/Fonts/
# Mac:     /Library/Fonts/
FONT_SERIF = _find_font([
    "C:/Windows/Fonts/georgia.ttf",
    "C:/Windows/Fonts/Georgia.ttf",
    "/Library/Fonts/Georgia.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSerif.ttf",
])
FONT_MONO = _find_font([
    "C:/Windows/Fonts/cour.ttf",           # Courier New
    "C:/Windows/Fonts/consola.ttf",        # Consolas
    "/Library/Fonts/Courier New.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
])


def _find_font(paths: list) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


class VideoAgent:
    def __init__(self):
        self.host  = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ─────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────

    def generate_video(self, state: ArticleState) -> str | None:
        """
        ArticleState から縦型ショート動画を生成する。
        Returns: 生成された MP4 ファイルのパス、または None（失敗時）
        """
        print(f"\n🎬 [VideoAgent] 動画生成開始: {state.title[:50]}")

        # 1. スクリプト生成
        script = self._generate_script(state)
        if not script:
            print("   [VideoAgent] スクリプト生成失敗")
            return None

        # 2. 動画生成
        output_path = self._render_video(script, state)
        if output_path:
            print(f"   [VideoAgent] ✅ 動画生成完了: {output_path}")
        return output_path

    # ─────────────────────────────────────────────────────
    # スクリプト生成 (Ollama)
    # ─────────────────────────────────────────────────────

    def _generate_script(self, state: ArticleState) -> dict | None:
        """
        記事からショート動画用スクリプトを生成。

        Returns dict:
        {
            "hook":   "冒頭フック (1文, 衝撃的な事実)",
            "points": ["ポイント1", "ポイント2", "ポイント3"],  // 3〜5個
            "cta":    "CTA文 (1文)",
            "caption": "SNS投稿用キャプション (150字以内)",
            "hashtags": ["#tag1", "#tag2", ...]  // 5〜8個
        }
        """
        lang_instruction = {
            "ja": "日本語で",
            "en": "in English",
            "es": "en español",
        }.get(state.language, "in English")

        prompt = f"""You are a short-form video scriptwriter. 
Create a 50-second video script {lang_instruction} from this article.

Article title: {state.title}
Article summary: {state.description}
Key content (first 600 chars): {state.content_markdown[:600]}

RULES:
- hook: 1 sentence. Must be a shocking fact or counterintuitive claim. No "Hey guys".
- points: 3 to 5 bullet points. Each under 12 words. Concrete facts only.
- cta: 1 sentence. Direct, no "like and subscribe".
- caption: Under 150 chars for social media post.
- hashtags: 6 relevant hashtags.

OUTPUT: JSON only.
{{
  "hook": "...",
  "points": ["...", "...", "..."],
  "cta": "...",
  "caption": "...",
  "hashtags": ["#...", "#..."]
}}"""

        try:
            res = requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": "json",
                    "stream": False,
                },
                timeout=60,
            )
            content = res.json()["message"]["content"].strip()
            for fence in ("```json", "```"):
                if content.startswith(fence):
                    content = content[len(fence):]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except Exception as e:
            print(f"   [VideoAgent] スクリプト生成エラー: {e}")
            return None

    # ─────────────────────────────────────────────────────
    # 動画レンダリング (MoviePy + Pillow)
    # ─────────────────────────────────────────────────────

    def _render_video(self, script: dict, state: ArticleState) -> str | None:
        try:
            from moviepy.editor import (
                ImageClip, concatenate_videoclips, AudioFileClip,
                CompositeVideoClip, ColorClip
            )
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
        except ImportError:
            print("   [VideoAgent] ❌ moviepy/pillow が未インストール")
            print("   インストール: pip install moviepy pillow numpy")
            return None

        clips = []

        # ── スライド1: フック ──────────────────────────────
        clips.append(self._make_slide(
            text=script["hook"],
            style="hook",
            duration=SLIDE_DURATION + 1.0,
        ))

        # ── スライド2〜N: ポイント ─────────────────────────
        for i, point in enumerate(script["points"][:5]):
            clips.append(self._make_slide(
                text=point,
                style="point",
                number=i + 1,
                duration=SLIDE_DURATION,
            ))

        # ── 最終スライド: CTA ─────────────────────────────
        clips.append(self._make_slide(
            text=script["cta"],
            style="cta",
            site="global-nexus-blog.pages.dev",
            duration=SLIDE_DURATION + 0.5,
        ))

        # ── 動画結合 ──────────────────────────────────────
        from moviepy.editor import concatenate_videoclips
        final = concatenate_videoclips(clips, method="compose")

        # ── BGM追加 ───────────────────────────────────────
        if os.path.exists(BGM_PATH):
            try:
                from moviepy.editor import AudioFileClip
                audio = AudioFileClip(BGM_PATH).subclip(0, final.duration)
                audio = audio.volumex(0.3)  # BGMは30%音量
                final = final.set_audio(audio)
            except Exception:
                pass  # BGMなしで続行

        # ── ファイル保存 ───────────────────────────────────
        from .orchestrator import Orchestrator
        slug = Orchestrator().slugify(state.title)
        output_path = os.path.join(OUTPUT_DIR, f"{state.language}_{slug}.mp4")

        final.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile="/tmp/temp_audio.m4a",
            remove_temp=True,
            logger=None,  # プログレスバーを非表示
        )

        # スクリプトもJSONで保存（YouTube投稿時に使用）
        script["title"] = state.title
        script["language"] = state.language
        script_path = output_path.replace(".mp4", "_script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump(script, f, ensure_ascii=False, indent=2)

        return output_path

    # ─────────────────────────────────────────────────────
    # スライド画像生成
    # ─────────────────────────────────────────────────────

    def _make_slide(
        self,
        text: str,
        style: str,          # "hook" | "point" | "cta"
        number: int = 0,
        site: str = "",
        duration: float = SLIDE_DURATION,
    ):
        """PIL で 1080x1920 のスライド画像を作り ImageClip として返す"""
        try:
            from moviepy.editor import ImageClip
            from PIL import Image, ImageDraw, ImageFont
            import numpy as np
        except ImportError:
            return None

        img = Image.new("RGB", (VIDEO_W, VIDEO_H), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        # ── 上部アクセントライン ──────────────────────────
        draw.rectangle([(0, 0), (VIDEO_W, 8)], fill=COLORS["moss"])

        # ── GN ロゴ ──────────────────────────────────────
        logo_font_size = 28
        try:
            logo_font = ImageFont.truetype(FONT_MONO, logo_font_size) if FONT_MONO else ImageFont.load_default()
        except Exception:
            logo_font = ImageFont.load_default()
        draw.text((60, 60), "GLOBAL NEXUS", font=logo_font, fill=COLORS["pale"])

        # ── スタイル別レイアウト ──────────────────────────
        if style == "hook":
            self._draw_hook(draw, img, text)
        elif style == "point":
            self._draw_point(draw, img, text, number)
        elif style == "cta":
            self._draw_cta(draw, img, text, site)

        # ── 下部サイトURL ─────────────────────────────────
        try:
            url_font = ImageFont.truetype(FONT_MONO, 24) if FONT_MONO else ImageFont.load_default()
        except Exception:
            url_font = ImageFont.load_default()
        draw.text((60, VIDEO_H - 80), "global-nexus-blog.pages.dev",
                  font=url_font, fill=COLORS["pale"])

        # PIL Image → numpy array → MoviePy ImageClip
        arr = np.array(img)
        clip = ImageClip(arr).set_duration(duration)

        # フェードイン/アウト
        clip = clip.fadein(FADE_DURATION).fadeout(FADE_DURATION)
        return clip

    def _draw_hook(self, draw, img, text: str):
        from PIL import ImageFont
        # 中央に大きくフックテキスト
        try:
            font = ImageFont.truetype(FONT_SERIF, 88) if FONT_SERIF else ImageFont.load_default()
            small_font = ImageFont.truetype(FONT_MONO, 32) if FONT_MONO else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
            small_font = font

        # "FACT" ラベル
        draw.text((60, VIDEO_H // 2 - 300), "FACT", font=small_font, fill=COLORS["moss"])
        # アクセントライン
        draw.rectangle([(60, VIDEO_H // 2 - 260), (160, VIDEO_H // 2 - 254)], fill=COLORS["moss"])

        # テキスト折り返し
        lines = textwrap.wrap(text, width=18)
        y = VIDEO_H // 2 - 220
        for line in lines[:4]:
            draw.text((60, y), line, font=font, fill=COLORS["deep"])
            y += 105

    def _draw_point(self, draw, img, text: str, number: int):
        from PIL import ImageFont
        try:
            num_font  = ImageFont.truetype(FONT_SERIF, 160) if FONT_SERIF else ImageFont.load_default()
            text_font = ImageFont.truetype(FONT_SERIF, 72)  if FONT_SERIF else ImageFont.load_default()
        except Exception:
            num_font = text_font = ImageFont.load_default()

        # 大きい番号
        draw.text((60, VIDEO_H // 2 - 350), str(number),
                  font=num_font, fill=(*COLORS["moss"], 60))  # 薄いmoss

        # ポイントテキスト
        lines = textwrap.wrap(text, width=20)
        y = VIDEO_H // 2 - 100
        for line in lines[:4]:
            draw.text((60, y), line, font=text_font, fill=COLORS["deep"])
            y += 88

    def _draw_cta(self, draw, img, text: str, site: str):
        from PIL import ImageFont
        try:
            text_font = ImageFont.truetype(FONT_SERIF, 76) if FONT_SERIF else ImageFont.load_default()
            url_font  = ImageFont.truetype(FONT_MONO, 36)  if FONT_MONO  else ImageFont.load_default()
        except Exception:
            text_font = url_font = ImageFont.load_default()

        # CTAテキスト
        lines = textwrap.wrap(text, width=20)
        y = VIDEO_H // 2 - 200
        for line in lines[:4]:
            draw.text((60, y), line, font=text_font, fill=COLORS["deep"])
            y += 90

        # サイトURL ボックス
        box_y = VIDEO_H // 2 + 200
        draw.rectangle([(60, box_y), (VIDEO_W - 60, box_y + 80)],
                        fill=COLORS["moss"])
        draw.text((80, box_y + 18), site, font=url_font, fill=COLORS["bg"])