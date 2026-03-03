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

        # 5. Perspective block (Positive Constraintsに変換)
        if contrarian_angle and unique_thesis:
            perspective_block = f"""
<editorial_mandate>
Contrarian Angle: {contrarian_angle}
Unique Thesis: {unique_thesis}
Target Reader: {target_audience}

Drive the narrative using this specific thesis. 
Open immediately with a sharp claim establishing the thesis.
Structure every H2 section as a supporting argument for the thesis.
Include a Comparison Table contrasting 'Conventional Wisdom' with the 'Thesis Position'.
Address and dismantle the 3 strongest skeptical objections in the FAQ section.
Maintain a highly opinionated, decisive tone throughout.
</editorial_mandate>
"""
        else:
            perspective_block = """
<editorial_mandate>
Select one non-obvious, highly opinionated angle and defend it decisively throughout the entire article. Open with a sharp claim.
</editorial_mandate>
"""

        # 6. Research context
        research_block = ""
        if brief.key_facts or brief.abstract:
            research_block = f"<research_context>\n{brief.to_prompt_context()}\n</research_context>"

        # 7. Assemble prompt (XML & Context First)
        prompt = f"""
<role>
You are an elite, authoritative journalist writing for highly intelligent, skeptical readers. 
They demand information density and sharp insights. Make your article the definitive final word on the subject.
</role>

<target_language>
{lang_instruction}
ALL internal processing and final outputs MUST be in {state.language}.
</target_language>

{research_block}

{perspective_block}

{feedback_instruction}

<instructions>
1. TITLE: Embed the contrarian angle directly. Make it punchy and expensive-sounding.
2. OPENING (first 100 words): Start with a specific, surprising fact or claim. Hook the reader instantly.
3. BODY: Use short, impactful paragraphs. Emphasize the core idea in bold.
4. COMPARISON TABLE: Use ❌ for popular belief and ✅ for the evidence-backed thesis.
5. PROS & CONS: Provide genuine, hard-hitting analysis.
6. FAQ: Provide direct, unflinching responses to skeptical objections.
7. CLOSING: End with a single, sharp, declarative sentence that leaves a lasting impact.
</instructions>

<output_format>
You must respond strictly in JSON.
CRITICAL: To ensure maximum logical rigor, you MUST output your internal thought process FIRST under the "editorial_strategy" key. Plan how you will weave the research into your thesis before writing the content.

{{
    "editorial_strategy": "Your step-by-step logical plan and argument structure in {state.language}",
    "title": "Thesis-driven title in {state.language}",
    "description": "Max 120 chars stating the thesis, in {state.language}",
    "content_markdown": "Full article in Markdown, in {state.language}",
    "tags": ["tag1", "tag2", "tag3"]
}}
</output_format>
"""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an elite autonomous journalist. You follow XML instructions perfectly and output only valid JSON."
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
