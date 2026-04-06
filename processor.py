import subprocess
import random
import logging
import os
from moviepy.editor import VideoFileClip, AudioFileClip

logger = logging.getLogger(__name__)

def get_video_duration(url):
    """Fetch the duration of a YouTube video without downloading it."""
    cmd = [
        'yt-dlp', 
        '--get-duration', 
        url
    ]
    try:
        duration_str = subprocess.check_output(cmd).decode().strip()
        # Convert H:M:S to total seconds
        parts = list(map(int, duration_str.split(':')))
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        return parts[0]
    except Exception:
        return 600 # Default to 10 mins if it fails

def download_random_slice(youtube_url, post_id, slice_duration=60):
    """Streams a random slice from a long YT video directly to a temp file."""
    os.makedirs("temp", exist_ok=True)
    output_path = f"temp/{post_id}_bg.mp4"
    
    total_duration = get_video_duration(youtube_url)
    
    # Pick a random start time, leaving room for the slice
    # We avoid the first 30s (intros) and the last 30s (outros)
    start_time = random.randint(30, max(31, int(total_duration) - slice_duration - 30))
    
    logger.info(f"Slicing {slice_duration}s starting at {start_time}s from {youtube_url}")

    # The 'magic' command: downloads ONLY the bytes needed for the slice
    cmd = [
        'yt-dlp',
        '-g', youtube_url, # Get the direct URL
        '-f', 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    ]
    
    try:
        direct_url = subprocess.check_output(cmd).decode().strip()
        
        # Use ffmpeg to cut the stream
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-t', str(slice_duration),
            '-i', direct_url,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-strict', 'experimental',
            '-y', output_path
        ]
        
        subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
        return output_path
    except Exception as e:
        logger.error(f"Slicing failed: {e}")
        return None

def generate_tts(text, post_id):
    """Generates TTS audio from text using edge-tts."""
    os.makedirs("temp", exist_ok=True)
    output_path = f"temp/{post_id}_tts.mp3"
    
    # Command to run edge-tts CLI
    cmd = [
        'edge-tts',
        '--text', text,
        '--write-media', output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return None

def assemble_video(bg_video_path, tts_audio_path, output_path):
    """Combines the background video and TTS audio using MoviePy."""
    try:
        video_clip = VideoFileClip(bg_video_path)
        audio_clip = AudioFileClip(tts_audio_path)
        
        # Trim the background video to exactly match the audio duration
        video_clip = video_clip.subclip(0, audio_clip.duration)
        
        # Set the generated TTS as the video's audio track
        final_clip = video_clip.set_audio(audio_clip)
        
        # Write the final video (logger=None removes verbose moviepy output)
        final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=30, logger=None)
        
        # Free resources
        video_clip.close()
        audio_clip.close()
        final_clip.close()
        return output_path
    except Exception as e:
        logger.error(f"Video assembly failed: {e}")
        return None

def process_reddit_short(post_data, bg_youtube_url):
    """Full pipeline: TTS -> Dynamic Background Slicing -> Assembly."""
    post_id = post_data["id"]
    text = f"{post_data['title']}. {post_data['content']}"
    
    # 1. Generate TTS
    logger.info(f"Generating TTS for {post_id}...")
    tts_path = generate_tts(text, post_id)
    if not tts_path:
        return None
        
    # 2. Get dynamic slice_duration based on TTS length
    audio_clip = AudioFileClip(tts_path)
    dynamic_slice_duration = int(audio_clip.duration) + 2  # Give a 2-second buffer
    audio_clip.close()
    
    # 3. Download Background using the dynamically calculated length
    logger.info(f"Downloading {dynamic_slice_duration}s background slice...")
    bg_path = download_random_slice(bg_youtube_url, post_id, slice_duration=dynamic_slice_duration)
    if not bg_path:
        return None
        
    # 4. Assemble Final Video
    os.makedirs("output", exist_ok=True)
    final_video_path = f"output/{post_id}_final.mp4"
    logger.info(f"Assembling final video to {final_video_path}...")
    
    return assemble_video(bg_path, tts_path, final_video_path)