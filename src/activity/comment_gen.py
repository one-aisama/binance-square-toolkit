"""AI-powered comment generation for Binance Square.

Generates short, relevant comments that sound like a real person
talking to the post author. Uses DeepSeek API (OpenAI-compatible).
"""

import os
import logging
import yaml
from typing import Any
from openai import AsyncOpenAI

logger = logging.getLogger("bsq.activity")

# Load comment rules from config
_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "content_rules.yaml")


def _load_comment_rules() -> dict:
    try:
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules.get("comments", {})
    except Exception:
        return {}


COMMENT_SYSTEM_PROMPT = """You are a regular person commenting on a crypto post on Binance Square.
You're talking directly to the author — like a conversation, not a separate post.

STRICT RULES:
- Write 1-2 sentences MAX. Keep it very short.
- Be relevant to EXACTLY what the author wrote. Reference specific details from their post.
- Sound like a real person in a chat — casual, direct, no fluff.
- Use simple words. Lowercase is fine. Skip punctuation if it feels natural.
- Types of comments: agree with a specific point, ask a follow-up question, add a related observation, or mildly disagree with reasoning.
- Talk TO the author, not about the post.

NEVER write:
- "Great post!" or "Thanks for sharing!" or "Very informative!"
- "I agree with everything you said"
- "Nice analysis, keep it up!"
- Generic motivational stuff
- Anything longer than 2 sentences

GOOD examples:
- "the part about eth gas fees is spot on but L2 adoption is fixing that faster than most people think"
- "wait you think 65k is support? that level got tested 3 times already and barely held"
- "interesting take but isnt the fed more likely to hold rates given last weeks jobs data"
- "yeah $SOL fees are crazy low but the network went down twice this month so theres that"
- "those short entries look solid. whats your stop loss on the $RIVER position"
- "damn 2000% on that river short. how long did you hold that"

Write ONLY the comment text, nothing else. No quotes. No "Comment:" prefix."""


class CommentGenerator:
    """Generate relevant comments using AI (DeepSeek/OpenAI compatible API)."""

    def __init__(self, provider: str = "deepseek", model: str = "deepseek-chat", api_key: str = ""):
        self._provider = provider
        self._model = model

        if provider == "deepseek":
            self._client = AsyncOpenAI(
                api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
                base_url="https://api.deepseek.com",
            )
        elif provider == "openai":
            self._client = AsyncOpenAI(
                api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            )
        elif provider == "anthropic":
            # For anthropic, we'll use the anthropic SDK directly
            self._client = None
            self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def generate(self, post_text: str, author_name: str = "") -> str:
        """Generate a relevant comment for the given post.

        Args:
            post_text: Full text of the post to comment on
            author_name: Name of the post author (for context)

        Returns:
            Comment text (1-2 sentences, relevant to post content)
        """
        user_prompt = f"Post by {author_name}:\n\n{post_text[:500]}\n\nWrite your comment:"

        if self._provider == "anthropic":
            return await self._generate_anthropic(user_prompt)

        # DeepSeek and OpenAI use the same API
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_tokens=100,
                temperature=0.8,
                messages=[
                    {"role": "system", "content": COMMENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            comment = response.choices[0].message.content.strip()
            # Remove quotes if AI wrapped it
            comment = comment.strip('"').strip("'")
            logger.info(f"Generated comment: {comment[:80]}...")
            return comment
        except Exception as e:
            logger.error(f"Comment generation failed: {e}")
            return ""

    async def _generate_anthropic(self, user_prompt: str) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        msg = await client.messages.create(
            model=self._model,
            max_tokens=100,
            system=COMMENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        comment = msg.content[0].text.strip().strip('"').strip("'")
        logger.info(f"Generated comment: {comment[:80]}...")
        return comment

    # Backward-compatible alias used by ActivityExecutor
    async def generate_comment(self, post_text: str, persona_style: str = "", comment_type: str | None = None) -> str:
        """Alias for generate() — keeps ActivityExecutor working without changes."""
        return await self.generate(post_text)
