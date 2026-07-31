import praw
import logging
import os
from dotenv import load_dotenv
from supabase import create_client

# Load variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

# Initializing Reddit using the exact keys from your .env
reddit = praw.Reddit(
    client_id=os.getenv("client_id"),
    client_secret=os.getenv("secret"),
    user_agent=os.getenv("app_name", "yt-shorts-bot")
)

# Initializing Supabase
# Your .env uses supabase_project_id and supabase_anon_key
SUPABASE_URL = f"https://{os.getenv('supabase_project_id')}.supabase.co"
SUPABASE_KEY = os.getenv("supabase_anon_key")
SUPABASE = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_processed_ids(reddit_ids):
    """batch-checks Supabase for which of the given ids have already been handled.

    Returns a set of reddit_ids that already exist in the pipeline table, so the
    caller can filter locally instead of querying once per submission.
    """
    if not reddit_ids:
        return set()
    try:
        res = (
            SUPABASE.table("reddit_shorts_pipeline")
            .select("reddit_id")
            .in_("reddit_id", list(reddit_ids))
            .execute()
        )
        return {row["reddit_id"] for row in res.data}
    except Exception as e:
        logger.error(f"Supabase batch check failed: {e}")
        return set()

def claim_post(post_data):
    """Inserts the post into Supabase to 'claim' it."""
    try:
        SUPABASE.table("reddit_shorts_pipeline").insert({
            "reddit_id": post_data['id'],
            "title": post_data['title'],
            "status": "PROCESSING",
            "subreddit": post_data['subreddit']
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to claim post {post_data['id']}: {e}")
        return False

def get_top_posts_from_subreddits():
    """Scans subreddits for valid 200-900 character stories."""
    subreddits = ["AmItheAsshole", "TwoSentenceHorror", "tifu", "AskReddit"]
    candidates = []

    # First pass: gather all valid submissions from Reddit (no DB calls in the loop).
    for sub_name in subreddits:
        logger.info(f"Scanning r/{sub_name}...")
        try:
            sub = reddit.subreddit(sub_name)
            for submission in sub.hot(limit=15):
                # Skip pinned posts
                if submission.stickied:
                    continue

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

    # Second pass: one batched Supabase query to drop already-processed posts.
    processed = get_processed_ids([c['id'] for c in candidates])
    if processed:
        candidates = [c for c in candidates if c['id'] not in processed]

    return candidates