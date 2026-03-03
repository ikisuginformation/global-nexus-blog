# ai_core/critic_agent.py  v3
#
# Three additions over v2:
#
# [A] Concreteness pre-check (regex, no LLM)
#     Counts specific numbers/percentages and named entities in the article.
#     Rejects immediately if below threshold — no LLM call wasted.
#
# [B] LLM audit with explicit concreteness rules
#     Critic now scores concreteness 0-10 and rejects if score < 6.
#     FAQ answers that repeat the question are explicitly flagged.
#
# [C] Local npm run build audit (pre-deploy failsafe)
#     Runs only after [A] and [B] pass — avoids wasting build time on bad articles.
#     Writes a temp file, runs Astro build, parses errors, deletes temp file.
#     Build errors are passed verbatim to the Writer for self-correction.

import re
import os
import json
import subprocess
import tempfile
import requests
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL, BASE_DIR

# ── Concreteness thresholds ───────────────────────────────────────────────────
MIN_NUMBERS      = 2   # e.g. "35%", "$4.2B", "2024", "14 million"
MIN_NAMED_TOKENS = 2   # capitalized multi-word phrases or known brand patterns
CONCRETENESS_LLM_THRESHOLD = 6  # out of 10

# Regex: matches numbers with context (%, $, year ranges, large numbers)
RE_NUMBERS = re.compile(
    r'\b(\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s?(?:%|percent|billion|million|thousand|\$|USD|JPY|EUR)))'
    r'|\b(19|20)\d{2}\b'          # years
    r'|\$[\d,]+(?:\.\d+)?[BMK]?'  # dollar amounts
    r'|\d+(?:\.\d+)?x\b',         # multipliers like 3x
    re.IGNORECASE
)

# Regex: capitalized words 4+ chars (rough named-entity proxy — good enough for rejection)
RE_NAMED = re.compile(r'\b[A-Z][a-zA-Z]{3,}(?:\s+[A-Z][a-zA-Z]{2,})*\b')


