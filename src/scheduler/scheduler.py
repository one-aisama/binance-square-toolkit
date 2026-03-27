"""Scheduler — orchestrates the main cycle."""

import os
import random
import logging
from datetime import datetime, timedelta
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from src.db.database import init_db, get_db_path
from src.session.adspower import AdsPowerClient
from src.session.harvester import harvest_credentials
from src.session.credential_store import CredentialStore
from src.session.validator import validate_credentials
from src.bapi.client import BapiClient
from src.accounts.manager import load_accounts, AccountConfig
from src.accounts.limiter import ActionLimiter
from src.parser.fetcher import TrendFetcher
from src.parser.aggregator import rank_topics
from src.content.generator import ContentGenerator
from src.content.publisher import ContentPublisher
from src.content.market_data import get_market_data
from src.activity.executor import ActivityExecutor, CommentGenerator
from src.activity.randomizer import HumanRandomizer
from src.activity.target_selector import TargetSelector

logger = logging.getLogger("bsq.scheduler")


class CycleScheduler:
    """Main cycle scheduler for Binance Square content farm."""

    def __init__(self, settings: dict[str, Any], accounts: list[AccountConfig], db_path: str):
        self._settings = settings
        self._accounts = accounts
        self._db_path = db_path
        self._scheduler = AsyncIOScheduler()
        self._credential_store = CredentialStore(db_path)
        self._limiter = ActionLimiter(db_path)
        self._adspower = AdsPowerClient(
            base_url=settings.get("adspower_base_url", "http://local.adspower.net:50325"),
            timeout_start=settings.get("adspower_start_timeout_sec", 60),
            timeout_stop=settings.get("adspower_stop_timeout_sec", 30),
        )

    def start(self):
        """Start the scheduler."""
        self._scheduler.start()
        if self._settings.get("first_run_immediate", True):
            self._schedule_next(delay_seconds=5)
        else:
            self._schedule_next()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def _schedule_next(self, delay_seconds: float | None = None):
        """Schedule the next cycle."""
        if delay_seconds is None:
            interval = self._settings.get("cycle_interval_hours", [2, 4])
            delay_seconds = random.uniform(*interval) * 3600

        run_date = datetime.now() + timedelta(seconds=delay_seconds)
        self._scheduler.add_job(
            self._run_cycle,
            trigger=DateTrigger(run_date=run_date),
            id="main_cycle",
            replace_existing=True,
        )
        logger.info(f"Next cycle scheduled at {run_date.strftime('%H:%M:%S')} ({delay_seconds:.0f}s)")

    async def _run_cycle(self):
        """Main cycle: validate credentials → parse → generate → publish → activity."""
        logger.info("=" * 50)
        logger.info("CYCLE STARTED")
        logger.info("=" * 50)

        try:
            for account in self._accounts:
                try:
                    await self._process_account(account)
                except Exception as e:
                    logger.error(f"Error processing account {account.account_id}: {e}")

            logger.info("CYCLE COMPLETED")
        except Exception as e:
            logger.error(f"Cycle failed: {e}")
        finally:
            self._schedule_next()

    async def _process_account(self, account: AccountConfig):
        """Process one account: credentials → parse → generate → publish → activity."""
        account_id = account.account_id
        logger.info(f"--- Processing account: {account_id} ---")

        # 1. Ensure valid credentials
        cred = await self._credential_store.load(account_id)
        needs_refresh = (
            cred is None
            or not cred["valid"]
            or await self._credential_store.is_expired(account_id)
        )

        if needs_refresh:
            logger.info(f"Refreshing credentials for {account_id}...")
            await self._refresh_credentials(account)
            cred = await self._credential_store.load(account_id)
            if cred is None or not cred["valid"]:
                logger.error(f"Failed to refresh credentials for {account_id} — skipping")
                return
        else:
            # Validate existing credentials
            is_valid = await validate_credentials(cred["cookies"], cred["headers"])
            if not is_valid:
                logger.info(f"Credentials expired for {account_id}, refreshing...")
                await self._refresh_credentials(account)
                cred = await self._credential_store.load(account_id)
                if cred is None or not cred["valid"]:
                    logger.error(f"Failed to refresh credentials for {account_id} — skipping")
                    return

        # 2. Create BapiClient for this account
        bapi_client = BapiClient(
            account_id=account_id,
            credential_store=self._credential_store,
            base_url=self._settings.get("bapi_base_url", "https://www.binance.com"),
            rate_limit_rpm=self._settings.get("bapi_rate_limit_rpm", 30),
            retry_attempts=self._settings.get("bapi_retry_attempts", 3),
            retry_backoff=self._settings.get("bapi_retry_backoff_sec", 1.0),
        )

        # 3. Parse trends
        logger.info(f"Parsing trends for {account_id}...")
        fetcher = TrendFetcher(bapi_client)
        posts = await fetcher.fetch_all(article_pages=3, feed_pages=3)
        topics = rank_topics(posts, top_n=10)

        if not topics:
            logger.warning(f"No topics found for {account_id}")
        else:
            logger.info(f"Top topics: {', '.join(t.name for t in topics[:5])}")

        # 4. Generate and queue content
        if account.persona and topics:
            await self._generate_content(account, topics, bapi_client)

        # 5. Publish queued content
        publisher = ContentPublisher(bapi_client, self._db_path)
        pending = await publisher.get_pending(account_id)
        for item in pending:
            try:
                result = await publisher.publish(item["text"])
                await publisher.mark_published(item["id"], post_id=str(result.get("data", {}).get("id", "")))
                await self._limiter.record_action(account_id, "post", status="success")
                logger.info(f"Published post #{item['id']} for {account_id}")
            except NotImplementedError:
                logger.warning(f"create_post not yet implemented — content stays in queue")
                break
            except Exception as e:
                await publisher.mark_failed(item["id"], str(e))
                await self._limiter.record_action(account_id, "post", status="failed", error=str(e))
                logger.error(f"Failed to publish #{item['id']}: {e}")

        # 6. Run activity
        if posts:
            await self._run_activity(account, posts, bapi_client)

    async def _refresh_credentials(self, account: AccountConfig):
        """Start AdsPower browser, harvest credentials, save to store."""
        try:
            browser_data = await self._adspower.start_browser(account.adspower_profile_id)
            ws_endpoint = browser_data.get("ws", "")
            if not ws_endpoint:
                logger.error(f"No WS endpoint for {account.account_id}")
                return

            cred = await harvest_credentials(ws_endpoint)
            await self._credential_store.save(
                account.account_id,
                cred["cookies"],
                cred["headers"],
                max_age_hours=self._settings.get("credential_max_age_hours", 12),
            )
            logger.info(f"Credentials refreshed for {account.account_id}")
        except Exception as e:
            logger.error(f"Credential refresh failed for {account.account_id}: {e}")
        finally:
            try:
                await self._adspower.stop_browser(account.adspower_profile_id)
            except Exception:
                pass

    async def _generate_content(self, account: AccountConfig, topics: list, bapi_client: BapiClient):
        """Generate content for account based on topics and persona."""
        persona = account.persona
        if not persona:
            return

        # Check if we can post today
        if not await self._limiter.check_allowed(
            account.account_id, "post", account.limits.posts_per_day
        ):
            logger.info(f"Post limit reached for {account.account_id} today")
            return

        # Filter topics by persona interests
        relevant_topics = [
            t for t in topics
            if any(pt in t.name.lower() for pt in persona.topics) or not persona.topics
        ]
        if not relevant_topics:
            relevant_topics = topics[:3]  # Fallback to top topics

        # Get market data for coins mentioned in topics
        all_coins = set()
        for t in relevant_topics[:3]:
            all_coins.update(t.coins)
        market_data = {}
        if all_coins:
            try:
                market_data = await get_market_data(list(all_coins)[:5])
            except Exception as e:
                logger.warning(f"Market data fetch failed: {e}")

        # Generate post
        ai_provider = self._settings.get("ai_provider", "anthropic")
        ai_model = self._settings.get("ai_model", "claude-sonnet-4-6")
        api_key = os.environ.get(
            "ANTHROPIC_API_KEY" if ai_provider == "anthropic" else "OPENAI_API_KEY", ""
        )

        if not api_key:
            logger.warning(f"No API key for {ai_provider} — skipping content generation")
            return

        generator = ContentGenerator(ai_provider, ai_model, api_key)
        topic = relevant_topics[0]

        try:
            text = await generator.generate(
                persona_style=persona.style,
                persona_topics=persona.topics,
                topic={"name": topic.name, "hashtags": topic.hashtags, "coins": topic.coins},
                market_data=market_data,
            )

            publisher = ContentPublisher(bapi_client, self._db_path)
            await publisher.queue_content(
                account_id=account.account_id,
                text=text,
                hashtags=topic.hashtags,
                topic=topic.name,
                meta={"model": ai_model, "provider": ai_provider},
            )
            logger.info(f"Generated and queued post for {account.account_id}: {text[:80]}...")
        except Exception as e:
            logger.error(f"Content generation failed for {account.account_id}: {e}")

    async def _run_activity(self, account: AccountConfig, posts: list, bapi_client: BapiClient):
        """Run activity cycle for an account."""
        all_account_ids = {a.account_id for a in self._accounts}

        randomizer = HumanRandomizer(
            delay_range=tuple(self._settings.get("activity_delay_range_sec", [30, 120])),
            skip_rate=self._settings.get("activity_skip_rate", 0.35),
        )
        selector = TargetSelector(
            own_account_ids=all_account_ids,
            min_views=self._settings.get("activity_min_views_for_comment", 1000),
        )

        # Convert ParsedPost objects to dicts for target selector
        post_dicts = [
            {
                "post_id": p.post_id,
                "author_id": p.author_id,
                "view_count": p.view_count,
                "text_preview": p.text_preview,
            }
            for p in posts
        ]

        executor = ActivityExecutor(
            client=bapi_client,
            limiter=self._limiter,
            randomizer=randomizer,
            target_selector=selector,
        )

        limits = {
            "like": account.limits.likes_per_day,
            "comment": account.limits.comments_per_day,
            "repost": [0, 1],
        }

        results = await executor.run_cycle(account.account_id, post_dicts, limits)
        logger.info(f"Activity for {account.account_id}: {results}")
