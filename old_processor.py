import os
import json
import random
import subprocess
import logging
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
import edge_tts

logger = logging.getLogger(__name__)

async def generate_audio(text, post_id):
    """
    Step 1: The Master Clock.
    Generates audio and returns (path, duration).
    """
    os.makedirs("temp", exist_ok=True)
    audio_path = f"temp/{post_id}.mp3"
    
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(audio_path)
    
    # We load it briefly just to get the exact duration for the rest of the pipeline
    with AudioFileClip(audio_path) as temp_audio:
        duration = temp_audio.duration
    
    logger.info(f"Audio synced at {duration:.2f}s")
    return audio_path, duration

def download_video_slice(youtube_url, post_id, target_duration):
    """
    Step 2: Proportional Slicing.
    Slices a chunk based on the target_duration.
    """
    output_path = f"temp/{post_id}_bg.mp4"
    # Added 2s buffer to prevent 'End of file' errors in MoviePy
    slice_duration = target_duration + 2.0 
    
    try:
        # Get stream URL
        cmd_url = ['yt-dlp', '-g', '-f', 'bestvideo[height<=1080][ext=mp4]', youtube_url]
        direct_url = subprocess.check_output(cmd_url).decode().strip()

        # Random start point (offset by 1 min to avoid intros)
        start_time = random.randint(60, 300)
        
        ffmpeg_cmd = [
            'ffmpeg', '-ss', str(start_time), '-t', str(slice_duration),
            '-i', direct_url, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
        return output_path
    except Exception as e:
        logger.error(f"FFmpeg Slicing failed: {e}")
        return None

def assemble_video(bg_path, audio_path, title, post_id):
    """
    Step 3: Final Transform.
    Uses the exact duration from the audio file.
    """
    output_path = f"temp/{post_id}_final.mp4"
    
    try:
        # Using context managers ('with' statements) is best practice for Data Engineers 
        # as it handles resource cleanup automatically.
        with VideoFileClip(bg_path) as video, AudioFileClip(audio_path) as audio:
            
            final_dur = audio.duration
            
            # Sync & Set Audio
            video = video.subclip(0, final_dur).set_audio(audio)
            
            # 9:16 Vertical Crop
            w, h = video.size
            target_w = h * (9/16)
            video_vertical = video.crop(x_center=w/2, y_center=h/2, width=target_w, height=h)
            
            # Text Overlay (Ensuring font is Ubuntu-compatible)
            txt = TextClip(
                title, fontsize=45, color='white', font='DejaVu-Sans-Bold',
                method='caption', size=(target_w*0.8, None), bg_color='black'
            ).set_duration(final_dur).set_position('center').set_opacity(0.8)
            
            final = CompositeVideoClip([video_vertical, txt])
            
            logger.info(f"Rendering {post_id} at {final_dur:.2f}s duration...")
            final.write_videofile(
                output_path, 
                codec="libx264", 
                audio_codec="aac", 
                fps=24, 
                threads=4,
                logger=None # Set to 'bar' for a progress bar
            )
            
        return output_path
    except Exception as e:
        logger.error(f"Assembly failed: {e}")
        return None

def cleanup(files):
    """Removes temporary assets from the 'temp' folder."""
    for f in files:
        if f and os.path.exists(f):
            os.remove(f)
            logger.info(f"Purged: {f}")