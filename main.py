# main.py  v2
#
# Change from v1: publisher.publish_to_world() now receives the ArticleState
# object so it can build structured commit messages with analysis metadata.

import time
import random
import json
from ai_core.orchestrator import Orchestrator
from ai_core.director_agent import DirectorAgent
from ai_core.publisher_agent import PublisherAgent


def main():
    print("==================================================")
    print(" GLOBAL NEXUS: Autonomous Mining & Production v3.1")
    print("==================================================")

    director     = DirectorAgent()
    orchestrator = Orchestrator()
    publisher    = PublisherAgent()

    with open("ai_core/topics_database.json", "r", encoding="utf-8") as f:
        topics_data = json.load(f)

    TARGET_LANGUAGES = ["en", "ja", "es"]
    iteration = 1

    while True:
        print(f"\n[System] Mining Cycle {iteration} Initiated...")

        seed_topic = random.choice(topics_data["topics"])
        print(f"[Director] Selected seed: {seed_topic}")

        strategies = director.discover_targets(seed_topic=seed_topic)

        if not strategies:
            print("[System] No viable strategies found. Retrying in 10s...")
            time.sleep(10)
            continue

        print(f"[System] {len(strategies)} strategy/strategies acquired. Starting production.")

        for strat in strategies:
            lang = random.choice(TARGET_LANGUAGES)

            # execute_pipeline returns (success: bool, state: ArticleState)
            result = orchestrator.execute_pipeline(
                strategy_data=strat,
                language=lang
            )

            # Unpack — orchestrator returns tuple in v2
            if isinstance(result, tuple):
                success, state = result
            else:
                # Backwards compat if orchestrator still returns bool only
                success, state = result, None

            if success and state is not None:
                publisher.publish_to_world(state=state)
            elif success:
                # Fallback: no state returned
                publisher.publish_to_world(
                    commit_message=f"Auto-generate: {strat.get('target_keyword', 'unknown')} ({lang})"
                )

            if success:
                wait_time = random.randint(30, 60)
                print(f"[System] Next production in {wait_time}s...")
                time.sleep(wait_time)

        print("[System] Cycle complete. Waiting 120s before next market scan...")
        time.sleep(120)
        iteration += 1


if __name__ == "__main__":
    main()