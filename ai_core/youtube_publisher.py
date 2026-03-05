# ai_core/youtube_publisher.py
#
# YouTubePublisher — YouTube Shorts 自動投稿
#
# 依存ライブラリのインストール:
#   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
#
# セットアップ手順（一度だけ）:
#   1. https://console.cloud.google.com にアクセス
#   2. 新しいプロジェクト作成 → 「YouTube Data API v3」を有効化
#   3. 認証情報 → OAuth 2.0 クライアントID → デスクトップアプリ を選択
#   4. client_secrets.json をダウンロード
#   5. ai_core/credentials/ フォルダに置く
#   6. python -m ai_core.youtube_publisher --setup を実行（初回認証）
#
# 認証後は token.json が生成され、以降は自動的にログインされる。

import os
import json
import pickle
import sys
from pathlib import Path

CREDENTIALS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials")
CLIENT_SECRETS  = os.path.join(CREDENTIALS_DIR, "client_secrets.json")
TOKEN_PATH      = os.path.join(CREDENTIALS_DIR, "youtube_token.pickle")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# YouTube Shorts 条件:
#   - 縦型 (9:16)
#   - 60秒以内
#   - タイトルに #Shorts を含める OR 説明欄に #Shorts

SHORTS_TAG = "#Shorts"


class YouTubePublisher:
    def __init__(self):
        os.makedirs(CREDENTIALS_DIR, exist_ok=True)
        self._service = None

    # ─────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────

    def upload_short(self, video_path: str, script_path: str) -> str | None:
        """
        動画ファイルとスクリプトJSONからYouTube Shortsにアップロード。

        Returns: YouTube video ID (例: "dQw4w9WgXcQ"), または None（失敗時）
        """
        if not os.path.exists(video_path):
            print(f"   [YouTube] 動画ファイルが見つかりません: {video_path}")
            return None

        # スクリプトJSON読み込み
        script = {}
        if os.path.exists(script_path):
            with open(script_path, encoding="utf-8") as f:
                script = json.load(f)

        # メタデータ構築
        title       = self._build_title(script)
        description = self._build_description(script)
        tags        = self._build_tags(script)

        print(f"   [YouTube] アップロード中: {title[:60]}")

        service = self._get_service()
        if not service:
            return None

        try:
            from googleapiclient.http import MediaFileUpload

            body = {
                "snippet": {
                    "title":       title,
                    "description": description,
                    "tags":        tags,
                    "categoryId":  "28",  # Science & Technology
                    "defaultLanguage": script.get("language", "en"),
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False,
                },
            }

            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=1024 * 1024 * 5,  # 5MB chunks
            )

            request = service.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    print(f"   [YouTube] アップロード中... {pct}%", end="\r")

            video_id = response["id"]
            url = f"https://www.youtube.com/shorts/{video_id}"
            print(f"\n   [YouTube] ✅ 投稿完了: {url}")
            return video_id

        except Exception as e:
            print(f"   [YouTube] アップロードエラー: {e}")
            return None

    # ─────────────────────────────────────────────────────
    # メタデータ構築
    # ─────────────────────────────────────────────────────

    def _build_title(self, script: dict) -> str:
        title = script.get("title", "Global Nexus Analysis")
        # YouTube タイトル上限100文字
        title = title[:90]
        # Shorts として認識させる
        return f"{title} {SHORTS_TAG}"

    def _build_description(self, script: dict) -> str:
        caption   = script.get("caption", "")
        hook      = script.get("hook", "")
        hashtags  = " ".join(script.get("hashtags", []))
        site_line = "🔗 Full analysis: https://global-nexus-blog.pages.dev"

        return f"""{caption}

{hook}

{site_line}

{hashtags} {SHORTS_TAG}

---
Independent analysis. No sponsored content. No ads.
"""

    def _build_tags(self, script: dict) -> list:
        raw = script.get("hashtags", [])
        # "#tag" → "tag"
        tags = [t.lstrip("#") for t in raw]
        # 共通タグを追加
        tags += ["Shorts", "GlobalNexus", "TechAnalysis", "SaaS"]
        return tags[:15]  # YouTube上限15タグ

    # ─────────────────────────────────────────────────────
    # OAuth 認証
    # ─────────────────────────────────────────────────────

    def _get_service(self):
        if self._service:
            return self._service

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            print("   [YouTube] ❌ Google APIライブラリ未インストール")
            print("   pip install google-api-python-client google-auth-oauthlib")
            return None

        creds = None

        # 保存済みトークンを読み込む
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, "rb") as f:
                creds = pickle.load(f)

        # トークンが期限切れなら更新
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            if not os.path.exists(CLIENT_SECRETS):
                print(f"   [YouTube] ❌ client_secrets.json が見つかりません")
                print(f"   配置場所: {CLIENT_SECRETS}")
                print("   取得方法: https://console.cloud.google.com → YouTube Data API v3 → OAuth 2.0")
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS, SCOPES
            )
            # ブラウザで認証（初回のみ）
            creds = flow.run_local_server(port=0)

        # トークンを保存
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    # ─────────────────────────────────────────────────────
    # セットアップ確認コマンド
    # ─────────────────────────────────────────────────────

    def check_setup(self) -> bool:
        """
        セットアップが完了しているかチェックして結果を表示する。
        python -m ai_core.youtube_publisher --check で実行可能。
        """
        print("\n=== YouTube Publisher セットアップ確認 ===")

        # ライブラリチェック
        try:
            import googleapiclient
            import google_auth_oauthlib
            print("✅ Google APIライブラリ: インストール済み")
        except ImportError:
            print("❌ Google APIライブラリ: 未インストール")
            print("   → pip install google-api-python-client google-auth-oauthlib")
            return False

        # client_secrets.json チェック
        if os.path.exists(CLIENT_SECRETS):
            print(f"✅ client_secrets.json: 存在 ({CLIENT_SECRETS})")
        else:
            print(f"❌ client_secrets.json: なし")
            print(f"   → {CLIENT_SECRETS} に配置してください")
            print("   取得: https://console.cloud.google.com → YouTube Data API v3")
            return False

        # 認証トークンチェック
        if os.path.exists(TOKEN_PATH):
            print(f"✅ 認証トークン: 存在")
        else:
            print(f"⚠️  認証トークン: 未認証（初回のみブラウザ認証が必要）")

        service = self._get_service()
        if service:
            print("✅ YouTube API: 接続成功")
            return True
        else:
            print("❌ YouTube API: 接続失敗")
            return False


if __name__ == "__main__":
    pub = YouTubePublisher()
    if "--check" in sys.argv:
        pub.check_setup()