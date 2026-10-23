"""Entry point: runs ONE full pipeline pass (reddit story -> voiceover -> video -> R2 + YouTube).

Flow of run_pipeline():
  1. scan subreddits for stories not seen before   (modules/reddit_ingest.py + state_db.py)
  2. claim the longest one in the SQLite state db  (state db is synced with R2)
  3. text-to-speech                                (modules/audio_generator.py)
  4. render vertical video with ffmpeg             (modules/video_processor.py)
  5. archive to R2, upload to YouTube              (cloud_storage.py, youtube_upload.py)
  6. mark the post DONE/FAILED and clean temp files
Scheduled by .github/workflows/pipeline.yml (twice a day) or run via docker compose.
"""
import asyncio
import logging
import os
from dotenv import load_dotenv
from config import TEMP_DIR


# import modules
from modules.reddit_ingest import get_top_posts_from_subreddits, claim_post
from modules.state_db import mark_status
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


# NOTE: a FAILED post is never retried - it stays in the state db, so the dedupe skips it
# next time. Delete its row from the db if you want it picked up again.

def sanitize_yt_title(title):
    """Clean and truncate title for YouTube API (Max 100 chars): 75 chars + hashtag suffix."""
    clean = title.replace('"', '').replace("'", "").strip()
    return f"{clean[:75]} #shorts #reddit"

def cleanup(post_id):
    """Delete this post's temp files (<post_id>.mp3, <post_id>_final.mp4) from TEMP_DIR."""
    if not post_id: return
    logger.info(f"Cleaning temp assets for {post_id}")
    for filename in os.listdir(TEMP_DIR):
        if filename.startswith(post_id):
            try:
                os.remove(os.path.join(TEMP_DIR, filename))
            except Exception as e:
                logger.warning(f"Cleanup error: {e}")

async def run_pipeline():
    """One end-to-end pass. Exactly one story is produced per call."""
    logger.info("Starting Batch-Scan Pipeline...")

    # 1. SCAN FOR STORIES
    candidates = get_top_posts_from_subreddits()
    if not candidates:
        logger.info("No suitable stories found. Adding more subs might help.")
        return

    # (The 200-900 char window is enforced in reddit_ingest.)
    # Sort to get the longest stories (within limits) first
    candidates.sort(key=lambda x: len(x['content']), reverse=True)
    
    # 2. CLAIM THE BEST ONE
    post = None
    for c in candidates:
        if claim_post(c):
            post = c
            break
            
    if not post:
        logger.error(" Could not claim any candidate in the state db.")
        return

    post_id = post['id']
    status = "FAILED"      # flipped to DONE only if the upload returns a video id
    youtube_id = None
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
        archive_video(final_video, post_id, post['subreddit'])  # best-effort: failure is only logged

        yt_title = sanitize_yt_title(post['title'])
        yt_desc = f"Story from r/{post['subreddit']}\n\n{post['content'][:400]}"
        
        youtube_id = start_upload(final_video, yt_title, yt_desc)

        if youtube_id:
            status = "DONE"
            logger.info(f"SUCCESS! Watch here: https://youtu.be/{youtube_id}")
        else:
            logger.error("YouTube upload failed.")

    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")
    
    finally:
        # record the outcome in the state db (and push it to R2), then delete temp files
        mark_status(post_id, status, youtube_id)
        cleanup(post_id)

if __name__ == "__main__":
    # config.py already creates TEMP_DIR on import; this is just a safety net
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)
    asyncio.run(run_pipeline())