import os

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "llama3.1"
TARGET_LANGUAGES = ["ja", "en", "es"]
MAX_RETRY_COUNT = 3
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "src", "content", "blog")
