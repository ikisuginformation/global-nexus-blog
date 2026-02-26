# ai_core/critic_agent.py
import requests
import json
from .models import ArticleState
from .config import OLLAMA_HOST, OLLAMA_MODEL

class CriticAgent:
    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL

    def evaluate_article(self, state: ArticleState) -> ArticleState:
        """
        生成された記事がSEO基準とAstroのビルド要件を満たしているか評価する。
        """
        print("   ...Criticによる厳格な監査プロセスを開始...")

        # 1. ハードコードされた物理チェック（LLMを呼び出す前の足切り）
        if not state.title or not state.content_markdown:
            state.is_approved = False
            state.critic_feedback = "タイトルまたは本文が空です。"
            return state

        if len(state.title) > 100:
            state.is_approved = False
            state.critic_feedback = f"タイトルが長すぎます（現在{len(state.title)}文字）。100文字以内に短縮してください。"
            return state

        if len(state.description) > 160:
            state.is_approved = False
            state.critic_feedback = f"Descriptionが長すぎます（現在{len(state.description)}文字）。120文字以内に要約してください。"
            return state

        if "## " not in state.content_markdown:
            state.is_approved = False
            state.critic_feedback = "MarkdownのH2見出し（## ）が一つも含まれていません。論理的な構造に修正してください。"
            return state

        # 2. LLMによる定性チェック（文脈、不自然な表現、魅力度の評価）
        prompt = f"""
        You are a strict SEO auditor and technical editor.
        Review the following blog article data and evaluate if it is ready for publishing.

        Target Language: {state.language}
        Title: {state.title}
        Description: {state.description}
        Content Snippet (First 500 chars): {state.content_markdown[:500]}...

        [EVALUATION CRITERIA]
        1. LANGUAGE: The text MUST be in the Target Language ({state.language}). Do NOT request English if the Target Language is not English.
        2. TITLE: Is it catchy and clickable in the Target Language?
        3. DESCRIPTION: Is it clear and concise?
        4. CONTENT: Does it start engagingly without weird AI-like phrases?

        [IMPORTANT]
        Do NOT be an extreme perfectionist. If the article is generally well-structured, written in the correct Target Language, and has no critical errors, you MUST approve it.

        [OUTPUT REQUIREMENT]
        Return strictly in JSON format.
        {{
            "is_approved": true/false,
            "critic_feedback": "Your specific feedback. If approved, just write 'Perfect'."
        }}
        """

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict code and text auditor. Output only JSON."},
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            
            result_json = response.json()
            content_text = result_json.get("message", {}).get("content", "")
            data = json.loads(content_text)
            
            # 評価結果をStateに反映
            state.is_approved = data.get("is_approved", False)
            state.critic_feedback = data.get("critic_feedback", "JSON解析エラーによる不合格")

            if state.is_approved:
                print("   [Critic Result] 監査合格 (Approved)")
            else:
                print(f"   [Critic Result] 監査不合格 (Rejected): {state.critic_feedback}")

            return state

        except Exception as e:
            print(f"[Critic Error] 監査APIエラー: {e}")
            state.is_approved = False
            state.critic_feedback = "監査システムのエラーにより再試行を要求します。"
            return state