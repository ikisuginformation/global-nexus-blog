# ai_core/editor_agent.py
import requests
import json
import os
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL, BASE_DIR

class EditorAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.ads_db_path = os.path.join(BASE_DIR, "ai_core", "ads_database.json")
        self.ads_data = self._load_ads_database()

    def _load_ads_database(self):
        try:
            with open(self.ads_db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Editor Warning] 広告データベースの読み込みに失敗しました: {e}")
            return []

    def inject_affiliate_link(self, state: ArticleState) -> ArticleState:
        """
        記事のトピックと内容を分析し、最適なアフィリエイト広告を選択してMarkdownに挿入する。
        """
        if not self.ads_data:
            return state

        print("   ...Editorが商流（アフィリエイトリンク）の最適配置を計算中...")

        # 広告データをプロンプトに渡せる形式に変換
        ads_context = json.dumps(self.ads_data, ensure_ascii=False, indent=2)

        prompt = f"""
        You are an expert affiliate marketer and editor.
        Your task is to select the BEST matching affiliate product from the provided database and inject it naturally into the provided blog article.

        Target Language: {state.language}
        Article Topic: {state.topic}

        [AVAILABLE ADS DATABASE]
        {ads_context}

        [REQUIREMENTS]
        1. Read the Article Topic and select exactly ONE product from the database that is most relevant.
        2. Write a highly converting "Call to Action" (CTA) section in the Target Language ({state.language}).
        3. The CTA must include the product name and the affiliate link, formatted beautifully in Markdown (e.g., a quote block or a bold CTA button).
        4. Output strictly a JSON object containing the modified full markdown content.

        [OUTPUT REQUIREMENT]
        Output only JSON.
        {{
            "selected_ad_id": "The ID of the ad you chose",
            "modified_markdown": "The original content PLUS your new CTA section added at the end or in a logical place."
        }}
        """

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a specialized affiliate editor. Output only JSON."},
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            
            result_json = response.json()
            content_text = result_json.get("message", {}).get("content", "").strip()

            # JSONクレンジング
            if content_text.startswith("```json"): content_text = content_text[7:]
            if content_text.startswith("```"): content_text = content_text[3:]
            if content_text.endswith("```"): content_text = content_text[:-3]
            content_text = content_text.strip()

            data = json.loads(content_text)
            
            # Editorが広告を挿入したMarkdownで状態を上書き
            if "modified_markdown" in data and len(data["modified_markdown"]) > len(state.content_markdown) * 0.5:
                state.content_markdown = data["modified_markdown"]
                print(f"   [Editor Result] 広告 [{data.get('selected_ad_id', 'Unknown')}] の挿入完了。")
            
            return state

        except Exception as e:
            print(f"[Editor Error] 広告の挿入に失敗しました。元のテキストを維持します: {e}")
            return state