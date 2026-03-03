# ai_core/publisher_agent.py  v2
#
# Change from v1: publish_to_world() now accepts an ArticleState object
# and builds a structured commit message with full metadata.
#
# Commit message format (6 months of these = queryable analysis dataset):
#
#   [en] Why NordVPN Is Making Your Privacy Worse
#
#   lang: en
#   model: llama3.1
#   retries: 0
#   concreteness: 7/10
#   tags: VPN, Privacy, Security
#   topic: vpn privacy risks remote work
#   angle: VPNs shift risk rather than eliminate it
#
# This gives you a git log you can grep, analyze, and correlate with
# Cloudflare Analytics traffic data to answer:
# "Which model/retry-count/concreteness combination produces ranking articles?"

import subprocess
import os
from .models import ArticleState
from .config import BASE_DIR, OLLAMA_MODEL


class PublisherAgent:
    def __init__(self):
        self.repo_dir = BASE_DIR

    def publish_to_world(self, state: ArticleState = None, commit_message: str = None):
        """
        Publishes to GitHub, triggering Cloudflare auto-build.

        Args:
            state:          ArticleState object (preferred — enables rich commits)
            commit_message: Plain string fallback (legacy support)
        """
        print(f"\n🚀 [Publisher] Deploy sequence starting...")

        # Build commit message
        if state is not None:
            msg = self._build_commit_message(state)
        elif commit_message:
            msg = commit_message
        else:
            msg = "Auto-publish: content update"

        try:
            # 1. Stage all changes
            subprocess.run(
                ["git", "add", "."],
                cwd=self.repo_dir,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # 2. Check if there is anything to commit
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True
            )
            if not status.stdout.strip():
                print("   [Publisher] No changes to commit. Skipping.")
                return True

            # 3. Commit with structured message
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self.repo_dir,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # 4. Push to remote → triggers Cloudflare build
            print("   ...Pushing to remote...")
            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=self.repo_dir,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            print("   [Publisher] ✅ Deployed. Cloudflare build triggered.")
            return True

        except subprocess.CalledProcessError as e:
            print(f"   [Publisher Error] Git command failed: {e}")
            return False
        except FileNotFoundError:
            print("   [Publisher Error] git not found. Is Git installed?")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Commit message builder
    # ─────────────────────────────────────────────────────────────────────────

    def _build_commit_message(self, state: ArticleState) -> str:
        """
        Builds a structured commit message from ArticleState.
        Designed to be grep-able and machine-parseable for later analysis.

        Format:
            [lang] Title (truncated to 60 chars)

            lang: en
            model: llama3.1
            retries: 0
            concreteness: 7/10
            tags: VPN, Privacy
            topic: vpn privacy risks
            angle: VPNs shift risk rather than eliminate it
        """
        # Subject line: language tag + truncated title
        lang_tag = f"[{state.language}]" if state.language else "[??]"
        title    = (state.title or "untitled")[:60]
        subject  = f"{lang_tag} {title}"

        # Body: structured metadata
        tags_str      = ", ".join(state.tags[:5]) if state.tags else "none"
        conc_score    = getattr(state, 'concreteness_score', 0)
        retries       = getattr(state, 'retry_count', 0)
        topic         = getattr(state, 'topic', '')[:80]
        angle         = getattr(state, 'contrarian_angle', '')[:100]

        body = (
            f"\n"
            f"lang: {state.language}\n"
            f"model: {OLLAMA_MODEL}\n"
            f"retries: {retries}\n"
            f"concreteness: {conc_score}/10\n"
            f"tags: {tags_str}\n"
        )
        if topic:
            body += f"topic: {topic}\n"
        if angle:
            body += f"angle: {angle}\n"

        return subject + body