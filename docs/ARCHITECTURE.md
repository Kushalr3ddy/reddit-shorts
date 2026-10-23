# reddit-shorts documentation

Automated pipeline that turns a Reddit story into a vertical YouTube Short. One run of
`python main.py` produces exactly one video.

## Contents

1. [Overview](#overview)
2. [Quick start](#quick-start)
3. [Configuration](#configuration)
4. [Pipeline walkthrough](#pipeline-walkthrough)
5. [State database](#state-database)
6. [Module reference](#module-reference)
7. [Deployment](#deployment)
8. [Operations and troubleshooting](#operations-and-troubleshooting)
9. [Limitations and ideas](#limitations-and-ideas)

## Overview

```
 Reddit (PRAW)            state db (SQLite on R2)          edge-tts
 hot posts, 200-900  -->  drop seen ids, claim one   -->   mp3 voiceover
 chars                                                        |
                                                              v
 YouTube (Data API)  <--  R2 archive  <--  ffmpeg: gameplay stream (yt-dlp) + title + audio
 private upload           archives/<id>.mp4     crop 9:16, 1080x1920, max 59.5 s
```

Stack: Python 3.12, PRAW, edge-tts, yt-dlp, ffmpeg, boto3 (Cloudflare R2), SQLite, Google API client.

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
sudo apt install ffmpeg fonts-dejavu-core
# create .env (see Configuration), put client_secrets.json in the project root
python main.py          # first run opens a browser on port 8080 for YouTube OAuth
```

Docker: `docker compose build`, run once interactively with `docker compose run reddit-bot`
to finish OAuth (this writes `token.pickle`), after that `docker compose run reddit-bot` or
cron it. The container runs once and exits (`restart: "no"`).

## Configuration

### `.env`

| Key | Used by | Purpose |
|-----|---------|---------|
| `client_id`, `secret`, `app_name` | `reddit_ingest` | Reddit app credentials and user agent |
| `bucket_endpoint`, `bucket_name`, `access_key_id`, `secret_access_key` | `cloud_storage` | R2 / S3 bucket for archives and the state db |
| `USE_GPU` | `config` | `true` switches the encoder to `h264_vaapi` (default `libx264`) |
| `FONT_PATH` | `config` | Override the title font (default DejaVu Sans Bold) |

The old `db_url`, `db_port`, `postgres_user`, `postgres_password` keys are no longer read.

### Other files

| File | Purpose |
|------|---------|
| `client_secrets.json` | Google OAuth client, from the Google Cloud console |
| `token.pickle` | Saved YouTube credentials, created on first run |
| `youtube_cookies.txt` | Netscape-format cookies for yt-dlp; needed on datacenter IPs (CI, cloud) or YouTube blocks the bot |
| `game_play_source.json` | Map of category to YouTube playlist URL; one random video is used per run |
| `config.py` | Dimensions (1080x1920), paths, encoder, font |

Subreddits, the length window and the TTS voice are plain constants in the code (see below).

## Pipeline walkthrough

`main.py` `run_pipeline()`:

1. **Scan.** `get_top_posts_from_subreddits()` reads the 15 hottest posts of r/AmItheAsshole,
   r/TwoSentenceHorror, r/tifu and r/AskReddit. Stickied posts are skipped and only posts whose
   body is 200 to 900 characters are kept. No database calls happen during the scan.
2. **Dedupe.** One query against the state db removes every id seen before, whatever its status.
3. **Pick and claim.** Candidates are sorted longest first. `claim_post()` inserts the first one
   as `PROCESSING` and uploads the db to R2. If someone already claimed it, the next is tried.
4. **Voice.** `generate_audio()` strips markdown characters (`* # _`), synthesises
   `"<title>. <body>"` with voice `en-US-ChristopherNeural` into `temp/<id>.mp3` and reads its
   length with mutagen. Length is capped to 59.5 s for the render to stay inside the Shorts limit.
5. **Video.** `process_video_ffmpeg()`:
   - `get_random_gameplay_url()` picks a random category from `game_play_source.json`, then a random
     video of that playlist with `yt-dlp --flat-playlist --playlist-random`.
   - `yt-dlp -g` resolves a direct stream URL (mp4, up to 1080p), so nothing is downloaded.
   - ffmpeg seeks to a random point between 120 s and 600 s, crops to 9:16, scales to 1080x1920,
     draws the wrapped title (25 chars per line) in a translucent box and muxes the voiceover.
   - Output: `temp/<id>_final.mp4`.
6. **Archive.** `archive_video()` uploads to R2 at `archives/<id>.mp4` with `reddit_id` and
   `subreddit` metadata. Failure is logged and does not stop the upload.
7. **Upload.** `start_upload()` sends the video to YouTube as **private** (category 24). Title is
   the cleaned Reddit title cut to 75 chars plus `#shorts #reddit`; the description holds the
   subreddit and the first 400 chars of the story. Retriable errors (500, 502, 503, 504) back off
   exponentially up to 10 times.
8. **Finish.** In a `finally` block the post is marked `DONE` (with the YouTube id) or `FAILED`,
   the db is pushed to R2 and `temp/<id>*` files are removed.

## State database

A single SQLite file stored in the bucket at `state/reddit_shorts_state.db`
(`cloud_storage.STATE_DB_KEY`). Implemented in `modules/state_db.py`.

Lifecycle of a run:

1. First db access downloads the file to `temp/reddit_shorts_state.db`. If the key does not exist
   (first ever run) a fresh db is created. Any other download error aborts the run, so a network
   blip cannot silently reset the history.
2. All reads and writes are local, in autocommit mode.
3. After a successful claim the file is uploaded so other runs see it. If that upload fails the
   claim is rolled back and the post is skipped.
4. After the final status update the file is uploaded again.

Schema:

```sql
CREATE TABLE reddit_shorts_pipeline (
    reddit_id  TEXT PRIMARY KEY,      -- a second insert for the same post is the "already claimed" signal
    title      TEXT,
    subreddit  TEXT,
    status     TEXT NOT NULL,         -- PROCESSING | DONE | FAILED
    youtube_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Common tasks:

- Inspect: download the file from the R2 dashboard and run `sqlite3 reddit_shorts_state.db 'select * from reddit_shorts_pipeline'`.
- Retry a failed post: delete its row, upload the file back to the same key.
- Start over: delete the object in the bucket.

Concurrency: this is not a lock. Two runs started within seconds of each other can both claim the
same post, because the last upload wins. With the twice-a-day schedule this does not happen. If it
ever matters, use a conditional put (`If-Match` on the object ETag) when uploading.

## Module reference

| File | Responsibility |
|------|----------------|
| `main.py` | Orchestration, title sanitising, temp cleanup, final status |
| `config.py` | Paths, dimensions, encoder, font |
| `modules/reddit_ingest.py` | Reddit scan and filtering; re-exports `claim_post` |
| `modules/state_db.py` | SQLite state: `init_db`, `push_db`, `get_processed_ids`, `claim_post`, `mark_status` |
| `modules/audio_generator.py` | edge-tts voiceover and duration |
| `modules/video_processor.py` | Random gameplay pick, yt-dlp stream URL, ffmpeg render. Finds the venv's yt-dlp first (the system one is too old) and passes `--js-runtimes node:<path>` when available |
| `modules/cloud_storage.py` | R2 client, video archive, state db download and upload |
| `modules/youtube_upload.py` | OAuth, resumable upload with retries |
| `lightning_studio/` | Unused Lightning AI template scripts |
| `gpu_vendors.md` | Notes on free GPU hosts |

## Deployment

### GitHub Actions (`.github/workflows/pipeline.yml`)

Runs at 00:00 and 12:00 UTC and on manual dispatch, 15 minute timeout. Environment
`reddit-shorts-pipeline` must hold these secrets:

| Secret | Becomes |
|--------|---------|
| `ENV_FILE` | `.env` |
| `CLIENT_SECRETS` | `client_secrets.json` |
| `TOKEN_PICKLE_BASE64` | `token.pickle` (base64 of the local file) |
| `YT_COOKIES` | `youtube_cookies.txt` |

`env_check.yml` is a manual workflow that only verifies the secrets restore into non-empty files.

### Docker

`Dockerfile` is python:3.12-slim plus ffmpeg, DejaVu fonts, libmagic and CA certificates.
`docker-compose.yml` mounts the repo at `/app` so `token.pickle` persists.

## Operations and troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `no video id off the '<category>' playlist` | Playlist dead or private, or yt-dlp blocked. Refresh `youtube_cookies.txt`, update yt-dlp |
| ffmpeg 403 on the stream URL | yt-dlp ran without a JS runtime; install node |
| `No suitable stories found` | Everything in range was already used. Add subreddits in `reddit_ingest.py` |
| `Could not claim any candidate` | Every candidate was claimed or the state db upload failed (check bucket credentials) |
| Run aborts at start with a boto error | State db download failed for a reason other than "not found" |
| YouTube upload fails after re-auth | Delete `token.pickle` and run interactively once |
| Post never retried | By design, `FAILED` rows are skipped. Delete the row |

## Limitations and ideas

- Gameplay is streamed from YouTube on every run; storing clips in the bucket would be faster and
  less fragile.
- `FAILED` posts are permanent until the row is deleted. An attempt counter would allow retries.
- Uploads are private, change `privacyStatus` in `youtube_upload.py` to publish automatically.
- Subreddits, the length window and the voice are hardcoded constants.
