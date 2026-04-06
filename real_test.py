import asyncio
import os
import logging
import processor  # Assuming your processing functions are in processor.py
import cloud_storage
from reddit_ingest import get_and_claim_reddit_post # Your existing scraper

# Configure logging for your Ubuntu terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_real_test():
    logger.info("Step 1: Fetching a real post from Reddit...")
    post = get_and_claim_reddit_post()
    
    if not post:
        logger.warning("No new posts found to process. Check your subreddits/filters.")
        return

    post_id = post['id']
    logger.info(f"Processing Post: {post['title']}")

    try:
        # Step 2: Audio
        logger.info("Step 2: Generating AI Voiceover...")
        audio_path = await processor.generate_audio(post['content'], post_id)
        
        # Step 3: Video Slice
        logger.info("Step 3: Slicing gameplay from YouTube...")
        source_url = processor.get_random_video_url()
        bg_video = processor.download_video_slice(source_url, post_id)
        
        # Step 4: Assemble (MoviePy)
        logger.info("Step 4: Rendering final video (this uses your CPU)...")
        final_video = processor.assemble_video(bg_video, audio_path, post['title'], post_id)
        
        if final_video:
            # Step 5: Archive
            logger.info("Step 5: Sending to Cloud Storage...")
            cloud_storage.archive_video(final_video, post_id)
            
            logger.info(f"🏁 DONE! Final video is at: {final_video}")
            
            # Optional: processor.cleanup([audio_path, bg_video])
            
    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")

if __name__ == "__main__":
    asyncio.run(run_real_test())