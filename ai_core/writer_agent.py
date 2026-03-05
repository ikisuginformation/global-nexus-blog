"""
ai_core/writer_agent.py — Global Nexus AI Writer v5

【修正内容】
  Fix 1: SyntaxError (line 227)
    f-string内でバックスラッシュエスケープ \" は使えない。
    → _build_table_html() ヘルパー関数に切り出し、
      cls 変数を f-string の外で組み立てることで解決。

  Fix 2: WriterAgent クラスが存在しなかった
    orchestrator.py が `from .writer_agent import WriterAgent` を呼ぶが
    クラスが未定義だったため ImportError になっていた。
    → Ollama を使う WriterAgent クラスを追加。

【動作モード】
  Mode A: WriterAgent クラス  ← orchestrator.py から使用 (Ollama)
  Mode B: スタンドアロン関数  ← CLI / GitHub Actions から使用 (Anthropic API)
"""

import json
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Relative imports (Mode A で必要) ──────────────────────────────────────────
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL

# ── Anthropic client (Mode B / CLI 用 — 遅延ロード) ──────────────────────────
_anthropic_client = None

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


# ─────────────────────────────────────────────────────────────
# AFFILIATE PROGRAMS — update with real IDs after approval
# ─────────────────────────────────────────────────────────────
AFFILIATE_PROGRAMS = {
    "semrush": {
        "name": "Semrush",
        "slug": "semrush",
        "commission": "$200/sale + 40% recurring",
        "cookie_days": 120,
        "trial": "14-day free trial",
        "price_from": "$129/month",
        "category": "B2B · SaaS",
        "apply_url": "https://www.semrush.com/partner/",
        "status": "pending",
    },
    "ahrefs": {
        "name": "Ahrefs",
        "slug": "ahrefs",
        "commission": "$100/sale",
        "cookie_days": 60,
        "trial": "7-day trial at $7",
        "price_from": "$99/month",
        "category": "SEO · Research",
        "apply_url": "https://ahrefs.com/affiliates",
        "status": "pending",
    },
    "nordvpn": {
        "name": "NordVPN",
        "slug": "nordvpn",
        "commission": "40% of sale",
        "cookie_days": 30,
        "trial": "30-day money-back",
        "price_from": "$3.99/month",
        "category": "VPN · Privacy",
        "apply_url": "https://nordvpn.com/affiliates/",
        "status": "pending",
    },
    "expressvpn": {
        "name": "ExpressVPN",
        "slug": "expressvpn",
        "commission": "$36/sale",
        "cookie_days": 90,
        "trial": "30-day money-back",
        "price_from": "$8.32/month",
        "category": "VPN · Privacy",
        "apply_url": "https://www.expressvpn.com/affiliate",
        "status": "pending",
    },
    "surfer-seo": {
        "name": "Surfer SEO",
        "slug": "surfer-seo",
        "commission": "25% recurring",
        "cookie_days": 60,
        "trial": "7-day free trial",
        "price_from": "$89/month",
        "category": "SEO · Content",
        "apply_url": "https://surferseo.com/affiliate/",
        "status": "pending",
    },
}

# ─────────────────────────────────────────────────────────────
# WRITER SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────
ARTICLE_BRIEF_SCHEMA = {
    "title": "string",
    "description": "string (155 chars max for SEO)",
    "hook": "string (first bold sentence — most surprising fact)",
    "target_keyword": "string",
    "secondary_keywords": ["string"],
    "category": "string",
    "categorySlug": "string",
    "articleId": "string (GNX-XXX)",
    "readingMinutes": "number",
    "pubDate": "string (YYYY-MM-DD)",
    "affiliateDisclosure": "boolean",
    "primaryAffiliate": "string (key from AFFILIATE_PROGRAMS)",
    "verdict": {
        "tool": "string",
        "verdict": "recommended|conditional|avoid",
        "summary": "string (2 sentences)",
        "pros": ["string (4 items)"],
        "cons": ["string (2-3 items)"],
        "price": "string",
        "affiliateSlug": "string",
        "affiliateLabel": "string",
    },
    "relatedTools": [{"name": "string", "slug": "string", "label": "string", "category": "string"}],
    "comparisonTableData": {
        "headers": ["string"],
        "rows": [["string"]],
        "recommendedRow": "number (0-indexed)",
    },
    "sections": [
        {"h2": "string", "keyPoints": ["string"]},
    ],
    "tags": ["string"],
}

