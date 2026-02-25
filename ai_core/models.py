# ai_core/models.py
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ArticleState:
    """
    エージェント間で共有される記事の現在の状態（ステータス）を保持するクラス。
    これがWriterからCriticへ、そしてまたWriterへと渡される。
    """
    topic: str
    language: str
    
    # Writer Agentが生成するデータ
    title: str = ""
    description: str = ""
    content_markdown: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Critic Agentが評価するデータ
    is_approved: bool = False
    critic_feedback: str = ""
    retry_count: int = 0
    
    # 最終的な出力用データ
    slug: str = ""
    
    def to_frontmatter(self) -> str:
        """Astro用のフロントマター（ヘッダー情報）を生成する"""
        tags_str = "\n".join([f"  - {tag}" for tag in self.tags])
        return f"""---
title: "{self.title}"
description: "{self.description}"
date: CURRENT_DATETIME
tags:
{tags_str}
---
"""