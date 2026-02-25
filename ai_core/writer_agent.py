# ai_core/writer_agent.py
import requests
import json
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL

class WriterAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL

    def generate_article(self, state: ArticleState) -> ArticleState:
        """
        Ollama APIを直接叩いて記事を生成する（公式ライブラリ不使用版）
        """
        
        # 1. 監査役（Critic）からのフィードバックをプロンプトに注入
        feedback_instruction = ""
        if state.retry_count > 0:
            feedback_instruction = f"""
            [CRITICAL FEEDBACK FROM AUDITOR - YOU MUST FIX THIS]
            Previous attempt failed. Reason: {state.critic_feedback}
            Please strictly address this issue in this rewrite.
            """

        # 2. メインプロンプトの構築
        prompt = f"""
        You are a world-class SEO web writer.
        Write a blog post in strictly JSON format based on the following topic.

        Topic: {state.topic}
        Target Language: {state.language}

        {feedback_instruction}

        [REQUIREMENTS]
        1. Output MUST be a valid JSON object. No markdown formatting outside the string values.
        2. The "content_markdown" must use H2 (##) and H3 (###) tags.
        3. Do NOT include any introductory text or explanations. Only the JSON.

        [JSON STRUCTURE]
        {{
            "title": "Catchy SEO Title in Target Language",
            "description": "SEO description max 120 chars",
            "content_markdown": "Full article body in Markdown",
            "tags": ["tag1", "tag2"]
        }}
        """

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that outputs only JSON."},
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False
        }

        try:
            print(f"   ...Ollama ({self.model}) に執筆リクエスト送信中...")
            
            response = requests.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status() 
            
            result_json = response.json()
            content_text = result_json.get("message", {}).get("content", "")

            # 3. OllamaのJSON揺らぎ（マークダウンブロック等）をクレンジング
            content_text = content_text.strip()
            if content_text.startswith("```json"):
                content_text = content_text[7:]
            if content_text.startswith("```"):
                content_text = content_text[3:]
            if content_text.endswith("```"):
                content_text = content_text[:-3]
            content_text = content_text.strip()

            # JSONテキストをPythonの辞書に変換
            data = json.loads(content_text)
            
            # ArticleStateに生成結果を格納
            state.title = data.get("title", f"Draft: {state.topic}")
            state.description = data.get("description", "")
            state.content_markdown = data.get("content_markdown", "")
            state.tags = data.get("tags", ["AI", "Tech", "Web3"])
            
            return state

        except json.JSONDecodeError:
            print(f"[Writer Error] Ollamaが不正なJSONを返しました。生の出力: {content_text[:100]}...")
            return state
        except Exception as e:
            print(f"[Writer Error] 通信エラー: {e}")
            return state