WRITER_SYSTEM = """You are the editorial writer for Global Nexus, an independent analysis publication.

Your voice:
- Direct. You state conclusions first, evidence second.
- Analytical. You cite specific numbers, not vague claims.
- Skeptical by default. You identify what the marketing copy omits.
- Never hedging. You don't write "may", "might", "could potentially".
- No AI tells. You never write: "In conclusion", "It's worth noting", "dive into",
  "game-changer", "robust solution", "leverage", "utilize", "crucial", "importantly".

Your job is to write articles that:
1. Rank on Google for commercial-intent keywords
2. Convert readers into affiliate purchases through honest, specific analysis
3. Build reader trust by including real limitations alongside strengths

Article structure that converts:
- Open with the most surprising or counterintuitive fact (bold)
- Present the cost/ROI case with a comparison table
- Include one inline affiliate CTA after the ROI section
- Address real limitations honestly (this builds trust, which increases conversions)
- End with a concrete verdict and next action

The ghost note (hidden text, barely visible, reveals on hover) should:
- Reference a measurement anomaly
- Be factually plausible but structurally impossible
- Example: "one data point in this comparison was recorded before the instrument existed"
"""


# ─────────────────────────────────────────────────────────────
# MODE A: WriterAgent クラス — orchestrator.py から使用
# Ollama (ローカルLLM) を呼ぶ
# ─────────────────────────────────────────────────────────────
class WriterAgent:
    """
    orchestrator.py が呼ぶクラス。
    state = self.writer.generate_article(state)
    """

    def __init__(self):
        self.host  = OLLAMA_HOST
        self.model = OLLAMA_MODEL

    def generate_article(self, state: ArticleState) -> ArticleState:
        """
        ArticleState を受け取り、記事を生成して返す。
        state.title / description / content_markdown / tags を埋める。
        """
        print(f"   ...Writer: '{state.topic}' [{state.language}]")

        contrarian = getattr(state, "contrarian_angle", "")
        thesis     = getattr(state, "unique_thesis", "")
        audience   = getattr(state, "target_audience", "")

        angle_block = ""
        if contrarian:
            angle_block += f"Contrarian angle: {contrarian}\n"
        if thesis:
            angle_block += f"Unique thesis: {thesis}\n"
        if audience:
            angle_block += f"Target audience: {audience}\n"

        prompt = (
            "Write a complete blog article for Global Nexus.\n\n"
            f"Language: {state.language}\n"
            f"Topic: {state.topic}\n"
            f"Title idea: {state.title or state.topic}\n"
            f"{angle_block}\n"
            "STRUCTURE REQUIREMENTS:\n"
            "1. Opening paragraph: bold claim with specific number or fact\n"
            "2. At least 3 H2 sections (## heading)\n"
            "3. One comparison table in Markdown format\n"
            "4. One FAQ section (## FAQ)\n"
            "5. Minimum 800 words\n\n"
            f"Write in {state.language}. Direct, analytical, no filler.\n\n"
            "OUTPUT FORMAT — JSON only:\n"
            '{"title":"max 80 chars","description":"max 155 chars",'
            '"tags":["t1","t2","t3","t4"],"content_markdown":"full Markdown body"}'
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert blog writer. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "stream": False,
        }

        try:
            resp = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=180,
            )
            resp.raise_for_status()

            raw = resp.json().get("message", {}).get("content", "").strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw).strip()

            data = json.loads(raw)

            state.title            = data.get("title", state.topic)
            state.description      = data.get("description", "")
            state.tags             = data.get("tags", [])
            state.content_markdown = data.get("content_markdown", "")

            print(f"   [Writer] OK: {state.title}")
            return state

        except requests.exceptions.Timeout:
            print("   [Writer] Ollama timeout — empty content")
            state.content_markdown = ""
            return state
        except Exception as e:
            print(f"   [Writer Error] {e}")
            state.content_markdown = ""
            return state


# ─────────────────────────────────────────────────────────────
# MODE B: スタンドアロン関数 — CLI / GitHub Actions から使用
# Anthropic API (claude-sonnet) を呼ぶ
# ─────────────────────────────────────────────────────────────

