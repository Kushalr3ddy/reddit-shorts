import praw
import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Constants from .env
SUBREDDITS = ["AskReddit", "TwoSentenceHorror", "AmItheAsshole", "Showerthoughts", "TodayILearned", "UnpopularOpinion"]
REDDIT_CLIENT_ID = os.getenv("client_id")
REDDIT_CLIENT_SECRET = os.getenv("secret")
SUPABASE_URL = f"https://{os.getenv('supabase_project_id')}.supabase.co"
SUPABASE_KEY = os.getenv("supabase_anon_key")

def get_and_claim_reddit_post():
    # Initialize Clients
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=f"script:{os.getenv('app_name')}:v1.0",
        )
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        return None

    for sub_reddit in SUBREDDITS:
        logger.info(f"Searching r/{sub_reddit}")
        try:
            cur_sub = reddit.subreddit(sub_reddit)
            # Use 'week' to give more options for deduplication
            for submission in cur_sub.top(time_filter="week", limit=15):
                if not submission.is_self or len(submission.selftext) < 300:
                    continue 

                # Database Deduplication Check
                res = supabase.table("reddit_shorts_pipeline").select("reddit_id").eq("reddit_id", submission.id).execute()
                
                if not res.data:
                    # Claim the post
                    supabase.table("reddit_shorts_pipeline").insert({
                        "reddit_id": submission.id,
                        "title": submission.title,
                        "status": "PROCESSING"
                    }).execute()
                    
                    logger.info(f"Claimed new post: {submission.id} from r/{sub_reddit}")
                    return {
                        "id": submission.id,
                        "title": submission.title,
                        "content": submission.selftext,
                        "subreddit": sub_reddit
                    }
                else:
                    logger.debug(f"Post {submission.id} already exists in database. Skipping.")

        except Exception as e:
            logger.error(f"Error processing r/{sub_reddit}: {e}")
            continue

    logger.warning("No new unique posts found in the specified subreddits.")
    return None

if __name__ == "__main__":
    target_post = get_and_claim_reddit_post()
    if target_post:
        logger.info(f"Target identified: {target_post['title'][:50]}...")