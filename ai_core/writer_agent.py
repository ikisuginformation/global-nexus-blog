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
        You are an elite tech journalist and authoritative subject-matter expert.
        Write a high-quality, in-depth blog post in strictly JSON format based on the following topic.

        Topic: {state.topic}
        Target Language: English

        {feedback_instruction}

        [CONTENT REQUIREMENTS — follow this structure precisely]

        1. OPENING HOOK (H1 title + first paragraph):
           - Write a bold, counter-intuitive, or surprising title that makes the reader need to know more.
           - The opening paragraph must immediately establish why this topic matters RIGHT NOW.
           - Keep it to 2-3 punchy sentences. No fluff.

        2. VISUAL RHYTHM throughout the article:
           - Use extremely short paragraphs (1-3 sentences each).
           - Use **bold text** to surface the most important ideas for skimmers.
           - Every H2/H3 should feel like a revelation, not a label.

        3. COMPARISON TABLE (required, under its own H2):
           - Include a Markdown table contrasting the old/conventional approach vs. the better/modern approach.
           - Use ❌ in the "Old Way" column and ✅ in the "New Way" column.
           - At least 4 rows of meaningful, specific comparisons.

        4. HONEST PROS & CONS (required, under its own H3):
           - Provide a bulleted Pros & Cons list.
           - Be genuinely balanced. Real cons build real trust — don't omit them or soften them artificially.

        5. FAQ SECTION (required, under its own H2 titled "Frequently Asked Questions"):
           - Include exactly 3 questions that a skeptical, intelligent reader would actually ask.
           - Answers must be direct and substantive — no vague non-answers.

        6. CLOSING:
           - End with a sharp, thought-provoking question or a single bold takeaway statement.
           - Do NOT use transitions like "In conclusion" or "To summarize".

        [FORMAT RULES]
        1. Output MUST be a valid JSON object. No markdown formatting outside the string values.
        2. The "content_markdown" must use H2 (##) and H3 (###) tags.
        3. Do NOT include any introductory text or explanations. Only the JSON.
        4. Write the entire article body in English, regardless of the topic language.

        [JSON STRUCTURE]
        {{
            "title": "Compelling, specific English title",
            "description": "SEO description max 120 chars, in English",
            "content_markdown": "Full article body in Markdown, in English",
            "tags": ["tag1", "tag2"]
        }}
        """

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert tech journalist. You output only valid JSON, exactly as instructed. No preamble, no explanation."},
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