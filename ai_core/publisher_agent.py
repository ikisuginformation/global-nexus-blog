# ai_core/publisher_agent.py
import subprocess
import os
from .config import BASE_DIR

class PublisherAgent:
    def __init__(self):
        self.repo_dir = BASE_DIR

    def publish_to_world(self, commit_message="Auto-publish new articles"):
        """
        生成されたコンテンツをGit経由で自動Pushし、Cloudflareのビルドをトリガーする。
        """
        print(f"\n🚀 [Publisher] 世界への公開（デプロイ）シーケンスを開始...")
        
        try:
            # 1. 変更されたファイルをすべてステージング
            subprocess.run(["git", "add", "."], cwd=self.repo_dir, check=True, stdout=subprocess.DEVNULL)
            
            # 変更があるか確認
            status = subprocess.run(["git", "status", "--porcelain"], cwd=self.repo_dir, capture_output=True, text=True)
            if not status.stdout.strip():
                print("   [Publisher] 新規アップロードする変更がありません。スキップします。")
                return True

            # 2. コミット
            subprocess.run(["git", "commit", "-m", commit_message], cwd=self.repo_dir, check=True, stdout=subprocess.DEVNULL)
            
            # 3. リモートリポジトリ（GitHub等）へPush
            print("   ...リモートサーバーへデータを転送中...")
            subprocess.run(["git", "push", "origin", "main"], cwd=self.repo_dir, check=True, stdout=subprocess.DEVNULL)
            
            print("   [Publisher Success] 🌍 デプロイ完了！Cloudflareでのビルドが自動開始されました。")
            return True

        except subprocess.CalledProcessError as e:
            print(f"   [Publisher Error] Gitコマンドの実行に失敗しました: {e}")
            return False
        except FileNotFoundError:
            print("   [Publisher Error] 'git' コマンドが見つかりません。Gitがインストールされているか確認してください。")
            return False