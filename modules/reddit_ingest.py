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

def is_already_processed(reddit_id):
    """Checks Supabase to see if this post has been handled."""
    try:
        res = SUPABASE.table("reddit_shorts_pipeline").select("reddit_id").eq("reddit_id", reddit_id).execute()
        return len(res.data) > 0
    except Exception as e:
        logger.error(f"Supabase check failed: {e}")
        return False

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
    
    for sub_name in subreddits:
        logger.info(f"Scanning r/{sub_name}...")
        try:
            sub = reddit.subreddit(sub_name)
            for submission in sub.hot(limit=15):
                # Skip if it's a pinned post or already processed
                if submission.stickied or is_already_processed(submission.id):
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
            
    return candidates