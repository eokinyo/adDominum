# publishing/poster.py
"""
Poster — publishes posts to X (Twitter).

Retry logic on connection failures:
  Attempt 1 — immediately
  Attempt 2 — 30 seconds later
  Attempt 3 — 90 seconds later
  Attempt 4 — 3 minutes later
  Attempt 5 — 5 minutes later
  After 5 failures — give up and log error
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from utils.logger import setup_logging
from utils.config import config

logger = setup_logging("poster")

# Retry delays in seconds: 0, 30, 90, 180, 300
RETRY_DELAYS = [0, 30, 90, 180, 300]


class Poster:
    def __init__(self):
        self.dry_run = config.dry_run
        self._client = None
        self._api_v1 = None

        if not self.dry_run:
            self._init_client()

    def _init_client(self):
        if not config.has_credentials:
            logger.error("X API credentials missing — check config/api_keys.env")
            return
        try:
            import tweepy

            auth = tweepy.OAuth1UserHandler(
                config.x_api_key, config.x_api_secret,
                config.x_access_token, config.x_access_secret,
            )
            self._api_v1 = tweepy.API(auth)

            self._client = tweepy.Client(
                consumer_key=config.x_api_key,
                consumer_secret=config.x_api_secret,
                access_token=config.x_access_token,
                access_token_secret=config.x_access_secret,
            )
            logger.info("X API clients initialised")

        except ImportError:
            logger.error("tweepy not installed — run: pip install tweepy")
        except Exception as e:
            logger.error(f"X API init failed: {e}")

    def post(self, text: str, card_path: Optional[Path] = None) -> bool:
        if not text:
            logger.warning("post() called with empty text")
            return False

        if self.dry_run:
            logger.info("=== DRY RUN — would post: ===")
            logger.info(f"  Text ({len(text)} chars):")
            for line in text.splitlines():
                logger.info(f"    {line}")
            if card_path and card_path.exists():
                logger.info(f"  Card: {card_path.name}")
            logger.info("=" * 40)
            return True

        if not self._client:
            logger.error("X client not initialised — cannot post")
            return False

        # Upload media once (before retry loop)
        media_id = None
        if card_path and card_path.exists():
            try:
                media = self._api_v1.media_upload(filename=str(card_path))
                media_id = media.media_id
                logger.info(f"Media uploaded: {media_id}")
            except Exception as e:
                logger.error(f"Media upload failed: {e} — posting text only")

        # Tweet with retry
        kwargs = {"text": text}
        if media_id:
            kwargs["media_ids"] = [media_id]

        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            if delay > 0:
                logger.warning(
                    f"Retrying in {delay} seconds... "
                    f"(attempt {attempt} of {len(RETRY_DELAYS)})"
                )
                time.sleep(delay)

            try:
                response = self._client.create_tweet(**kwargs)
                tweet_id = response.data["id"]
                logger.info(f"Posted: https://x.com/i/status/{tweet_id}")
                return True

            except Exception as e:
                err = str(e)
                is_connection_err = any(w in err for w in [
                    "ConnectionReset", "ConnectionAborted",
                    "RemoteDisconnected", "BrokenPipe", "timeout"
                ])

                if attempt < len(RETRY_DELAYS) and is_connection_err:
                    logger.warning(f"Attempt {attempt} failed: {err}")
                    continue
                else:
                    logger.error(f"Post failed after {attempt} attempt(s): {e}")
                    return False

        logger.error("All retry attempts exhausted — post failed")
        return False