def generate_article_brief(
    topic: str,
    primary_affiliate: str,
    target_keyword: str,
    article_id: str,
) -> dict:
    """Generate a structured article brief from a topic."""

    affiliate = AFFILIATE_PROGRAMS.get(primary_affiliate, {})

    prompt = f"""Generate a complete article brief for Global Nexus.

Topic: {topic}
Primary affiliate tool: {affiliate.get('name', primary_affiliate)}
Target keyword: {target_keyword}
Affiliate commission: {affiliate.get('commission', 'unknown')}
Trial offer: {affiliate.get('trial', 'none')}
Price: {affiliate.get('price_from', 'unknown')}

Requirements:
- The title must contain the target keyword or a close variant
- The hook (first bold sentence) must cite a specific number or fact
- The verdict must be honest — include real limitations
- The comparison table must show cost savings vs alternatives
- Include 3-4 related tools (all with affiliate potential)
- Tags should include the primary keyword and category terms

Return ONLY valid JSON matching this schema:
{json.dumps(ARTICLE_BRIEF_SCHEMA, indent=2)}

Article ID: {article_id}
Today's date: {datetime.now().strftime('%Y-%m-%d')}
"""

    response = _get_anthropic().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        system="Return only valid JSON. No markdown code fences. No preamble."
    )

    text = response.content[0].text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    return json.loads(text)


# ─────────────────────────────────────────────────────────────
# 【Fix 1】テーブルHTML生成ヘルパー
#
# 問題のあったコード (SyntaxError):
#   f'<tr{"  class=\\"recommended-row\\"" if i==recommended else ""}>'
#   → f-string の {} 内でバックスラッシュは使えない
#
# 解決策:
#   class属性を f-string の外で変数 cls に組み立ててから使う
# ─────────────────────────────────────────────────────────────
def _build_table_html(headers: list, rows: list, recommended: int) -> str:
    """
    比較テーブルの HTML を生成する。

    NG (SyntaxError になる):
        f'<tr{"  class=\\"recommended-row\\"" if i==rec else ""}>'

    OK (この関数のやり方):
        cls = ' class="recommended-row"' if i == recommended else ""
        f"<tr{cls}>..."
    """
    if not headers or not rows:
        return ""

    header_cells = "".join(f"<th>{h}</th>" for h in headers)

    row_parts = []
    for i, row in enumerate(rows):
        # ← ここがポイント: class属性を先に変数に入れる
        cls   = ' class="recommended-row"' if i == recommended else ""
        cells = "</td><td>".join(str(c) for c in row)
        row_parts.append(f"<tr{cls}><td>{cells}</td></tr>")

    body = "\n".join(row_parts)

    return (
        '\n<table class="compare-table">\n'
        f"<thead><tr>{header_cells}</tr></thead>\n"
        f"<tbody>\n{body}\n</tbody>\n"
        "</table>\n"
    )


def generate_article_body(brief: dict) -> str:
    """Generate full markdown article body from brief."""

    affiliate   = AFFILIATE_PROGRAMS.get(brief.get("primaryAffiliate", ""), {})
    table_data  = brief.get("comparisonTableData", {})

    # ← 修正済み: _build_table_html() を使う (f-string backslash 問題を回避)
    table_md = _build_table_html(
        table_data.get("headers", []),
        table_data.get("rows", []),
        table_data.get("recommendedRow", 0),
    )

    # Build sections outline
    sections_outline = "\n".join(
        f"## {s['h2']}\nKey points: {', '.join(s.get('keyPoints', []))}"
        for s in brief.get("sections", [])
    )

    aff_slug   = brief["verdict"]["affiliateSlug"]
    aff_label  = brief["verdict"]["affiliateLabel"]
    trial_text = affiliate.get("trial", "free trial")
    article_id = brief["articleId"]
    hook       = brief["hook"]
    keyword    = brief["target_keyword"]

    # Build special blocks as plain strings (f-string内のネストを避ける)
    aff_cta = (
        '<div class="aff-cta">\n'
        f'  <span class="aff-cta-text">{trial_text} — no credit card required.</span>\n'
        f'  <a href="/go/{aff_slug}" class="aff-cta-btn" target="_blank" rel="noopener">'
        f'{aff_label} \u2192</a>\n'
        '  <span class="aff-disc">Affiliate link \u2014 commission earned at no cost to you</span>\n'
        '</div>'
    )

    ghost_note = (
        f'<div class="ghost-note">[ field note {article_id}: '
        'one measurement in this record was made by an instrument '
        'that was not present at the time of measurement. '
        'the record is otherwise accurate. ]</div>'
    )

    prompt = f"""Write the full body of this Global Nexus article.

BRIEF:
Title: {brief['title']}
Hook: {hook}
Target keyword: {keyword}
Secondary keywords: {', '.join(brief.get('secondary_keywords', []))}

SECTIONS TO COVER:
{sections_outline}

COMPARISON TABLE (insert after the ROI/cost section):
{table_md}

AFFILIATE CTA (insert after the comparison table exactly as-is):
{aff_cta}

GHOST NOTE (insert once in the middle of the article exactly as-is):
{ghost_note}

RULES:
- Start with **{hook}** (bold, no "Introduction:" heading)
- Use ## for H2 headings, ### for H3
- No conclusion section — end with the verdict recommendation
- No bullet points for flowing analysis — use prose paragraphs
- Bullet points ONLY for the pros/cons or feature lists
- Target keyword "{keyword}" must appear in first 100 words
- Cite specific numbers throughout — percentages, prices, time estimates
- Include the comparison table HTML exactly as provided above
- Include one <div class="aff-cta"> block exactly as specified
- Include one <div class="ghost-note"> block
- Total length: 1,200-1,600 words
"""

    response = _get_anthropic().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        system=WRITER_SYSTEM,
    )

    return response.content[0].text


