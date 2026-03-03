# ai_core/models.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ArticleState:
    """
    Shared state object passed between all agents in the pipeline.
    
    Flow: Orchestrator → Writer → Editor → Critic → (retry?) → Publisher
    
    New fields (v2):
      contrarian_angle  — the non-obvious take provided by the Director
      unique_thesis     — the specific argument the article will defend
      target_audience   — who is searching for this topic
    """
    topic: str
    language: str

    # ── Writer output ──────────────────────────────────────────────────────────
    title:            str       = ""
    description:      str       = ""
    content_markdown: str       = ""
    tags:             List[str] = field(default_factory=list)

    # ── Critic evaluation ──────────────────────────────────────────────────────
    is_approved:      bool = False
    critic_feedback:  str  = ""
    retry_count:      int  = 0
    concreteness_score: int = 0  # 0-10, set by CriticAgent

    # ── Perspective Architecture (from Director via Orchestrator) ─────────────
    contrarian_angle: str = ""   # "VPNs don't protect privacy — they move the risk"
    unique_thesis:    str = ""   # "Most VPN users are paying for false confidence"
    target_audience:  str = ""   # "Remote workers who think they are already protected"

    # ── Research cache (Fix 2) ────────────────────────────────────────────────
    # ResearcherAgent runs ONCE and stores the result here.
    # Retries reuse this instead of re-running all HTTP calls.
    research_brief: object = None

    # ── Output ────────────────────────────────────────────────────────────────
    slug: str = ""

    def to_frontmatter(self) -> str:
        """Generates Astro-compatible frontmatter."""
        tags_str = "\n".join([f"  - {tag}" for tag in self.tags])

        # Include language in frontmatter (schema supports it as optional)
        lang_line = f'language: "{self.language}"\n' if self.language else ""

        return f"""---
title: "{self._escape(self.title)}"
description: "{self._escape(self.description)}"
date: CURRENT_DATETIME
{lang_line}tags:
{tags_str}
---
"""

    @staticmethod
    def _escape(text: str) -> str:
        """Escapes double quotes in frontmatter string values."""
        return text.replace('"', '\\"')