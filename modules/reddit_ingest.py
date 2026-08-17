import praw
import logging
import os
from dotenv import load_dotenv
import psycopg2

# Load variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

# Initializing Reddit using the exact keys from your .env
reddit = praw.Reddit(
    client_id=os.getenv("client_id"),
    client_secret=os.getenv("secret"),
    user_agent=os.getenv("app_name", "yt-shorts-bot")
)

# plain postgres now, ditched the supabase client cause it was just a wrapper around this anyway
# .env has the direct connect bits: db_url (host), db_port, postgres_user, postgres_password
# autocommit ON on purpose: each query is its own lil transaction, so a failed insert
# (like a dupe claim) doesnt poison the connection and make every query after it shit itself
CONN = psycopg2.connect(
    host=os.getenv("db_url"),
    port=os.getenv("db_port"),
    user=os.getenv("postgres_user"),
    password=os.getenv("postgres_password"),
    dbname="postgres"
)
CONN.autocommit = True

def get_processed_ids(reddit_ids):
    """asks postgres ONCE which of these ids we already did, instead of hammering it per post.

    hands back a set of the reddit_ids that are already in the table, so the caller can
    just filter locally. this is the whole optimisation, no more querying inside the loop
    """
    if not reddit_ids:
        return set()
    try:
        # ANY(%s) = dump the whole id list in as one postgres array, so its 1 query not 60
        with CONN.cursor() as cur:
            cur.execute(
                "SELECT reddit_id FROM reddit_shorts_pipeline WHERE reddit_id = ANY(%s)",
                (list(reddit_ids),)
            )
            return {row[0] for row in cur.fetchall()}
    except Exception as e:
        logger.error(f"postgres batch check shat itself: {e}")
        return set()

def claim_post(post_data):
    """shoves the post into postgres to 'claim' it so no other run steals the same one."""
    try:
        # if the reddit_id already exists this INSERT blows up (unique constraint) and we
        # return False. thats not a bug, thats literally how the claiming works
        with CONN.cursor() as cur:
            cur.execute(
                """
                INSERT INTO reddit_shorts_pipeline (reddit_id, title, status, subreddit)
                VALUES (%s, %s, %s, %s)
                """,
                (post_data['id'], post_data['title'], "PROCESSING", post_data['subreddit'])
            )
        return True
    except Exception as e:
        logger.error(f"couldnt claim post {post_data['id']}: {e}")
        return False

def get_top_posts_from_subreddits():
    """Scans subreddits for valid 200-900 character stories."""
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