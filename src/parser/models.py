"""Parser data models."""

from dataclasses import dataclass, field


@dataclass
class ParsedPost:
    """A parsed post from bapi feed/article endpoints."""
    post_id: str
    author_name: str = ""
    author_id: str = ""
    card_type: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hashtags: list[str] = field(default_factory=list)
    trading_pairs: list[str] = field(default_factory=list)
    is_ai_created: bool = False
    created_at: int = 0  # timestamp ms
    text_preview: str = ""


@dataclass
class Topic:
    """A ranked topic/trend extracted from parsed posts."""
    name: str
    hashtags: list[str] = field(default_factory=list)
    coins: list[str] = field(default_factory=list)
    engagement_score: float = 0.0
    post_count: int = 0
