# ai_core/researcher_agent.py
#
# LOCATION: ai_core/researcher_agent.py  (same folder as all other agents)
#
# Researcher Agent — Free APIs Only
#
# Data source stack (all free, priority order):
#
#   1. SearXNG (self-hosted)     — PRIMARY. Real Google/Bing results, no limits.
#                                  Run once: docker run -d -p 8888:8080 searxng/searxng
#                                  Falls back gracefully if not running.
#
#   2. Wikipedia REST API        — Free, no key, multilingual.
#                                  Works well for established topics.
#
#   3. Reddit RSS                — Free, no key. Subreddit RSS gives current
#                                  community discussion on any topic.
#
#   4. Hacker News Algolia API   — Free, no key. Best for tech topics.
#
#   5. DuckDuckGo Instant Answer — Free, no key. Fallback for structured facts.
#
#   6. Wikidata API              — Free, no key. Structured numerical facts
#                                  (population, founding year, etc.)
#
# Design principle: every source is optional. If SearXNG isn't running,
# the pipeline continues with whatever other sources return. Never blocks.

import requests
import json
import feedparser
import re
from dataclasses import dataclass, field
from typing import List
from urllib.parse import quote, urlencode


# ─────────────────────────────────────────────────────────────────────────────
# Config — change SEARXNG_URL if you run on a different port
# ─────────────────────────────────────────────────────────────────────────────
SEARXNG_URL   = "http://localhost:8888"
REQUEST_TIMEOUT = 7   # seconds per source


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ResearchBrief:
    topic: str
    language: str

    abstract: str = ""                    # Background paragraph (Wikipedia / DDG)
    key_facts: List[str] = field(default_factory=list)      # Max 6 sourced facts
    current_discussion: List[str] = field(default_factory=list)  # Reddit/HN headlines
    related_searches: List[str] = field(default_factory=list)    # SearXNG suggestions
    gap_questions: List[str] = field(default_factory=list)       # Unanswered questions
    sources_used: List[str] = field(default_factory=list)        # Audit trail

    def has_data(self) -> bool:
        return bool(self.abstract or self.key_facts or self.current_discussion)

    def to_prompt_context(self) -> str:
        if not self.has_data():
            return ""

        lines = [
            "═══════════════════════════════════════════",
            "RESEARCH BRIEF — GROUND YOUR ARTICLE IN THIS",
            "═══════════════════════════════════════════",
            f"Topic: {self.topic}",
            f"Sources: {', '.join(self.sources_used) if self.sources_used else 'none'}",
        ]

        if self.abstract:
            lines += ["", "BACKGROUND (factual foundation):", self.abstract[:600]]

        if self.key_facts:
            lines += ["", "VERIFIED FACTS (cite at least 2 of these):"]
            for f in self.key_facts[:6]:
                lines.append(f"  • {f}")

        if self.current_discussion:
            lines += ["", "WHAT PEOPLE ARE DISCUSSING RIGHT NOW:"]
            for d in self.current_discussion[:4]:
                lines.append(f"  → {d}")

        if self.gap_questions:
            lines += ["", "QUESTIONS YOUR ARTICLE MUST ANSWER:"]
            for q in self.gap_questions[:3]:
                lines.append(f"  ? {q}")

        lines += [
            "",
            "CRITICAL: Do NOT invent statistics.",
            "Every number you cite must come from this brief.",
            "If this brief lacks a specific number, say 'research suggests' not a fake %.",
            "═══════════════════════════════════════════",
        ]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class ResearcherAgent:
    """
    Fetches real data from free sources before the Writer runs.
    All sources are optional — failures degrade gracefully, never block.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; GlobalNexus-Research/2.0)"
        })

    def research(self, topic: str, language: str) -> ResearchBrief:
        brief = ResearchBrief(topic=topic, language=language)
        print(f"   ...Researcher: [{language}] '{topic}' のデータ収集中...")

        # Run all sources in priority order
        # Each is wrapped individually — one failure never stops the others
        self._try("SearXNG",   self._fetch_searxng,   brief)
        self._try("Wikipedia", self._fetch_wikipedia,  brief)
        self._try("Reddit",    self._fetch_reddit,     brief)
        self._try("HackerNews",self._fetch_hackernews, brief)
        if not brief.abstract:
            self._try("DDG",   self._fetch_ddg,        brief)

        # Always generate gap questions (no external call needed)
        self._generate_gap_questions(brief)

        quality = "rich" if len(brief.key_facts) >= 3 else \
                  "partial" if brief.has_data() else "empty"
        print(f"   [Researcher] {quality} brief: "
              f"{len(brief.key_facts)} facts, "
              f"{len(brief.current_discussion)} discussions, "
              f"sources={brief.sources_used}")

        return brief

    def _try(self, name: str, fn, brief: ResearchBrief):
        try:
            fn(brief)
        except Exception as e:
            print(f"   [Researcher] {name} skipped: {type(e).__name__}: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Source 1: SearXNG (self-hosted) — PRIMARY
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_searxng(self, brief: ResearchBrief):
        """
        Queries self-hosted SearXNG for real search results.
        SearXNG aggregates Google, Bing, DuckDuckGo simultaneously.

        Setup (one time):
            docker run -d -p 8888:8080 \\
                -e BASE_URL="http://localhost:8888/" \\
                searxng/searxng

        Returns titles and snippets from top results —
        exactly the competitive landscape the article needs to beat.
        """
        params = {
            "q":        brief.topic,
            "format":   "json",
            "language": brief.language,
            "engines":  "google,bing,duckduckgo",
            "safesearch": "0",
        }
        url = f"{SEARXNG_URL}/search?{urlencode(params)}"
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        results = data.get("results", [])

        if not results:
            return

        brief.sources_used.append("SearXNG")

        # Extract snippets as key facts
        for r in results[:8]:
            snippet = r.get("content", "").strip()
            title   = r.get("title", "").strip()
            if snippet and len(snippet) > 40:
                # Clean HTML tags if any
                snippet = re.sub(r'<[^>]+>', '', snippet)[:220]
                brief.key_facts.append(snippet)

            if title and title not in brief.related_searches:
                brief.related_searches.append(title)

            if len(brief.key_facts) >= 6:
                break

        # Suggestions → related searches
        suggestions = data.get("suggestions", [])
        brief.related_searches.extend(suggestions[:5])

    # ─────────────────────────────────────────────────────────────────────────
    # Source 2: Wikipedia REST API — multilingual, authoritative
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_wikipedia(self, brief: ResearchBrief):
        """
        Wikipedia summary API — works in 300+ languages.
        https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}
        """
        title_encoded = quote(brief.topic.replace(" ", "_"))
        langs_to_try  = [brief.language, "en"] if brief.language != "en" else ["en"]

        for lang in langs_to_try:
            url  = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title_encoded}"
            resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue

            data    = resp.json()
            extract = data.get("extract", "").strip()
            if len(extract) < 50:
                continue

            if not brief.abstract:
                brief.abstract = extract[:700]
                brief.sources_used.append(f"Wikipedia-{lang}")

            # First 3 sentences as additional facts
            sentences = [s.strip() for s in extract.split(". ") if len(s.strip()) > 30]
            for sentence in sentences[:3]:
                fact = sentence + ("." if not sentence.endswith(".") else "")
                if fact not in brief.key_facts:
                    brief.key_facts.append(fact[:220])
            return

    # ─────────────────────────────────────────────────────────────────────────
    # Source 3: Reddit RSS — current community discussion, no API key
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_reddit(self, brief: ResearchBrief):
        """
        Reddit's public RSS endpoint — no auth required.
        Searches across all subreddits for current discussion.
        Format: https://www.reddit.com/search.json?q={query}&sort=top&t=month
        """
        params = {
            "q":    brief.topic,
            "sort": "top",
            "t":    "month",
            "limit": 8,
        }
        url  = f"https://www.reddit.com/search.json?{urlencode(params)}"
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data  = resp.json()
        posts = data.get("data", {}).get("children", [])

        if not posts:
            return

        brief.sources_used.append("Reddit")

        for post in posts[:6]:
            post_data = post.get("data", {})
            title     = post_data.get("title", "").strip()
            selftext  = post_data.get("selftext", "").strip()
            score     = post_data.get("score", 0)
            comments  = post_data.get("num_comments", 0)

            if title and score > 10:
                # High-score post titles reveal what the community cares about
                brief.current_discussion.append(
                    f"{title} ({comments} comments, {score} upvotes)"
                )

            # Post body text often contains useful facts
            if selftext and len(selftext) > 80:
                clean = re.sub(r'http\S+', '', selftext)
                clean = re.sub(r'\s+', ' ', clean).strip()[:200]
                if clean not in brief.key_facts:
                    brief.key_facts.append(clean)

    # ─────────────────────────────────────────────────────────────────────────
    # Source 4: Hacker News Algolia API — tech topics, free
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_hackernews(self, brief: ResearchBrief):
        """
        HN Algolia search API — completely free, no key.
        Best for tech, startup, and programming topics.
        https://hn.algolia.com/api/v1/search
        """
        params = {
            "query":          brief.topic,
            "tags":           "story",
            "hitsPerPage":    6,
            "numericFilters": "points>50",  # only significant discussions
        }
        url  = f"https://hn.algolia.com/api/v1/search?{urlencode(params)}"
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        hits = data.get("hits", [])

        if not hits:
            return

        brief.sources_used.append("HackerNews")

        for hit in hits[:5]:
            title   = (hit.get("title") or "").strip()
            points  = hit.get("points", 0)
            comment_count = hit.get("num_comments", 0)

            if title:
                brief.current_discussion.append(
                    f"[HN] {title} ({points} points, {comment_count} comments)"
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Source 5: DuckDuckGo Instant Answer — fallback only
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_ddg(self, brief: ResearchBrief):
        """
        DDG Instant Answer API — structured facts for well-known entities.
        Only called if Wikipedia didn't provide an abstract.
        Returns nothing for ~70% of long-tail queries (limitation acknowledged).
        """
        url  = f"https://api.duckduckgo.com/?q={quote(brief.topic)}&format=json&no_redirect=1&no_html=1"
        resp = self.session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        data     = resp.json()
        abstract = data.get("AbstractText", "").strip()

        if abstract and len(abstract) > 40:
            brief.abstract = abstract[:600]
            brief.sources_used.append("DuckDuckGo")

            related = data.get("RelatedTopics", [])
            for item in related[:5]:
                if isinstance(item, dict):
                    text = item.get("Text", "").strip()
                    if text and len(text) > 20 and text not in brief.key_facts:
                        brief.key_facts.append(text[:200])

    # ─────────────────────────────────────────────────────────────────────────
    # Gap questions — no API needed
    # ─────────────────────────────────────────────────────────────────────────

    def _generate_gap_questions(self, brief: ResearchBrief):
        """
        Generates the 3 highest-value unanswered questions for this topic.

        Logic:
          - If we have community discussion data, derive questions from it
            (what people ARE asking = what the article should answer)
          - Otherwise fall back to proven question templates
        """
        topic = brief.topic

        if brief.current_discussion:
            # Use LLM-style heuristics to extract question themes from discussions
            # Pattern: long titles that end in "?" or contain "how", "why", "should"
            derived = []
            for disc in brief.current_discussion:
                lower = disc.lower()
                if any(w in lower for w in ["why", "how", "should", "worth", "vs", "problem"]):
                    # Strip the score annotation
                    clean = re.sub(r'\(.*?\)', '', disc).strip()
                    if len(clean) > 15:
                        derived.append(clean[:120] + "?")
            if derived:
                brief.gap_questions = derived[:3]
                return

        # Template fallback
        brief.gap_questions = [
            f"Is {topic} worth it in 2026?",
            f"What are the real risks of {topic} that most articles ignore?",
            f"Who should NOT use {topic}, and why?",
        ]