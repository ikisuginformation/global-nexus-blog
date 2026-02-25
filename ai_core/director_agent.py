# ai_core/director_agent.py
import json
import requests
import random
import xml.etree.ElementTree as ET
from .config import OLLAMA_HOST, OLLAMA_MODEL

class DirectorAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL

    def discover_targets(self, seed_topic: str = None) -> list:
        """
        戦略ターゲットを発掘する（ライブラリ非依存・軽量版）。
        Google TrendsのRSSフィードを直接解析してトレンドを取得する。
        """
        candidates = []
        
        print(f"\n🕵️ [Director] 市場調査を開始... (Mode: {'Expansion' if seed_topic else 'Mining'})")

        try:
            if seed_topic:
                # 特定テーマがある場合は、LLMの知識で関連ワードを広げる
                # （RSSでは特定ワードの検索ができないため、ここをAIの推論に切り替え）
                print(f"   ...'{seed_topic}' に関連するニッチ需要をAIが推論中...")
                candidates = self._brainstorm_with_llm(seed_topic)
            else:
                # 完全自律：各国のGoogle Trends RSSフィードからリアルタイムデータを取得
                target_geo = random.choice(['US', 'JP', 'GB']) # アメリカ、日本、イギリス
                rss_url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={target_geo}"
                
                print(f"   ...Google Trends RSS ({target_geo}) にアクセス中...")
                response = requests.get(rss_url)
                
                if response.status_code == 200:
                    # XMLを解析してタイトル（キーワード）を抽出
                    root = ET.fromstring(response.content)
                    # RSSの構造: channel -> item -> title
                    for item in root.findall('.//item'):
                        title = item.find('title').text
                        candidates.append(title)
                else:
                    print(f"   [Director Warning] RSS取得失敗: Status {response.status_code}")
                    # 失敗時はAI推論へフォールバック
                    candidates = self._brainstorm_with_llm("latest technology trends")

        except Exception as e:
            print(f"[Director Warning] トレンド取得エラー: {e}")
            candidates = self._brainstorm_with_llm(seed_topic)

        # 重複削除とリスト整理（上位10個）
        candidates = list(set(candidates))[:10]
        print(f"   ...候補キーワード: {candidates}")
        
        # 候補の中から「金になる」キーワードだけを精密検査する
        verified_targets = []
        for kw in candidates:
            strategy = self._evaluate_viability(kw)
            if strategy:
                verified_targets.append(strategy)
                
        return verified_targets

    def _brainstorm_with_llm(self, seed_topic):
        """外部データが取れない場合のAIブレインストーミング"""
        base = seed_topic if seed_topic else "viral tech trends 2026"
        prompt = f"""
        List 5 specific, high-traffic, low-competition niche keywords related to: "{base}".
        Output strictly a JSON list of strings. Example: ["keyword1", "keyword2"]
        """
        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "format": "json",
                "stream": False
            }
            res = requests.post(f"{self.host}/api/chat", json=payload)
            data = json.loads(res.json()['message']['content'])
            if isinstance(data, list):
                return data
            elif "keywords" in data:
                return data["keywords"]
            return []
        except:
            return [base]

    def _evaluate_viability(self, keyword: str):
        """
        キーワードの収益性（CPC, KD）をLLMに推定させ、
        GOサインが出れば具体的な戦略（記事構成・マネタイズ・SNS）を立案する。
        """
        print(f"   ...分析中: {keyword}")
        
        prompt = f"""
        You are a Strategic SEO Director. Analyze this keyword: "{keyword}".

        [CRITERIA]
        1. Is this a "Micro-Niche" with low competition (KD < 20 estimated)?
        2. Is there commercial intent (CPC > $1.00 estimated)?
        3. Can we monetize this via Ads, Affiliates, or Digital Products?

        [TASK]
        If it meets the criteria, create a full content strategy JSON.
        If it is trash (too competitive, no money), return NULL.

        [OUTPUT FORMAT - JSON ONLY]
        {{
            "is_viable": true,
            "target_keyword": "{keyword}",
            "estimated_intent": "Informational/Transactional",
            "monetization_route": "AdSense" or "Affiliate (SaaS)" or "Digital Product",
            "article_title": "The exact killer title for the blog post",
            "video_idea": "A short description for a TikTok/Reels video",
            "target_audience": "Who is searching for this?"
        }}
        """

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            
            # JSONクレンジング
            content = response.json()['message']['content'].strip()
            if content.startswith("```json"): content = content[7:]
            if content.startswith("```"): content = content[3:]
            if content.endswith("```"): content = content[:-3]
            
            data = json.loads(content.strip())
            
            if data.get("is_viable") is True:
                print(f"   💰 [Approved] 承認: {keyword} (Route: {data.get('monetization_route')})")
                return data
            else:
                print(f"   🗑️ [Rejected] 却下: {keyword} (低収益または高競合)")
                return None
                
        except Exception:
            return None