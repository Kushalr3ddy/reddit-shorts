import edge_tts
import logging
import asyncio
from mutagen.mp3 import MP3

logger = logging.getLogger(__name__)

async def generate_audio(text, post_id):
    audio_path = f"temp/{post_id}.mp3"
    
    # 1. Clean the text (Remove weird characters that break TTS)
    # Edge-TTS can sometimes choke on emojis or strange Reddit formatting
    clean_text = text.replace("*", "").replace("#", "").replace("_", "").strip()

    try:
        # 2. Generate the stream
        communicate = edge_tts.Communicate(clean_text, "en-US-ChristopherNeural")
        
        # 3. Ensure the file is FULLY saved before moving on
        await communicate.save(audio_path)
        
        # 4. Small delay to ensure OS file handles are closed
        await asyncio.sleep(1) 
        
        # 5. Get Duration
        audio_info = MP3(audio_path)
        duration = audio_info.info.length
        
        if duration < 2:
            logger.error(f"Audio is suspiciously short: {duration}s")
            
        logger.info(f"Audio generated: {duration:.2f}s")
        return audio_path, duration

    except Exception as e:
        logger.error(f"TTS Failed: {e}")
        return None, 0