"""Step 1 of the pipeline: find candidate stories on Reddit.

Uses PRAW (read-only, app credentials from .env: client_id, secret, app_name). Which posts have
already been used is tracked in modules/state_db.py (SQLite synced with R2); claim_post is
re-exported from there so main.py's import stays the same.
"""
import praw
import logging
import os
from dotenv import load_dotenv

from modules.state_db import get_processed_ids, claim_post  # noqa: F401  (claim_post used by main.py)

# Load variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

# Initializing Reddit using the exact keys from your .env
reddit = praw.Reddit(
    client_id=os.getenv("client_id"),
    client_secret=os.getenv("secret"),
    user_agent=os.getenv("app_name", "yt-shorts-bot")
)

def get_top_posts_from_subreddits():
    """Scans subreddits for valid 200-900 character stories.

    Returns a list of dicts {id, title, content, subreddit} that are NOT already in the state db.
    """
    subreddits = ["AmItheAsshole", "TwoSentenceHorror", "tifu", "AskReddit"]
    candidates = []

    # pass 1: grab all the decent submissions off reddit first. NO db calls in here, thats the point
    for sub_name in subreddits:
        logger.info(f"Scanning r/{sub_name}...")
        try:
            sub = reddit.subreddit(sub_name)
            for submission in sub.hot(limit=15):
                # skip the pinned mod posts, theyre never actual stories
                if submission.stickied:
                    continue

                # length window: long enough to fill a Short, short enough to read in < 60s
                content = submission.selftext
                if 200 <= len(content) <= 900:
                    candidates.append({
                        'id': submission.id,
                        'title': submission.title,
                        'content': content,
                        'subreddit': sub_name
                    })
        except Exception as e:
            logger.error(f"Reddit error on r/{sub_name}: {e}")

    # pass 2: one single db hit to throw out the ones we already did
    processed = get_processed_ids([c['id'] for c in candidates])
    if processed:
        candidates = [c for c in candidates if c['id'] not in processed]

    return candidates
