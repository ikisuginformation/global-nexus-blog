# ai_core/orchestrator.py
import os
import re
from datetime import datetime
from .models import ArticleState
from .config import OUTPUT_DIR, MAX_RETRY_COUNT
from .writer_agent import WriterAgent
from .critic_agent import CriticAgent
from .editor_agent import EditorAgent  # 新規追加

class Orchestrator:
    def __init__(self):
        self.writer = WriterAgent()
        self.critic = CriticAgent()
        self.editor = EditorAgent()    # 新規追加

    def slugify(self, text: str) -> str:
        """タイトルから安全なファイル名（スラグURL）を生成する"""
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        return text.strip('-')

    def execute_pipeline(self, strategy_data: dict, language: str) -> bool:
        """
        Directorが策定した戦略データに基づいて製造ラインを稼働させる。
        """
        topic = strategy_data["target_keyword"]
        title_idea = strategy_data["article_title"]
        monetization_type = strategy_data["monetization_route"]
        
        print(f"\n==================================================")
        print(f" [Orchestrator] 戦略的製造開始: {topic}")
        print(f" [Target] {title_idea} ({language})")
        print(f" [Money Route] {monetization_type}")
        print(f"==================================================")
        
        # Stateに戦略情報を引き継ぐ
        state = ArticleState(topic=topic, language=language)
        state.title = title_idea # Directorが決めたタイトルを初期値にする

        while state.retry_count < MAX_RETRY_COUNT:
            print(f"\n▶ 試行回数: {state.retry_count + 1} / {MAX_RETRY_COUNT}")
            
            # 1. Writer: 記事を書く（前回ダメだった場合はフィードバック付き）
            state = self.writer.generate_article(state)
            
            # 2. Editor: 広告（商流）を注入する
            # ※Writerが書き直すたびに、最適な広告を再選定して入れ直す
            state = self.editor.inject_affiliate_link(state)
            
            # 3. Critic: 広告込みの記事を監査する
            state = self.critic.evaluate_article(state)
            
            # 判定結果の処理
            if state.is_approved:
                print("   [Orchestrator] 監査クリア。ファイル出力へ移行します。")
                self._save_to_astro(state)
                return True
            else:
                state.retry_count += 1
                print(f"   [Orchestrator] 監査差し戻し。フィードバック: {state.critic_feedback}")
        
        print(f"\n[Orchestrator Fatal] {MAX_RETRY_COUNT}回の試行で品質基準を満たしませんでした。リソース保護のため記事を破棄します。")
        return False

    def _save_to_astro(self, state: ArticleState):
        """完成した記事をAstroの言語別ディレクトリに保存する"""
        
        # ★修正: 言語ごとのサブフォルダを作成 (例: src/content/blog/ja/)
        lang_dir = os.path.join(OUTPUT_DIR, state.language)
        os.makedirs(lang_dir, exist_ok=True)
        
        # URLスラグの生成
        slug = self.slugify(state.title)
        if not slug or len(slug) < 3:
            slug = f"article-{int(datetime.now().timestamp())}"
        
        filename = f"{slug}.md"
        filepath = os.path.join(lang_dir, filename) # 言語フォルダの中に保存

        # フロントマターの生成
        frontmatter = state.to_frontmatter()
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        frontmatter = frontmatter.replace("CURRENT_DATETIME", current_time)

        # ファイル書き込み
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write("\n")
            f.write(state.content_markdown)

        print(f"   [Orchestrator Success] 記事生成・保存完了: {state.language}/{filename}")