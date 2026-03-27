"""AI content generation with persona-specific prompts."""

import logging
from typing import Any

logger = logging.getLogger("bsq.content")


class ContentGenerator:
    """Generate post text using Claude or OpenAI API."""

    def __init__(self, provider: str, model: str, api_key: str):
        self._provider = provider
        self._model = model
        self._api_key = api_key

    async def generate(
        self,
        persona_style: str,
        persona_topics: list[str],
        topic: dict[str, Any],
        market_data: dict[str, Any],
    ) -> str:
        """Generate post text using AI with persona-specific prompt.

        Args:
            persona_style: Writing style description (e.g., "analytical, data-heavy")
            persona_topics: Topic areas the persona covers
            topic: Trending topic dict with name, hashtags, coins
            market_data: Current prices/changes for relevant coins

        Returns:
            Generated post text ready for publishing.
        """
        system_prompt = self._build_system_prompt(persona_style, persona_topics)
        user_prompt = self._build_user_prompt(topic, market_data)

        if self._provider == "anthropic":
            return await self._generate_anthropic(system_prompt, user_prompt)
        else:
            return await self._generate_openai(system_prompt, user_prompt)

    def _build_system_prompt(self, style: str, topics: list[str]) -> str:
        return (
            f"You are a regular person who posts about crypto on Binance Square. "
            f"Your vibe: {style}. "
            f"You usually talk about: {', '.join(topics)}.\n\n"
            f"You're just a normal person texting or posting online. "
            f"Never use typical AI writing style. Never.\n\n"
            f"STRICT RULES (follow every single one):\n"
            f"- Use very simple words and short sentences.\n"
            f"- Sound like a real conversation — the way people actually talk in real life.\n"
            f"- You can start sentences with 'and', 'but', 'so', 'yeah', 'nah', 'honestly' etc.\n"
            f"- Casual grammar is fine — lowercase starts, skipping punctuation, contractions.\n"
            f"- Be direct. Cut every unnecessary word.\n"
            f"- No marketing fluff, no hype, no inspirational speeches.\n"
            f"- No clichés like: 'let's dive into', 'unlock your potential', 'embark on a journey', "
            f"'unique landscape', 'take it to the next level', 'revolutionary approach', "
            f"'paradigm shift', 'cutting-edge solutions', 'transformational', 'unprecedented', "
            f"'game-changer', 'it's worth noting', 'in conclusion', 'comprehensive guide'.\n"
            f"- Explain complex stuff simply, like you're telling a friend over coffee — "
            f"no fancy jargon unless needed (and if you use a term, explain it quick).\n"
            f"- Use emojis or slang only if it looks natural. don't force them.\n"
            f"- Include relevant $CASHTAGS and #hashtags naturally in your post.\n"
            f"- Use concrete numbers, percentages, price levels when you have them.\n"
            f"- Write in English only.\n"
            f"- Post length: 100-280 chars for quick takes, up to 1000 for deeper analysis.\n\n"
            f"VERY BAD (never write like this):\n"
            f"'Let's dive into this exciting topic and unlock the full potential of DeFi!'\n"
            f"'This comprehensive guide will revolutionize your approach to trading.'\n"
            f"'Arm yourself with these transformational insights to skyrocket your portfolio.'\n\n"
            f"GOOD examples of how you should sound:\n"
            f"'$BTC just broke 67k. honestly didn't expect it this fast'\n"
            f"'so eth is pumping again but volume looks kinda weak ngl'\n"
            f"'nah skip that token, tokenomics are trash'\n"
            f"'looks like whales are loading up on $SOL. interesting'\n"
            f"'this dip is probably nothing but i'm setting a limit order just in case'\n\n"
            f"Stay in character. No apologies for your style. No meta-commentary about how you write."
        )

    def _build_user_prompt(self, topic: dict, market_data: dict) -> str:
        parts = [f"Write a post about: {topic.get('name', 'crypto')}"]

        if topic.get("hashtags"):
            parts.append(f"Trending hashtags: {', '.join('#' + h for h in topic['hashtags'][:5])}")

        if topic.get("coins"):
            parts.append(f"Related coins: {', '.join('$' + c for c in topic['coins'][:5])}")

        if market_data:
            market_lines = []
            for coin, data in market_data.items():
                if isinstance(data, dict):
                    price = data.get("price", 0)
                    change = data.get("change_24h", 0)
                    market_lines.append(f"${coin}: ${price:,.2f} ({change:+.1f}% 24h)")
            if market_lines:
                parts.append("Current market data:\n" + "\n".join(market_lines))

        return "\n\n".join(parts)

    async def _generate_anthropic(self, system: str, user: str) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        message = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text

    async def _generate_openai(self, system: str, user: str) -> str:
        import openai
        client = openai.AsyncOpenAI(api_key=self._api_key)
        response = await client.chat.completions.create(
            model=self._model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
