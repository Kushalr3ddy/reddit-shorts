"""Step 4: build the vertical video.

No gameplay file is downloaded: yt-dlp resolves a direct stream URL for a random video from the
playlists in game_play_source.json, and ffmpeg seeks into that stream, crops to 9:16, burns the
title in, and muxes the TTS audio - all in one pass.
"""
import json
import random
import subprocess
import os
import sys
import shutil
import logging
from config import VIDEO_ENCODER, WIDTH, HEIGHT, FONT_PATH, THREADS
import textwrap

logger = logging.getLogger(__name__)

def _resolve_yt_dlp():
    """grab the yt-dlp thats sitting inside our venv, NOT the /usr/bin one.
    the system one was like 2 years old and just choked on youtube. falls back to PATH if theres no venv copy"""
    candidate = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
    return candidate if os.path.exists(candidate) else "yt-dlp"

YT_DLP = _resolve_yt_dlp()

def _js_runtime_args():
    """new yt-dlp wants a js runtime to properly rip youtube. without one it silently drops to a
    crippled client and the stream url it spits out just 403s in ffmpeg later.
    so if node exists AND this yt-dlp knows the flag, point it at node. worked out once so we dont recheck every call"""
    node = shutil.which("node")
    if not node:
        return []
    try:
        help_txt = subprocess.run([YT_DLP, "--help"], capture_output=True, text=True).stdout
    except Exception:
        return []
    return ["--js-runtimes", f"node:{node}"] if "--js-runtimes" in help_txt else []

JS_RUNTIME_ARGS = _js_runtime_args()

def get_random_gameplay_url():
    """Selects a random video URL from the playlists in game_play_source.json"""
    try:
        with open("game_play_source.json", "r") as f:
            data = json.load(f)
        
        category = random.choice(list(data.keys()))
        playlist_url = data[category]
        
        cookie_file = 'youtube_cookies.txt'
        
        # FIXED COMMAND:
        # --playlist-random: Tells yt-dlp to shuffle the list
        # --max-downloads 1: Tells it to stop after picking one
        # --get-id: Returns just the ID
        
        # killed --quiet, it was eating the yt-dlp errors so everything looked fine while breaking. + js runtime args
        cmd = [
            YT_DLP,
            '--flat-playlist',
            '--get-id',
            '--playlist-random',
            '--max-downloads', '1',
            *JS_RUNTIME_ARGS,
            playlist_url
        ]

        # check if cookie file exists and add to command if it does
        if os.path.exists(cookie_file):
            cmd.extend(['--cookies', cookie_file])

        logger.info(f"Picking random video from {category} playlist...")
        res = subprocess.run(cmd, capture_output=True, text=True)

        # sometimes it hands back multiple ids, just take the first one
        video_id = res.stdout.strip().split("\n")[0] if res.stdout.strip() else ""

        # empty = playlist is dead/private/region locked or yt-dlp got blocked. bail here and say why,
        # otherwise we build a "watch?v=" with nothing after it and ffmpeg eats garbage 3 steps later
        if not video_id:
            logger.error(f"no video id off the '{category}' playlist. yt-dlp said: {res.stderr.strip()[-300:]}")
            return None

        return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        logger.error(f"Failed to get random gameplay: {e}")
        return None

def process_video_ffmpeg(audio_path, title, post_id, audio_duration):
    """Render temp/<post_id>_final.mp4 (audio_duration seconds long). Returns the path or None."""
    output_path = f"temp/{post_id}_final.mp4"
    
    # Get a fresh YouTube URL
    youtube_url = get_random_gameplay_url()
    if not youtube_url:
        return None

    gameplay_path = f"temp/{post_id}_gameplay.mp4"
    try:
        # grab the WHOLE gameplay clip to disk first, THEN render off the local file.
        # streaming the url straight into ffmpeg kept dying with 403s (youtube ties the
        # stream url to whatever client ripped it), a native download lets yt-dlp handle
        # all that itself. costs disk + a wait but its way more reliable than streaming
        logger.info(f"downloading gameplay: {youtube_url}")
        cookie_file = 'youtube_cookies.txt'

        dl_cmd = [
            YT_DLP,
            '-f', 'bestvideo[height<=1080][ext=mp4]/best[ext=mp4]/best',
            *JS_RUNTIME_ARGS,
            '-o', gameplay_path,
            youtube_url
        ]

        if os.path.exists(cookie_file):
            logger.info("found YouTube cookies, adding to yt-dlp command")
            dl_cmd.extend(['--cookies', cookie_file])

        subprocess.run(dl_cmd, check=True, capture_output=True)
        if not os.path.exists(gameplay_path):
            logger.error("yt-dlp finished but theres no gameplay file on disk, bailing")
            return None

        start_time = random.randint(120, 600) # Start deeper into the video (skip intros)
        # (an earlier safe_title was computed here without wrapping; it was immediately
        # overwritten below, so it has been removed)
        # 1. WRAP THE TEXT (Crucial for visibility)
        # This turns "One long sentence" into "One long\nsentence"
        wrapped_title = textwrap.fill(title, width=25) 
        safe_title = wrapped_title.replace("'", "'\\''").replace(":", "\\:")

        # 2. ROBUST FILTER
        # crop to 9:16 around the centre, scale to WIDTHxHEIGHT, draw title in a translucent box.
        # font comes from config.FONT_PATH
        # Note: Using 'DejaVuSans-Bold' which is standard on Ubuntu
        filter_complex = (
        f"[0:v]crop=ih*(9/16):ih,scale={WIDTH}:{HEIGHT},"
        f"drawtext=text='{safe_title}':"
        f"fontfile={FONT_PATH}:"
        f"fontsize=65:fontcolor=white:line_spacing=15:"
        f"box=1:boxcolor=black@0.6:boxborderw=40:" # Thick box for readability
        f"x=(w-text_w)/2:y=(h-text_h)/2 [v_out]"
    )

        cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-t', str(audio_duration + 1), # Input buffer
        '-i', gameplay_path,
        '-i', audio_path,
        '-filter_complex', filter_complex,
        '-map', '[v_out]',
        '-map', '1:a',
        '-c:v', VIDEO_ENCODER,
        '-c:a', 'aac',
        '-t', str(audio_duration),     # Output limit
        output_path
    ]

        logger.info("rendering off the downloaded gameplay file...")
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    except subprocess.CalledProcessError as e:
        # capture_output hides ffmpeg/yt-dlp stderr inside the exception, so dig it out and log WHY it died
        err = e.stderr.decode()[-500:] if e.stderr else str(e)
        logger.error(f"FFmpeg/yt-dlp error: {err}")
        return None
    except Exception as e:
        logger.error(f"FFmpeg/yt-dlp error: {e}")
        return None
    finally:
        # ditch the big gameplay download either way, no point sitting on 100s of MB
        if os.path.exists(gameplay_path):
            try:
                os.remove(gameplay_path)
            except OSError:
                pass