# ai_core/config.py
import os
from typing import List

# Ollama設定（ローカルホスト）
OLLAMA_HOST = "http://localhost:11434"

# 使用するモデル名（※あなたがOllamaでpull済みのモデル名を入れる）
# 推奨: 多言語・論理推論に強い "llama3.1", "qwen2.5", "gemma2" 等
OLLAMA_MODEL = "llama3.1" 

# 生成設定
TARGET_LANGUAGES: List[str] = ["ja", "en", "es"]
MAX_RETRY_COUNT = 100  

# ディレクトリ設定
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "src", "content", "blog")