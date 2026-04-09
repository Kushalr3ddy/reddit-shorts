import os
import json
import random
import asyncio
import subprocess
import logging
from moviepy.editor import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip

logger = logging.getLogger(__name__)

async def generate_audio(text, post_id):
    """Generates audio and returns (path, duration)."""
    os.makedirs("temp", exist_ok=True)
    audio_path = f"temp/{post_id}.mp3"
    
    import edge_tts
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(audio_path)
    
    # Get the actual duration of the generated audio
    temp_audio = AudioFileClip(audio_path)
    duration = temp_audio.duration
    temp_audio.close() # Close immediately so the file isn't 'busy'
    
    logger.info(f"Audio generated: {duration:.2f} seconds")
    return audio_path, duration

def download_video_slice(youtube_url, post_id, target_duration):
    """Slices a chunk exactly as long as the audio + a 1s buffer."""
    os.makedirs("temp", exist_ok=True)
    output_path = f"temp/{post_id}_bg.mp4"
    
    # Add a 1-second buffer to ensure MoviePy doesn't run out of frames
    slice_duration = target_duration + 1.0 
    
    try:
        cmd_url = ['yt-dlp', '-g', '-f', 'bestvideo[height<=1080][ext=mp4]', youtube_url]
        direct_url = subprocess.check_output(cmd_url).decode().strip()

        # Random start time (assuming 10min video)
        start_time = random.randint(60, 400)
        
        logger.info(f"Slicing {slice_duration:.2f}s starting at {start_time}s")
        
        ffmpeg_cmd = [
            'ffmpeg', '-ss', str(start_time), '-t', str(slice_duration),
            '-i', direct_url, '-c:v', 'libx264', '-c:a', 'aac', '-y', output_path
        ]
        subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
        return output_path
    except Exception as e:
        logger.error(f"Slicing failed: {e}")
        return None

def assemble_video(bg_path, audio_path, title, post_id):
    """Assembles video using the natural duration of the audio clip."""
    output_path = f"temp/{post_id}_final.mp4"
    
    try:
        video = VideoFileClip(bg_path)
        audio = AudioFileClip(audio_path)
        
        # Sync video to exact audio length
        final_dur = audio.duration
        video = video.subclip(0, final_dur).set_audio(audio)
        
        # 9:16 Crop
        w, h = video.size
        target_w = h * (9/16)
        video = video.crop(x_center=w/2, y_center=h/2, width=target_w, height=h)
        
        # Text Overlay
        txt = TextClip(
            title, fontsize=45, color='white', font='DejaVu-Sans-Bold',
            method='caption', size=(target_w*0.8, None), bg_color='black'
        ).set_duration(final_dur).set_position('center').set_opacity(0.8)
        
        final = CompositeVideoClip([video, txt])
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=24, threads=4)
        
        video.close()
        audio.close()
        return output_path
    except Exception as e:
        logger.error(f"Assembly failed: {e}")
        return None