def brief_to_frontmatter(brief: dict) -> str:
    """Convert article brief to Astro content collection frontmatter."""

    verdict = brief.get("verdict", {})
    related = brief.get("relatedTools", [])
    tags    = brief.get("tags", [])

    related_yaml = "\n".join(
        f'  - name: "{t["name"]}"\n'
        f'    slug: "{t["slug"]}"\n'
        f'    label: "{t["label"]}"\n'
        f'    category: "{t["category"]}"'
        for t in related
    )
    pros_yaml = "\n".join(f'    - "{p}"' for p in verdict.get("pros", []))
    cons_yaml = "\n".join(f'    - "{c}"' for c in verdict.get("cons", []))
    tags_yaml = "\n".join(f'  - "{t}"' for t in tags)
    aff_disc  = str(brief.get("affiliateDisclosure", True)).lower()

    return (
        "---\n"
        f'title: "{brief["title"]}"\n'
        f'description: "{brief["description"]}"\n'
        f'pubDate: "{brief["pubDate"]}"\n'
        f'category: "{brief["category"]}"\n'
        f'categorySlug: "{brief["categorySlug"]}"\n'
        f'articleId: "{brief["articleId"]}"\n'
        f'readingMinutes: {brief["readingMinutes"]}\n'
        f'hook: "{brief["hook"]}"\n'
        f"affiliateDisclosure: {aff_disc}\n"
        "verdict:\n"
        f'  tool: "{verdict.get("tool", "")}"\n'
        f'  verdict: "{verdict.get("verdict", "conditional")}"\n'
        f'  summary: "{verdict.get("summary", "")}"\n'
        "  pros:\n"
        f"{pros_yaml}\n"
        "  cons:\n"
        f"{cons_yaml}\n"
        f'  price: "{verdict.get("price", "")}"\n'
        f'  affiliateSlug: "{verdict.get("affiliateSlug", "")}"\n'
        f'  affiliateLabel: "{verdict.get("affiliateLabel", "")}"\n'
        "relatedTools:\n"
        f"{related_yaml}\n"
        "tags:\n"
        f"{tags_yaml}\n"
        "---\n"
    )


def generate_full_article(
    topic: str,
    primary_affiliate: str,
    target_keyword: str,
    article_id: str,
    output_dir: str = "src/content/posts",
) -> str:
    """Full pipeline: topic → brief → article → .md file. Returns file path."""

    print(f"[Writer] Generating brief for: {topic}")
    brief = generate_article_brief(topic, primary_affiliate, target_keyword, article_id)

    print(f"[Writer] Brief: {brief['title']}")
    print("[Writer] Generating article body...")
    body = generate_article_body(brief)

    full_content = brief_to_frontmatter(brief) + "\n" + body

    slug = re.sub(r'[^a-z0-9]+', '-', brief['title'].lower()).strip('-')[:60]

    output_path = Path(output_dir) / f"{slug}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(full_content, encoding="utf-8")

    print(f"[Writer] Saved: {output_path}")
    return str(output_path)


