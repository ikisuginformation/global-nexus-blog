# ai_core/writer_agent.py
#
# Writer Agent — v3 (3 critical fixes applied)
#
# Fix 1: editorial_strategy field removed.
#         Chain-of-Thought moved to system prompt.
#         Models reason better when told HOW to think, not asked to output thinking.
#
# Fix 2: ResearcherAgent now runs ONCE per article, cached in state.research_brief.
#         Retries reuse the same data. No redundant HTTP calls.
#
# Fix 3: XML tags replaced with numbered plain-text rules.
#         llama3.1 with format:json treats XML as string data to escape,
#         not as structural instructions. Plain numbered lists get followed.

import requests
import json
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL
from .researcher_agent import ResearcherAgent, ResearchBrief

LANGUAGE_INSTRUCTIONS = {
    "ja": "Write entirely in Japanese. Think natively in Japanese from the first word. Do not translate.",
    "es": "Write entirely in Spanish. Think natively in Spanish. Do not translate from English.",
    "en": "Write in English. Direct, confident, no hedging.",
    "zh": "Write entirely in Chinese. Think natively in Chinese. Do not translate.",
    "ko": "Write entirely in Korean. Think natively in Korean. Do not translate.",
    "fr": "Write entirely in French. Think natively in French. Do not translate.",
    "de": "Write entirely in German. Think natively in German. Do not translate.",
    "pt": "Write entirely in Portuguese. Think natively in Portuguese. Do not translate.",
}

MAX_FEEDBACK_CHARS = 300


class WriterAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.researcher = ResearcherAgent()

    def generate_article(self, state: ArticleState) -> ArticleState:

        # ── Fix 2: Research runs ONCE, cached on state ────────────────────────
        # On retry, state.research_brief already exists — skip the HTTP calls.
        if not getattr(state, 'research_brief', None):
            state.research_brief = self.researcher.research(
                state.topic, state.language
            )
        brief: ResearchBrief = state.research_brief

        # ── Context assembly ──────────────────────────────────────────────────
        contrarian_angle = getattr(state, 'contrarian_angle', '')
        unique_thesis    = getattr(state, 'unique_thesis', '')
        target_audience  = getattr(state, 'target_audience', 'a skeptical, intelligent reader')
        lang_instruction = LANGUAGE_INSTRUCTIONS.get(
            state.language,
            f"Write entirely in {state.language}. Do not translate."
        )

        # Retry feedback
        feedback_block = ""
        if state.retry_count > 0 and state.critic_feedback:
            feedback_block = (
                f"\nPREVIOUS ATTEMPT REJECTED. FIX THIS BEFORE WRITING:\n"
                f"{state.critic_feedback[:MAX_FEEDBACK_CHARS]}\n"
            )

        # Research block — plain text, no XML
        research_block = ""
        if brief.has_data():
            research_block = (
                "VERIFIED RESEARCH DATA — cite at least 2 of these facts in the article:\n"
                + brief.to_prompt_context()
            )

        # Thesis block
        if contrarian_angle and unique_thesis:
            thesis_block = (
                f"THESIS TO DEFEND: {unique_thesis}\n"
                f"CONTRARIAN ANGLE: {contrarian_angle}\n"
                f"TARGET READER: {target_audience}"
            )
        else:
            thesis_block = (
                "Choose ONE non-obvious, opinionated angle and defend it decisively. "
                "Do not write a balanced 'pros and cons' piece."
            )

        # ── Fix 3: Plain numbered rules — no XML tags ─────────────────────────
        # llama3.1 with format:json parses XML as escape-needed string data.
        # Numbered plain-text rules are processed correctly.
        prompt = f"""ROLE: Elite journalist. Opinionated. Evidence-based. No hedging.
LANGUAGE: {lang_instruction}

{thesis_block}

{research_block}

{feedback_block}

WRITING RULES — follow every rule exactly:
1. First sentence states the thesis as a direct, confident fact. Zero setup or background.
2. Each H2 heading is a sub-argument defending the thesis, not a label or category.
3. Comparison table required. Left column: ❌ popular myth or conventional wisdom. Right column: ✅ evidence-backed thesis position. Minimum 4 rows.
4. Pros and Cons section required. Cons must be genuine — not softened or vague.
5. FAQ section required. Each answer MUST include one specific company name, study, or number. Answers that repeat the question without new evidence are rejected.
6. Final sentence: one declarative claim. No "In conclusion", no "To summarize".
7. Bold the single most important idea in each section.
8. Paragraphs: maximum 3 sentences each.

OUTPUT FORMAT: JSON only. No markdown fences. No preamble. No extra keys.
{{"title": "Thesis-driven title in {state.language}", "description": "Max 120 chars, states the thesis, in {state.language}", "content_markdown": "Full article in Markdown, in {state.language}", "tags": ["tag1", "tag2", "tag3"]}}"""

        # ── Fix 1: Chain-of-Thought in system prompt, not as output field ─────
        # Asking the model to OUTPUT its strategy wastes tokens on throwaway text.
        # Telling it HOW to reason in the system prompt costs nothing extra.
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an elite journalist with a strong editorial voice. "
                        "Before writing each section, silently ask: "
                        "'Does this sentence advance the thesis or just fill space?' "
                        "Cut anything that fills space. "
                        "Output only valid JSON. No preamble, no fences, no extra keys."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False
        }

        try:
            print(f"   ...Writer: {self.model} "
                  f"[lang={state.language}, "
                  f"facts={len(brief.key_facts)}, "
                  f"retry={state.retry_count}]...")

            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=120
            )
            response.raise_for_status()

            content_text = response.json().get("message", {}).get("content", "").strip()

            # Strip markdown fences if model ignores format:json instruction
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
            print(f"   [Writer Error] Invalid JSON: {content_text[:120]}...")
            return state
        except requests.exceptions.Timeout:
            print(f"   [Writer Error] Timeout after 120s — topic too complex for {self.model}")
            return state
        except Exception as e:
            print(f"   [Writer Error] {e}")
            return state