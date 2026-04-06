import os
import json
import random
import asyncio
import subprocess
import logging
import boto3
import edge_tts
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# R2 Configuration
R2_ENDPOINT = os.getenv("bucket_endpoint")
R2_ACCESS_KEY = os.getenv("access_key_id")
R2_SECRET_KEY = os.getenv("secret_access_key")
BUCKET_NAME = os.getenv("bucket_name")

s3 = boto3.client(
    's3',
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    config=Config(signature_version='s3v4'),
    region_name='auto'
)

async def generate_audio(text, post_id):
    """Converts Reddit text to speech."""
    os.makedirs("temp", exist_ok=True)
    output_path = f"temp/{post_id}.mp3"
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_path)
    logger.info(f"Audio saved: {output_path}")
    return output_path

def get_random_video_url(json_path="game_play_source.json"):
    """Picks a random video ID from the playlists in your JSON."""
    with open(json_path, 'r') as f:
        sources = json.load(f)
    game = random.choice(list(sources.keys()))
    playlist_url = sources[game]
    
    cmd = ['yt-dlp', '--get-id', '--flat-playlist', playlist_url]
    video_ids = subprocess.check_output(cmd).decode().splitlines()
    selected_id = random.choice(video_ids)
    return f"https://www.youtube.com/watch?v={selected_id}"

def download_video_slice(youtube_url, post_id, duration=60):
    """Slices a random 60s chunk from YouTube without downloading the full file."""
    output_path = f"temp/{post_id}_bg.mp4"
    
    # Get direct stream URL
    cmd_url = ['yt-dlp', '-g', '-f', 'bestvideo[height<=1080][ext=mp4]', youtube_url]
    direct_url = subprocess.check_output(cmd_url).decode().strip()

    # Random start time (assuming 10min video, start between 1-8 mins)
    start_time = random.randint(60, 480)
    
    ffmpeg_cmd = [
        'ffmpeg', '-ss', str(start_time), '-t', str(duration),
        '-i', direct_url, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path
    ]
    subprocess.run(ffmpeg_cmd, capture_output=True)
    logger.info(f"Video slice saved: {output_path}")
    return output_path

def assemble_video(bg_path, audio_path, title, post_id):
    """Crops to 9:16 and overlays title."""
    output_path = f"temp/{post_id}_final.mp4"
    
    video = VideoFileClip(bg_path)
    audio = AudioFileClip(audio_path)
    
    # Sync duration to audio (max 59s for Shorts)
    final_dur = min(audio.duration, 59.0)
    video = video.subclip(0, final_dur).set_audio(audio)
    
    # Vertical Crop
    w, h = video.size
    target_w = h * (9/16)
    video = video.crop(x_center=w/2, y_center=h/2, width=target_w, height=h)
    
    # Title Overlay
    txt = TextClip(title, fontsize=50, color='white', font='Arial-Bold',
                   method='caption', size=(target_w*0.8, None), bg_color='black')
    txt = txt.set_duration(final_dur).set_position('center').set_opacity(0.8)
    
    final = CompositeVideoClip([video, txt])
    final.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24, threads=4)
    return output_path

def archive_to_r2(file_path, post_id):
    """Uploads finished video to your 'shitposting-bot' bucket."""
    r2_key = f"archives/{post_id}.mp4"
    s3.upload_file(file_path, BUCKET_NAME, r2_key)
    logger.info(f"Archived to R2: {r2_key}")

def cleanup(files):
    """Deletes temporary assets."""
    for f in files:
        if f and os.path.exists(f):
            os.remove(f)
            logger.info(f"Cleaned up: {f}")


if __name__ == "__main__":
    # Mock data for testing
    test_id = "test_123"
    test_text = "This is a test story for my Reddit pipeline. It should be long enough to hear the voice."
    test_title = "Testing the Processor Module"

    async def test():
        audio = await generate_audio(test_text, test_id)
        yt_url = get_random_video_url()
        video_bg = download_video_slice(yt_url, test_id)
        
        final = assemble_video(video_bg, audio, test_title, test_id)
        archive_to_r2(final, test_id)
        
        # Uncomment to clean up after test
        # cleanup([audio, video_bg, final])
        print(f"🚀 SUCCESS: Check {final}")

    asyncio.run(test())