def generate_video_script(
    article_path: str,
    format: str = "short",
) -> dict:
    """Generate video script from article. Returns dict."""

    article_content = Path(article_path).read_text(encoding="utf-8")

    if format == "short":
        duration  = "55-60 seconds"
        structure = (
            "[0-3s]   HOOK: One number or fact. No greeting. No intro.\n"
            "[3-25s]  PROBLEM: The thing the industry doesn't want you to know.\n"
            "[25-50s] EVIDENCE: One specific data point that proves the problem.\n"
            "[50-60s] RESOLUTION: What to do instead. Ends on question or insight, not CTA.\n"
        )
    else:
        duration  = "7-10 minutes"
        structure = (
            "[0-30s]  HOOK: Most surprising finding from the analysis.\n"
            "[30s-2m] CONTEXT: Why this matters to the viewer specifically.\n"
            "[2-6m]   EVIDENCE: Walk through the comparison data and methodology.\n"
            "[6-8m]   NUANCE: Where the tool works vs where it fails.\n"
            "[8-10m]  VERDICT: Specific recommendation with conditions.\n"
        )

    prompt = (
        f"Based on this article, generate a {format} video script for YouTube/TikTok/Reels.\n\n"
        f"ARTICLE:\n{article_content[:3000]}\n\n"
        f"FORMAT: {format} ({duration})\nSTRUCTURE:\n{structure}\n\n"
        "RULES:\n"
        "- Write exactly what the presenter says — no stage directions\n"
        "- No 'Hey guys', no 'In today's video', no 'Don't forget to subscribe'\n"
        "- Start with a statement, not a question\n"
        "- Use contractions (don't, can't, won't) — sounds human\n"
        "- No filler: 'basically', 'essentially', 'kind of'\n\n"
        "Return as JSON:\n"
        '{"hook_text":"first 3 seconds of spoken text","full_script":"complete word-for-word script",'
        '"caption":"platform caption (150 chars max)","hashtags":["t1","t2","t3","t4","t5"],'
        '"youtube_description":"3 paragraphs or null for shorts","title_options":["o1","o2","o3"]}'
    )

    response = _get_anthropic().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
        system="Return only valid JSON. No markdown fences.",
    )

    text = response.content[0].text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


def generate_note_article(article_path: str) -> dict:
    """Generate note.mu companion article in Japanese. Different angle, not translation."""

    article_content = Path(article_path).read_text(encoding="utf-8")

    prompt = (
        "This English article will be repurposed for Japan's note.mu platform.\n\n"
        f"ORIGINAL ARTICLE:\n{article_content[:2000]}\n\n"
        "Generate a note.mu article that:\n"
        "- Takes a DIFFERENT ANGLE on the same topic (not a translation)\n"
        "- Is written in natural Japanese\n"
        "- Opens with the Japanese reader's specific pain point\n"
        "- Length: 600-800 words\n"
        "- Ends with a link to the full English analysis\n\n"
        "Do NOT use: 〜となっています / 〜と言えるでしょう\n\n"
        'Return JSON: {"title":"","body":"","tags":["t1","t2","t3","t4","t5"],"cta_line":""}'
    )

    response = _get_anthropic().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        system="Return only valid JSON. No markdown fences.",
    )

    text = response.content[0].text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


# ─────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
Global Nexus Writer Agent v5
Usage:
  python -m ai_core.writer_agent article <topic> <affiliate_key> <keyword> <article_id>
  python -m ai_core.writer_agent video <article_path> [short|long]
  python -m ai_core.writer_agent note <article_path>
  python -m ai_core.writer_agent affiliates

Examples:
  python -m ai_core.writer_agent article "Semrush vs Ahrefs for B2B teams" semrush "semrush review" GNX-007
  python -m ai_core.writer_agent video src/content/posts/my-article.md short
  python -m ai_core.writer_agent affiliates
""")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "article":
        topic, aff_key, keyword, art_id = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
        path = generate_full_article(topic, aff_key, keyword, art_id)
        print(f"\n✓ Article: {path}")
        print("\n[Writer] Generating Short video script...")
        script = generate_video_script(path, "short")
        script_path = path.replace('.md', '-short-script.json')
        Path(script_path).write_text(json.dumps(script, indent=2, ensure_ascii=False))
        print(f"✓ Short script: {script_path}")

    elif cmd == "video":
        article_path = sys.argv[2]
        fmt = sys.argv[3] if len(sys.argv) > 3 else "short"
        script = generate_video_script(article_path, fmt)
        out = article_path.replace('.md', f'-{fmt}-script.json')
        Path(out).write_text(json.dumps(script, indent=2, ensure_ascii=False))
        print(f"✓ Script: {out}")
        print(f"\nHOOK: {script['hook_text']}")
        print(f"CAPTION: {script['caption']}")

    elif cmd == "note":
        article_path = sys.argv[2]
        note = generate_note_article(article_path)
        out = article_path.replace('.md', '-note.json')
        Path(out).write_text(json.dumps(note, indent=2, ensure_ascii=False))
        print(f"✓ note.mu: {out}")
        print(f"Title: {note['title']}")

    elif cmd == "affiliates":
        print("\n=== AFFILIATE PROGRAMS ===\n")
        for key, prog in AFFILIATE_PROGRAMS.items():
            icon = "✓" if prog["status"] == "active" else "○"
            print(f"{icon} {prog['name']}")
            print(f"  Commission: {prog['commission']}")
            print(f"  Apply: {prog['apply_url']}")
            print(f"  Status: {prog['status']}\n")