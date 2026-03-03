# ai_core/writer_agent.py
#
# Writer Agent — Perspective Architecture
#
# The core problem with AI content farms: they generate the same article
# everyone else generates. The fix is forcing the model to commit to a
# SPECIFIC THESIS before writing.
#
# Perspective Architecture:
#   1. Director provides contrarian_angle and unique_thesis
#   2. Writer OPENS with the thesis (not background, not definitions)
#   3. Writer DEFENDS the thesis — not "on one hand / on the other"
#   4. Comparison table: conventional view vs. thesis view
#   5. FAQ answers the strongest objections to the thesis
#   6. Real research data (from ResearcherAgent) grounds every claim

import requests
import json
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL
from .researcher_agent import ResearcherAgent, ResearchBrief

LANGUAGE_INSTRUCTIONS = {
    "ja": "日本語で執筆すること。翻訳ではなく、日本語ネイティブとして最初から日本語で思考・執筆すること。",
    "es": "Escribe en español nativo. No traduzcas desde el inglés — piensa y redacta directamente en español.",
    "en": "Write in English. Use a confident, direct editorial voice. No hedging.",
    "zh": "用中文写作。不要翻译，直接用中文思考和写作。",
    "ko": "한국어로 작성하세요. 번역이 아닌, 처음부터 한국어로 사고하고 작성하세요.",
    "fr": "Écris en français natif. Ne traduis pas depuis l'anglais — rédige directement en français.",
    "de": "Schreibe auf Deutsch. Nicht übersetzen — direkt auf Deutsch denken und schreiben.",
    "pt": "Escreve em português nativo. Não traduzas do inglês — pensa e rediges diretamente em português.",
    "ar": "اكتب باللغة العربية. لا تترجم من الإنجليزية — فكر واكتب مباشرة بالعربية.",
    "hi": "हिंदी में लिखें। अंग्रेज़ी से अनुवाद न करें — सीधे हिंदी में सोचें और लिखें।",
}

MAX_FEEDBACK_CHARS = 300


class WriterAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.researcher = ResearcherAgent()

    def generate_article(self, state: ArticleState) -> ArticleState:
        """
        Generates a blog article with a specific thesis and real research data.
        """

        # 1. Fetch real research data (never blocks — degrades gracefully)
        brief: ResearchBrief = self.researcher.research(state.topic, state.language)

        # 2. Extract perspective from strategy (set by Orchestrator from Director output)
        contrarian_angle = getattr(state, 'contrarian_angle', '')
        unique_thesis    = getattr(state, 'unique_thesis', '')
        target_audience  = getattr(state, 'target_audience', 'a curious, skeptical reader')

        # 3. Language instruction
        lang_instruction = LANGUAGE_INSTRUCTIONS.get(
            state.language,
            f"Write in {state.language}. Think and write natively — do not translate."
        )

        # 4. Feedback injection (retry path)
        feedback_instruction = ""
        if state.retry_count > 0 and state.critic_feedback:
            feedback_instruction = f"""
[AUDITOR FEEDBACK — MUST FIX]
Previous attempt rejected. Reason: {state.critic_feedback[:MAX_FEEDBACK_CHARS]}
Fix this specifically in your rewrite.
"""

        # 5. Perspective block
        if contrarian_angle and unique_thesis:
            perspective_block = f"""
[PERSPECTIVE ARCHITECTURE — EDITORIAL MANDATE]
Contrarian Angle: {contrarian_angle}
Unique Thesis: {unique_thesis}
Target Reader: {target_audience}

RULES:
- First paragraph MUST STATE this thesis. Not after background. NOW.
- Every H2 section must ADVANCE or DEFEND this thesis.
- Comparison table: "conventional wisdom" (left, ❌) vs "thesis position" (right, ✅)
- FAQ: answer the 3 strongest OBJECTIONS to your thesis
- Do NOT write "on the other hand" or "it depends" — take a position
- Be wrong confidently rather than right vaguely.
"""
        else:
            perspective_block = """
[PERSPECTIVE REQUIREMENT]
Choose ONE non-obvious angle and defend it throughout.
Do NOT write a balanced "pros and cons" piece — take a position in paragraph 1.
"""

        # 6. Research context
        research_block = ""
        if brief.key_facts or brief.abstract:
            research_block = brief.to_prompt_context()

        # 7. Assemble prompt
        prompt = f"""
You are an elite journalist writing for intelligent, skeptical readers.
They have already read 50 articles on this topic. Make yours the last one they need.

Topic: {state.topic}
Target Language: {state.language}

[LANGUAGE — NON-NEGOTIABLE]
{lang_instruction}
ALL output fields (title, description, content_markdown) MUST be in {state.language}.

{perspective_block}

{research_block}

{feedback_instruction}

[STRUCTURE]

1. TITLE: Must embed the contrarian angle.
   GOOD: "Why NordVPN Is Making Your Privacy Worse (Not Better)"
   BAD:  "Top 5 VPNs for Privacy in 2026"

2. OPENING (first 100 words):
   - State the thesis immediately with a specific, surprising claim
   - NEVER start with "In today's world...", "Have you ever wondered...", "In this article..."

3. BODY SECTIONS:
   - Short paragraphs (1-3 sentences)
   - **Bold** the most important idea per section
   - H2 headings read like arguments, not labels

4. COMPARISON TABLE (H2: thesis vs conventional wisdom)
   - ❌ column: standard advice / popular belief
   - ✅ column: what evidence / the thesis actually shows
   - At least 4 rows

5. PROS & CONS (H3): Genuine balance — do NOT soften the cons.

6. FAQ (H2 in {state.language}):
   - 3 objections a skeptical reader would raise
   - Direct, engaged responses — no deflection

7. CLOSING: One sharp sentence. No "In conclusion."

[OUTPUT — VALID JSON ONLY, NO PREAMBLE, NO FENCES]
{{
    "title": "Thesis-driven title in {state.language}",
    "description": "Max 120 chars stating the thesis, in {state.language}",
    "content_markdown": "Full article in Markdown, in {state.language}",
    "tags": ["tag1", "tag2", "tag3"]
}}
"""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are an authoritative journalist writing in {state.language}. "
                        "You take strong editorial positions and defend them. "
                        "Output only valid JSON. No preamble, no fences."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False
        }

        try:
            print(f"   ...Writer: {self.model} へ送信 "
                  f"[lang={state.language}, facts={len(brief.key_facts)}]...")

            response = requests.post(
                f"{self.host}/api/chat", json=payload, timeout=120
            )
            response.raise_for_status()

            content_text = response.json().get("message", {}).get("content", "").strip()

            for fence in ("```json", "```"):
                if content_text.startswith(fence):
                    content_text = content_text[len(fence):]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
            content_text = content_text.strip()

            data = json.loads(content_text)

            state.title            = data.get("title", f"Draft: {state.topic}")
            state.description      = data.get("description", "")
            state.content_markdown = data.get("content_markdown", "")
            state.tags             = data.get("tags", ["AI", "Tech"])

            return state

        except json.JSONDecodeError:
            print(f"   [Writer Error] 不正なJSON: {content_text[:120]}...")
            return state
        except Exception as e:
            print(f"   [Writer Error] 通信エラー: {e}")
            return state