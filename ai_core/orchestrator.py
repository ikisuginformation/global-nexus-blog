# ai_core/orchestrator.py
#
# Orchestrator — Updated
#
# Changes from v1:
#   1. Passes contrarian_angle, unique_thesis, target_audience from strategy
#      into ArticleState so WriterAgent can use them
#   2. MAX_RETRY_COUNT enforced at 3 (not 100) with exponential backoff
#   3. Backoff between retries prevents hammering the local LLM
#   4. Language saved into frontmatter via state (schema already accepts it)

import os
import re
import time
from datetime import datetime
from .models import ArticleState
from .config import OUTPUT_DIR, MAX_RETRY_COUNT
from .writer_agent import WriterAgent
from .critic_agent import CriticAgent
from .editor_agent import EditorAgent

# Hard cap regardless of config — protects local compute
HARD_RETRY_CAP = 3

# Backoff in seconds between retries: [15s, 30s, 60s]
RETRY_BACKOFF = [15, 30, 60]


class Orchestrator:
    def __init__(self):
        self.writer = WriterAgent()
        self.critic = CriticAgent()
        self.editor = EditorAgent()

    def slugify(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        return text.strip('-')[:80]  # cap slug length

    def execute_pipeline(self, strategy_data: dict, language: str) -> bool:
        """
        Runs the full content pipeline for one strategy.
        
        Strategy data from Director now includes:
          - target_keyword
          - article_title
          - monetization_route
          - contrarian_angle    ← NEW: the non-obvious take
          - unique_thesis       ← NEW: the argument to defend
          - target_audience     ← NEW: who is searching
        """
        topic             = strategy_data["target_keyword"]
        title_idea        = strategy_data.get("article_title", topic)
        monetization_type = strategy_data.get("monetization_route", "AdSense")
        contrarian_angle  = strategy_data.get("contrarian_angle", "")
        unique_thesis     = strategy_data.get("unique_thesis", "")
        target_audience   = strategy_data.get("target_audience", "")

        print(f"\n{'='*50}")
        print(f" [Orchestrator] 製造開始: {topic}")
        print(f" [Lang] {language}  [Route] {monetization_type}")
        if contrarian_angle:
            print(f" [Angle] {contrarian_angle[:70]}")
        print(f"{'='*50}")

        # Build initial state with ALL strategy data
        state = ArticleState(topic=topic, language=language)
        state.title = title_idea

        # Attach perspective data to state so WriterAgent can access it
        state.contrarian_angle = contrarian_angle
        state.unique_thesis    = unique_thesis
        state.target_audience  = target_audience

        max_retries = min(MAX_RETRY_COUNT, HARD_RETRY_CAP)

        while state.retry_count < max_retries:
            attempt = state.retry_count + 1
            print(f"\n▶ 試行 {attempt} / {max_retries}")

            # 1. Write
            state = self.writer.generate_article(state)

            if not state.content_markdown:
                print("   [Orchestrator] Writer returned empty content. Retrying...")
                state.retry_count += 1
                state.critic_feedback = "Content was empty — generate a complete article."
                backoff = RETRY_BACKOFF[min(state.retry_count - 1, len(RETRY_BACKOFF) - 1)]
                time.sleep(backoff)
                continue

            # 2. Inject affiliate link
            state = self.editor.inject_affiliate_link(state)

            # 3. Audit
            state = self.critic.evaluate_article(state)

            if state.is_approved:
                print("   [Orchestrator] Audit passed → saving file")
                self._save_to_astro(state)
                return True
            else:
                state.retry_count += 1
                print(f"   [Orchestrator] Rejected: {state.critic_feedback}")
                if state.retry_count < max_retries:
                    backoff = RETRY_BACKOFF[min(state.retry_count - 1, len(RETRY_BACKOFF) - 1)]
                    print(f"   [Backoff {backoff}s...]")
                    time.sleep(backoff)

        print(f"\n[Orchestrator] Failed after {max_retries} attempts. Discarding.")
        return False, state

    def _save_to_astro(self, state: ArticleState):
        """
        Saves the completed article to the language-specific content directory.
        Path: src/content/blog/{language}/{slug}.md
        Astro slug will be: {language}/{slug} → URL: /blog/{language}/{slug}/
        """
        lang_dir = os.path.join(OUTPUT_DIR, state.language)
        os.makedirs(lang_dir, exist_ok=True)

        slug = self.slugify(state.title)
        if not slug or len(slug) < 3:
            slug = f"article-{int(datetime.now().timestamp())}"

        # Avoid filename collisions
        filepath = os.path.join(lang_dir, f"{slug}.md")
        if os.path.exists(filepath):
            filepath = os.path.join(lang_dir, f"{slug}-{int(datetime.now().timestamp())}.md")

        # Build frontmatter
        frontmatter = state.to_frontmatter()
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        frontmatter = frontmatter.replace("CURRENT_DATETIME", current_time)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write("\n")
            f.write(state.content_markdown)

        filename = os.path.basename(filepath)
        print(f"   [Saved] {state.language}/{filename}")