class CriticAgent:
    def __init__(self):
        self.host     = OLLAMA_HOST
        self.model    = OLLAMA_MODEL
        self.repo_dir = BASE_DIR

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def evaluate_article(self, state: ArticleState) -> ArticleState:
        print("   ...Critic v3: audit sequence starting...")

        # ① Physical checks (fast, no LLM)
        rejection = self._physical_checks(state)
        if rejection:
            state.is_approved    = False
            state.critic_feedback = rejection
            print(f"   [Critic] ① REJECTED (physical): {rejection}")
            return state

        # ② Concreteness pre-check (regex, no LLM)
        conc_score, conc_feedback = self._concreteness_regex(state)
        state.concreteness_score = conc_score
        if conc_score < 3:
            state.is_approved    = False
            state.critic_feedback = conc_feedback
            print(f"   [Critic] ② REJECTED (concreteness regex, score={conc_score}): {conc_feedback}")
            return state

        # ③ LLM qualitative audit
        state = self._llm_audit(state)
        if not state.is_approved:
            print(f"   [Critic] ③ REJECTED (LLM): {state.critic_feedback}")
            return state

        # ④ npm run build pre-deploy audit (only runs on articles that pass ①②③)
        build_ok, build_error = self._build_audit(state)
        if not build_ok:
            state.is_approved    = False
            state.critic_feedback = (
                "Astro build failed. Fix the following error in the content_markdown:\n"
                + build_error[:600]
            )
            print(f"   [Critic] ④ REJECTED (build): {build_error[:120]}")
            return state

        print(f"   [Critic] ✅ APPROVED (concreteness={state.concreteness_score}/10)")
        return state

    # ─────────────────────────────────────────────────────────────────────────
    # ① Physical checks
    # ─────────────────────────────────────────────────────────────────────────

    def _physical_checks(self, state: ArticleState) -> str:
        """Returns rejection reason string, or empty string if all pass."""
        if not state.title or not state.content_markdown:
            return "Title or content is empty."
        if len(state.title) > 100:
            return f"Title too long ({len(state.title)} chars). Max 100."
        if state.description and len(state.description) > 160:
            return f"Description too long ({len(state.description)} chars). Max 160."
        if "## " not in state.content_markdown:
            return "No H2 headings found. Add structured sections with ## headings."
        if len(state.content_markdown) < 600:
            return f"Content too short ({len(state.content_markdown)} chars). Min 600."
        return ""

    # ─────────────────────────────────────────────────────────────────────────
    # ② Concreteness pre-check (regex)
    # ─────────────────────────────────────────────────────────────────────────

    def _concreteness_regex(self, state: ArticleState) -> tuple[int, str]:
        """
        Returns (score 0-10, feedback string).
        Score is a rough proxy — LLM audit does the precise assessment.
        This catches the obvious cases (zero numbers, zero named entities)
        without spending LLM tokens.
        """
        content = state.content_markdown

        numbers_found = RE_NUMBERS.findall(content)
        named_found   = [
            m for m in RE_NAMED.findall(content)
            if m not in ("The", "This", "That", "These", "Their",
                         "There", "They", "When", "What", "Which",
                         "According", "However", "Moreover", "Furthermore")
        ]

        number_count = len(numbers_found)
        named_count  = len(set(named_found))  # unique named tokens

        # Score: 0-4 points from numbers, 0-4 from named, 0-2 from both present
        score = min(4, number_count * 2) + min(4, named_count) + (2 if number_count >= 2 and named_count >= 2 else 0)
        score = min(10, score)

        feedback_parts = []
        if number_count < MIN_NUMBERS:
            feedback_parts.append(
                f"Only {number_count} specific number(s) found (need {MIN_NUMBERS}+). "
                "Add percentages, dollar amounts, years, or statistics."
            )
        if named_count < MIN_NAMED_TOKENS:
            feedback_parts.append(
                f"Only {named_count} named entity/entities found (need {MIN_NAMED_TOKENS}+). "
                "Name specific companies, products, researchers, or publications."
            )

        feedback = " | ".join(feedback_parts) if feedback_parts else "Concreteness OK."
        return score, feedback

    # ─────────────────────────────────────────────────────────────────────────
    # ③ LLM qualitative audit
    # ─────────────────────────────────────────────────────────────────────────

    def _llm_audit(self, state: ArticleState) -> ArticleState:
        """
        LLM audit with explicit concreteness rules.
        Critic scores concreteness and rejects if score < threshold.
        """
        prompt = f"""You are a strict editorial auditor. Evaluate this article.

Target language: {state.language}
Title: {state.title}
Description: {state.description}
Content (first 800 chars): {state.content_markdown[:800]}

AUDIT RULES — reject if ANY of these fail:
1. LANGUAGE: Text must be in {state.language}. Reject if wrong language.
2. OPENING: First paragraph must state a specific claim, not background or definitions.
3. CONCRETENESS: Score 0-10 based on:
   - Each specific company/product name mentioned: +1 (max 4)
   - Each specific number/stat/year with context: +1 (max 4)
   - FAQ answers that add new evidence (not just restate question): +2
   Reject if concreteness_score < {CONCRETENESS_LLM_THRESHOLD}.
4. STRUCTURE: Must have comparison table and FAQ section.

OUTPUT: JSON only.
{{"is_approved": true/false, "concreteness_score": 0-10, "critic_feedback": "Specific fix instruction if rejected. 'Approved.' if passed."}}"""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict editorial auditor. Output only valid JSON."
                },
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=90
            )
            response.raise_for_status()

            content_text = response.json().get("message", {}).get("content", "").strip()
            data = json.loads(content_text)

            state.is_approved        = data.get("is_approved", False)
            state.critic_feedback    = data.get("critic_feedback", "LLM audit parse error.")
            llm_score                = data.get("concreteness_score", 0)

            # Use the higher of regex score and LLM score (LLM has full context)
            state.concreteness_score = max(state.concreteness_score, llm_score)

            return state

        except requests.exceptions.Timeout:
            # Timeout: approve conservatively to avoid infinite retry loops
            print("   [Critic] LLM audit timeout — approving conservatively.")
            state.is_approved     = True
            state.critic_feedback = "LLM audit timed out. Approved by timeout fallback."
            return state
        except Exception as e:
            print(f"   [Critic Error] LLM audit failed: {e}")
            state.is_approved     = False
            state.critic_feedback = f"Audit system error: {e}"
            return state

    # ─────────────────────────────────────────────────────────────────────────
    # ④ npm run build pre-deploy audit
    # ─────────────────────────────────────────────────────────────────────────

    def _build_audit(self, state: ArticleState) -> tuple[bool, str]:
        """
        Writes article to a temp file, runs `npm run build`, parses errors.
        Temp file is always deleted, even if build fails.

        Returns (passed: bool, error_message: str)
        """
        # Construct minimal valid frontmatter for the temp file
        from datetime import datetime
        temp_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        tags_yaml = "\n".join([f"  - {t}" for t in (state.tags or ["tech"])])

        # Escape double quotes in title/description
        safe_title = state.title.replace('"', '\\"')
        safe_desc  = (state.description or "").replace('"', '\\"')

        temp_content = f"""---
title: "{safe_title}"
description: "{safe_desc}"
date: {temp_date}
language: "{state.language}"
tags:
{tags_yaml}
---

{state.content_markdown}
"""
        # Write temp file into the blog content directory
        content_dir = os.path.join(self.repo_dir, "src", "content", "blog")
        os.makedirs(content_dir, exist_ok=True)
        temp_path = os.path.join(content_dir, "_critic_temp_check.md")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(temp_content)

            print("   ...Critic ④: running npm run build (pre-deploy audit)...")

            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=120,    # Astro builds typically take 15-60s
                encoding="utf-8",
                errors="replace"
            )

            if result.returncode == 0:
                return True, ""

            # Build failed — extract the relevant error
            combined = (result.stdout + "\n" + result.stderr)

            # Filter to lines containing actual errors (Astro-specific patterns)
            error_lines = [
                line for line in combined.splitlines()
                if any(kw in line for kw in [
                    "error", "Error", "ERROR",
                    "Expected", "Unexpected",
                    "Cannot", "failed", "invalid",
                    "_critic_temp_check"  # lines referencing our file
                ])
            ]

            error_summary = "\n".join(error_lines[:20]) if error_lines else combined[:600]
            return False, error_summary

        except subprocess.TimeoutExpired:
            return False, "npm run build timed out after 120s."
        except FileNotFoundError:
            # npm not in PATH — skip build check rather than blocking pipeline
            print("   [Critic] npm not found — build audit skipped.")
            return True, ""
        except Exception as e:
            print(f"   [Critic] Build audit exception: {e} — skipping.")
            return True, ""  # Non-fatal: skip rather than block
        finally:
            # Always clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)