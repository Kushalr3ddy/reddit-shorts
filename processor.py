import os
import json
import random
import asyncio
import subprocess
import logging
import boto3
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from botocore.client import Config
from dotenv import load_dotenv
import edge_tts

load_dotenv()

# Logging Configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# R2 Configuration from .env
R2_ENDPOINT = os.getenv("bucket_endpoint")
R2_ACCESS_KEY = os.getenv("access_key_id")
R2_SECRET_KEY = os.getenv("secret_access_key")
BUCKET_NAME = os.getenv("bucket_name")

def get_r2_client():
    """Initializes the S3 client for Cloudflare R2."""
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )

async def generate_audio(text, post_id):
    """Converts Reddit text to a high-quality AI voiceover."""
    os.makedirs("temp", exist_ok=True)
    output_path = f"temp/{post_id}.mp3"
    
    # Using 'Christopher' - a popular deep voice for Reddit stories
    voice = "en-US-ChristopherNeural"
    communicate = edge_tts.Communicate(text, voice)
    
    try:
        await communicate.save(output_path)
        logger.info(f"Audio generated: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate audio: {e}")
        return None

def get_random_video_url(json_path="game_play_source.json"):
    """Picks a random video ID from the playlists in your JSON."""
    try:
        with open(json_path, 'r') as f:
            sources = json.load(f)
        
        game = random.choice(list(sources.keys()))
        playlist_url = sources[game]
        logger.info(f"Selected Game: {game}")

        # Get all video IDs from the playlist
        cmd = ['yt-dlp', '--get-id', '--flat-playlist', playlist_url]
        video_ids = subprocess.check_output(cmd).decode().splitlines()
        selected_id = random.choice(video_ids)
        
        return f"https://www.youtube.com/watch?v={selected_id}"
    except Exception as e:
        logger.error(f"Failed to get video URL: {e}")
        return None

def download_video_slice(youtube_url, post_id, duration=60):
    """Slices a random chunk from YouTube without downloading the full file."""
    os.makedirs("temp", exist_ok=True)
    output_path = f"temp/{post_id}_bg.mp4"
    
    try:
        # Get direct stream URL
        cmd_url = ['yt-dlp', '-g', '-f', 'bestvideo[height<=1080][ext=mp4]', youtube_url]
        direct_url = subprocess.check_output(cmd_url).decode().strip()

        # Random start time (start between 1-8 mins)
        start_time = random.randint(60, 480)
        
        logger.info(f"Slicing {duration}s from {youtube_url} starting at {start_time}s")
        
        ffmpeg_cmd = [
            'ffmpeg', '-ss', str(start_time), '-t', str(duration),
            '-i', direct_url, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
        return output_path
    except Exception as e:
        logger.error(f"Video slicing failed: {e}")
        return None

def assemble_video(bg_path, audio_path, title, post_id):
    """Crops to 9:16 and overlays title (Classic MoviePy v1.0.x syntax)."""
    output_path = f"temp/{post_id}_final.mp4"
    
    try:
        video = VideoFileClip(bg_path)
        audio = AudioFileClip(audio_path)
        
        # Sync duration to audio (max 59s for Shorts)
        final_dur = min(audio.duration, 59.0)
        video = video.subclip(0, final_dur).set_audio(audio)
        
        # Vertical Crop (9:16)
        w, h = video.size
        target_w = h * (9/16)
        video = video.crop(x_center=w/2, y_center=h/2, width=target_w, height=h)
        
        # Title Overlay - Using DejaVu-Sans-Bold (Standard on Ubuntu)
        txt = TextClip(
            title, 
            fontsize=45, 
            color='white', 
            font='DejaVu-Sans-Bold',
            method='caption', 
            size=(target_w*0.8, None), 
            bg_color='black'
        ).set_duration(final_dur).set_position('center').set_opacity(0.8)
        
        final = CompositeVideoClip([video, txt])
        
        logger.info(f"Rendering final video for {post_id}...")
        final.write_videofile(
            output_path, 
            codec="libx264", 
            audio_codec="aac", 
            fps=24, 
            threads=4,
            logger='bar'
        )
        
        # Resource cleanup
        video.close()
        audio.close()
        
        return output_path
    except Exception as e:
        logger.error(f"MoviePy Assembly failed: {e}")
        return None

def archive_to_r2(file_path, post_id):
    """Uploads finished video to your R2 bucket."""
    try:
        s3 = get_r2_client()
        r2_key = f"archives/{post_id}.mp4"
        s3.upload_file(file_path, BUCKET_NAME, r2_key)
        logger.info(f"✅ Successfully archived to R2: {r2_key}")
        return True
    except Exception as e:
        logger.error(f"R2 Archive failed: {e}")
        return False

def cleanup(files):
    """Deletes temporary assets."""
    for f in files:
        if f and os.path.exists(f):
            try:
                os.remove(f)
                logger.info(f"Cleaned up: {f}")
            except Exception as e:
                logger.warning(f"Could not delete {f}: {e}")