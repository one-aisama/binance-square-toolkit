"""Pydantic models for bapi responses."""

from pydantic import BaseModel
from typing import Any


class BapiResponse(BaseModel):
    """Standard bapi response wrapper."""
    code: str = ""
    message: str | None = None
    data: Any = None
    success: bool = False

    @property
    def is_ok(self) -> bool:
        return self.code == "000000" or self.success


class FeedPost(BaseModel):
    """A post from the feed/article endpoints."""
    post_id: str = ""
    author_name: str = ""
    author_role: str = ""
    card_type: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    hashtags: list[str] = []
    trading_pairs: list[str] = []
    is_ai_created: bool = False
    created_at: int = 0  # timestamp ms
    text_preview: str = ""
