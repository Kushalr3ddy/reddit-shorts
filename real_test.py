import asyncio
import os
import logging
import processor # Ensure processor.py is in the same folder
from dotenv import load_dotenv

# Setup logging to see the progress in your Ubuntu terminal
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_full_pipeline():
    load_dotenv()
    
    # 1. Mock Data
    test_id = "test_run_001"
    test_title = "The mystery of the forgotten Ubuntu terminal"
    test_content = """
    I was sitting at my desk when suddenly my laptop started fans at full speed. 
    I realized I had left a MoviePy render running in a infinite loop. 
    My CPU was at 100 percent and my coffee was staying warm just from the heat.
    """
    
    logger.info("--- STARTING PROCESSOR TEST ---")

    try:
        # Step 1: Audio Generation & Duration Check
        logger.info("TEST 1: Audio Generation...")
        audio_path, duration = await processor.generate_audio(test_content, test_id)
        if audio_path and os.path.exists(audio_path):
            logger.info(f"✅ Audio Success: {duration:.2f} seconds")
        else:
            logger.error("❌ Audio Failed")
            return

        # Step 2: YouTube Random URL Selection
        logger.info("TEST 2: Selecting random gameplay...")
        yt_url = processor.get_random_video_url()
        if yt_url:
            logger.info(f"✅ URL Success: {yt_url}")
        else:
            logger.error("❌ URL Selection Failed")
            return

        # Step 3: Video Slicing (Duration Synced)
        logger.info(f"TEST 3: Slicing {duration:.2f}s from YouTube...")
        bg_video = processor.download_video_slice(yt_url, test_id, duration)
        if bg_video and os.path.exists(bg_video):
            logger.info("✅ Slicing Success")
        else:
            logger.error("❌ Slicing Failed")
            return

        # Step 4: MoviePy Assembly (The 'Final Boss')
        logger.info("TEST 4: Final Assembly & Rendering...")
        final_video = processor.assemble_video(bg_video, audio_path, test_title, test_id)
        if final_video and os.path.exists(final_video):
            logger.info(f"✅ Assembly Success: {final_video}")
        else:
            logger.error("❌ Assembly Failed (Check ImageMagick/MoviePy attributes)")
            return

        # Step 5: R2 Archive (Optional)
        logger.info("TEST 5: R2 Archiving...")
        archive_success = processor.archive_to_r2(final_video, test_id)
        if archive_success:
            logger.info("✅ R2 Archive Success")
        else:
            logger.warning("⚠️ R2 Archive Failed (Check .env keys)")

        logger.info("--- ALL TESTS PASSED! ---")
        logger.info(f"You can find your test video at: {final_video}")

    except Exception as e:
        logger.error(f"💥 Pipeline crashed with error: {e}")
    finally:
        # We leave the 'final' video for you to watch, but clean up the parts
        logger.info("Cleaning up intermediate temp files...")
        processor.cleanup([audio_path, bg_video])

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())