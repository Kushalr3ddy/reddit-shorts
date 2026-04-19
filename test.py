import asyncio
import os
import logging
from dotenv import load_dotenv

# Import your modularized functions
from reddit_shorts import video_processor as processor
from reddit_shorts import cloud_storage  # Assuming you moved R2 logic here
# from reddit_bot import get_and_claim_reddit_post 

# Logging configuration for the terminal
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_full_pipeline():
    load_dotenv()
    
    # 1. Mock Reddit Data (Replace this with your scraper call later)
    # post = get_and_claim_reddit_post()
    post = {
        "id": "dev_test_001",
        "title": "Why Python is great for Data Engineering",
        "content": "Python's ecosystem, from libraries like MoviePy to PRAW, makes building automated ETL pipelines incredibly efficient for solo developers."
    }
    
    post_id = post['id']
    logger.info(f"--- Starting Sync Test for Post: {post_id} ---")

    # Step 1: Generate Audio and Get the "Master Duration"
    # ---------------------------------------------------
    try:
        audio_path, duration = await processor.generate_audio(post['content'], post_id)
        if not audio_path:
            raise Exception("Audio generation failed.")
    except Exception as e:
        logger.error(f"Stop: {e}")
        return

    # Step 2: Get Video Slice synced to Audio Duration
    # -----------------------------------------------
    try:
        yt_url = processor.get_random_video_url()
        # We pass the 'duration' we got from the audio step here
        bg_video = processor.download_video_slice(yt_url, post_id, duration)
        if not bg_video:
            raise Exception("Video slicing failed.")
    except Exception as e:
        logger.error(f"Stop: {e}")
        return

    # Step 3: Final Assembly
    # ----------------------
    try:
        # The assembler will now use the exact audio length for the final render
        final_video = processor.assemble_video(bg_video, audio_path, post['title'], post_id)
        if not final_video:
            raise Exception("Assembly failed.")
    except Exception as e:
        logger.error(f"Stop: {e}")
        return

    # Step 4: Archive to Cloudflare R2
    # -------------------------------
    try:
        archive_status = processor.archive_to_r2(final_video, post_id)
        if archive_status:
            logger.info("✅ Archive Complete.")
    except Exception as e:
        logger.warning(f"R2 Archive Step failed: {e}")

    # Step 5: Clean Up
    # ---------------
    # We keep the final_video so you can check it, but delete the parts
    processor.cleanup([audio_path, bg_video])
    logger.info(f"--- Pipeline Finished. Check: {final_video} ---")

if __name__ == "__main__":
    if not os.path.exists("game_play_source.json"):
        logger.error("Missing game_play_source.json! Please create it before running.")
    else:
        asyncio.run(test_full_pipeline())