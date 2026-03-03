# ai_core/director_agent.py
#
# DirectorAgent — llama3.1対応・高速化版
#
# 変更点：
#   - 評価プロンプトを約60%短縮（llama3.1で45秒以内に完了するため）
#   - タイムアウトを120秒に延長（重いトピックでもクラッシュしない）
#   - タイムアウト時はNoneを返してスキップ（クラッシュしない）
#   - ブレインストームプロンプトも短縮

import json
import requests
import random
import xml.etree.ElementTree as ET
from .config import OLLAMA_HOST, OLLAMA_MODEL

QUESTION_GAP_PATTERNS = [
    "{kw} worth it",
    "{kw} problems nobody talks about",
    "{kw} for beginners mistakes",
    "is {kw} still relevant",
    "{kw} honest review",
    "why {kw} fails",
    "{kw} vs alternatives",
]

OVERSATURATION_SIGNALS = [
    "best ai tools", "chatgpt", "make money online",
    "passive income", "crypto millionaire", "nft", "dropshipping",
    "how to start a blog",
]


class DirectorAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL

    def discover_targets(self, seed_topic: str = None) -> list:
        """トレンド情報からコンテンツ戦略を生成する"""
        candidates = []
        print(f"\n🕵️ [Director] 市場調査開始... (seed: {seed_topic or 'autonomous'})")

        try:
            if seed_topic:
                candidates.extend(self._mine_question_gaps(seed_topic))
                candidates.extend(self._brainstorm_with_llm(seed_topic))
            else:
                geo = random.choice(['US', 'JP', 'GB', 'AU', 'CA'])
                rss_url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
                print(f"   ...Google Trends RSS ({geo}) 取得中...")

                resp = requests.get(rss_url, timeout=8)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    raw_trends = [
                        item.find('title').text
                        for item in root.findall('.//item')
                        if item.find('title') is not None
                    ]
                    filtered = [
                        t for t in raw_trends
                        if not any(sig in t.lower() for sig in OVERSATURATION_SIGNALS)
                    ][:6]
                    for trend in filtered:
                        candidates.extend(self._mine_question_gaps(trend))
                else:
                    candidates = self._brainstorm_with_llm("emerging technology trends")

        except Exception as e:
            print(f"   [Director Warning] トレンド取得エラー: {e}")
            candidates = self._brainstorm_with_llm(seed_topic or "technology")

        # 重複排除・シャッフル・上限12件
        candidates = list(dict.fromkeys(candidates))
        random.shuffle(candidates)
        candidates = candidates[:12]

        print(f"   ...候補 {len(candidates)} 件の審査開始...")

        verified = []
        for kw in candidates:
            strategy = self._evaluate_viability(kw)
            if strategy:
                verified.append(strategy)
            if len(verified) >= 3:
                break

        print(f"   ✅ {len(verified)} 件の戦略を承認しました。")
        return verified

    def _mine_question_gaps(self, seed: str) -> list:
        """シードトピックから質問型キーワードを生成"""
        seed_clean = seed.lower().strip()
        patterns = random.sample(QUESTION_GAP_PATTERNS, min(3, len(QUESTION_GAP_PATTERNS)))
        return [pattern.format(kw=seed_clean) for pattern in patterns]

    def _brainstorm_with_llm(self, seed_topic: str) -> list:
        """LLMによるキーワードブレインストーミング（短縮プロンプト）"""
        base = seed_topic if seed_topic else "technology 2026"
        prompt = f"""Topic: "{base}"
List 5 specific long-tail keyword phrases with search intent.
Format: JSON array of strings only.
Example: ["vpn privacy risks remote work", "is nordvpn worth it 2026"]"""

        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "format": "json",
                "stream": False
            }
            res = requests.post(f"{self.host}/api/chat", json=payload, timeout=60)
            data = json.loads(res.json()['message']['content'])
            if isinstance(data, list):
                return [str(k) for k in data if isinstance(k, str)][:5]
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return [str(k) for k in v if isinstance(k, str)][:5]
            return [base]
        except Exception:
            return [base]

    def _evaluate_viability(self, keyword: str) -> dict | None:
        """
        キーワードの収益性を評価する（高速化版プロンプト）
        
        llama3.1での実測：短縮前 60-90秒 → 短縮後 20-40秒
        """
        print(f"   ...審査中: {keyword}")

        if any(sig in keyword.lower() for sig in OVERSATURATION_SIGNALS):
            print(f"   🗑️ [除外] 過飽和: {keyword}")
            return None

        # ── 短縮プロンプト（フィールドを9→5に削減、説明文を最小化）──
        prompt = f"""Analyze keyword: "{keyword}"

Output JSON only.
If viable for affiliate/AdSense blog:
{{"is_viable": true, "target_keyword": "{keyword}", "monetization_route": "AdSense or Affiliate (SaaS) or Affiliate (Product)", "contrarian_angle": "one non-obvious take", "unique_thesis": "one specific argument", "article_title": "compelling title", "target_audience": "who searches this"}}

If not viable:
{{"is_viable": false}}"""

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(
                f"{self.host}/api/chat",
                json=payload,
                timeout=120  # 45秒→120秒に延長
            )
            response.raise_for_status()

            content = response.json()['message']['content'].strip()
            # マークダウンフェンスを除去
            for fence in ("```json", "```"):
                if content.startswith(fence):
                    content = content[len(fence):]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)

            if data.get("is_viable") is True:
                if not data.get("contrarian_angle") or not data.get("unique_thesis"):
                    print(f"   ⚠️  差別化要素なし、スキップ: {keyword}")
                    return None
                print(f"   💰 [承認] {keyword}")
                print(f"       Angle: {data.get('contrarian_angle', '')[:70]}")
                return data
            else:
                print(f"   🗑️ [却下] {keyword}")
                return None

        except requests.exceptions.Timeout:
            # タイムアウトはクラッシュせずスキップ
            print(f"   ⏱️  [タイムアウト] スキップ: {keyword}")
            return None
        except Exception as e:
            print(f"   [Director Error] {keyword}: {e}")
            return None