import asyncio
import logging
import os
from dotenv import load_dotenv
from config import TEMP_DIR


# import modules
from modules.reddit_ingest import get_top_posts_from_subreddits, claim_post
from modules.audio_generator import generate_audio
from modules.video_processor import process_video_ffmpeg
from modules.youtube_upload import start_upload
from modules.cloud_storage import archive_video

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

#load .env stuff
load_dotenv()
logger.info("Environment variables loaded.")


def sanitize_yt_title(title):
    """Clean and truncate title for YouTube API (Max 100 chars)."""
    clean = title.replace('"', '').replace("'", "").strip()
    return f"{clean[:75]} #shorts #reddit"

def cleanup(post_id):
    """Save disk space and RAM"""
    if not post_id: return
    logger.info(f"Cleaning temp assets for {post_id}")
    for filename in os.listdir(TEMP_DIR):
        if filename.startswith(post_id):
            try:
                os.remove(os.path.join(TEMP_DIR, filename))
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

async def run_pipeline():
    logger.info("Starting Batch-Scan Pipeline...")

    # 1. SCAN FOR STORIES
    candidates = get_top_posts_from_subreddits()
    if not candidates:
        logger.info("No suitable stories found. Adding more subs might help.")
        return

    # Sort to get the longest stories (within limits) first
    candidates.sort(key=lambda x: len(x['content']), reverse=True)
    
    # 2. CLAIM THE BEST ONE
    post = None
    for c in candidates:
        if claim_post(c):
            post = c
            break
            
    if not post:
        logger.error(" Could not claim any candidate in Supabase.")
        return

    post_id = post['id']
    logger.info(f"Claimed: {post_id} (r/{post['subreddit']})")

    try:
        # 3. VOICE GENERATION
        full_text = f"{post['title']}. {post['content']}"
        audio_path, duration = await generate_audio(full_text, post_id)

        if not audio_path or duration <= 0:
            raise Exception("Audio generation failed.")

        # 4. VIDEO RENDERING
        # Ensure we stay under the 60s Shorts limit
        render_duration = min(duration, 59.5)
        
        final_video = process_video_ffmpeg(
            audio_path=audio_path,
            title=post['title'],
            post_id=post_id,
            audio_duration=render_duration
        )

        if not final_video:
            raise Exception("FFmpeg render failed.")

        # 5. STORAGE & UPLOAD
        archive_video(final_video, post_id, post['subreddit'])

        yt_title = sanitize_yt_title(post['title'])
        yt_desc = f"Story from r/{post['subreddit']}\n\n{post['content'][:400]}"
        
        youtube_id = start_upload(final_video, yt_title, yt_desc)

        if youtube_id:
            logger.info(f"SUCCESS! Watch here: https://youtu.be/{youtube_id}")
        else:
            logger.error("YouTube upload failed.")

    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")
    
    finally:
        cleanup(post_id)

if __name__ == "__main__":
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
    asyncio.run(run_pipeline())