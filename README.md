# Reddit-to-YouTube Shorts Automated ETL Pipeline

An automated data pipeline that extracts trending stories from Reddit, generates AI voiceovers, slices relevant gameplay footage from YouTube, and assembles high-retention vertical "Shorts" videos.

## System Architecture

The project follows a modular ETL (Extract, Transform, Load) pattern:

1.  **Extract**: Scrapes top posts from targeted subreddits using **PRAW** (Reddit API).
2.  **Verify**: Uses **Supabase (PostgreSQL)** to deduplicate posts and track processing status.
3.  **Transform**:
    * **Audio**: Generates AI voiceovers via **edge-tts**.
    * **Video**: Performs "Stream-Slicing" using **yt-dlp** and **FFmpeg** to pull random 60s clips from long-form gameplay.
    * **Assembly**: Crops to 9:16, overlays text, and renders the final MP4 using **MoviePy**.
4.  **Load**: 
    * Archives the master render to **Cloudflare R2** (use any S3-compatible storage).
    * Publishes to **YouTube** via the Data API v3.


---

## Tech Stack

* **Language**: Python 3.12
* **Database**: Supabase (PostgreSQL)
* **Cloud Storage**: Cloudflare R2
* **Video Engine**: MoviePy & FFmpeg
* **Scraping**: PRAW (Python Reddit API Wrapper)
* **Voice**: edge-tts (Microsoft Neural TTS)
* **Infrastructure**: Linux (Ubuntu)

---

##