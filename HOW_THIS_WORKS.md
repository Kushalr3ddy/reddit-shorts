# reddit-shorts : explained

> the plain-english version. for the formal writeup see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
> and the [README](README.md). this file is just me talking you through what actually happens.

## WHAT IS THIS THING

You want a faceless youtube channel that posts those reddit-story-over-gameplay
shorts, but you dont want to make them by hand. So this bot does the whole thing:
it grabs a story off reddit, reads it out loud in a robot voice, slaps that audio
over some random gameplay footage, crops it to phone-shape, and uploads it to
youtube. all on its own, twice a day.

one run of `python main.py` = exactly one video. thats it.

## THE BIG PICTURE

```
reddit story  ->  robot voice  ->  stick it over gameplay  ->  crop to 9:16  ->  upload to youtube
   (praw)         (edge-tts)         (yt-dlp + ffmpeg)           (ffmpeg)         (youtube api)
```

the whole thing is one straight line. [main.py](main.py) is the conductor, it calls
each piece in order. every piece lives in its own file in `modules/` so you can poke
at one without breaking the others.

## WALKING THROUGH ONE RUN   [main.py -> run_pipeline()]

1. **find stories** `[modules/reddit_ingest.py]`
   scan a few subreddits (AmItheAsshole, tifu, etc) for text posts between 200 and 900
   characters. too short = boring, too long = doesnt fit in a 60s short. skip the pinned
   mod posts, theyre never actual stories.

2. **dont repeat yourself** `[modules/state_db.py]`
   before we commit to a story we check we havent already done it (see the STATE DB bit
   below). out of everything thats left we grab the LONGEST story, cause longer = more
   watch time.

3. **claim it** `[modules/state_db.py]`
   write the post into the state db marked PROCESSING. if that write blows up it means
   another run already grabbed this one, so we just move to the next candidate. thats the
   whole "claiming" trick, no actual locks.

4. **robot voice** `[modules/audio_generator.py]`
   feed the title + body to edge-tts (microsofts free neural voices, no api key needed).
   out comes an mp3. we also measure how long it is cause everything downstream is timed
   to the audio.

5. **make the video** `[modules/video_processor.py]`
   this is the meaty part, see GAMEPLAY below. short version: download a random gameplay
   clip, crop it to 9:16, scale to 1080x1920, burn the story title on top in a black box,
   glue the robot-voice audio onto it, cut it to the length of the audio. one mp4 out.

6. **store + upload** `[modules/cloud_storage.py, modules/youtube_upload.py]`
   shove the finished mp4 into the R2 bucket as a backup, then upload it to youtube as a
   PRIVATE video (private on purpose so a bad render doesnt go public by accident, flip it
   yourself when youre happy).

7. **write down what happened**
   mark the post DONE (if the upload worked) or FAILED in the state db, push the db back to
   R2, and delete the temp files so we dont fill up the disk.

## THE STATE DB   [modules/state_db.py]  <- the clever bit

the problem: how does the bot remember which stories it already posted, ACROSS runs, when
each run is a fresh throwaway machine (github actions spins up a clean box every time)?

old answer: a supabase/postgres table. worked but its a whole hosted database for basically
a checklist. overkill.

new answer: a tiny SQLite file that lives IN the R2 bucket. the flow is:

```
run starts  ->  download the .db from R2  (or make an empty one if its the first ever run)
during run  ->  read/write it locally with plain sqlite3
after claim ->  upload it back to R2 immediately
run ends    ->  upload it back to R2 again
```

so R2 is the single source of truth and the db just rides along in it. the `reddit_id` is
the PRIMARY KEY, so trying to insert the same post twice throws an error, and THAT is how
`claim_post()` knows someone already took it. no extra lookup needed.

is it a real lock? no. two runs starting at the exact same second could both grab the same
story before either uploads the db. but the bot only runs twice a day so that basically
never happens. if it ever matters youd use a conditional put (If-Match on the ETag).

## THE GAMEPLAY   [modules/video_processor.py]

the background footage comes from youtube gameplay playlists listed in
[game_play_source.json](game_play_source.json). we pick a random playlist, pick a random
video out of it, and jump to a random spot deep into the video (skip the intro).

**why we DOWNLOAD the clip instead of streaming it.** the old way handed yt-dlp's stream
url straight to ffmpeg and let ffmpeg pull the bytes while rendering. clever, saves disk...
except youtube ties that stream url to whatever client ripped it, so ffmpeg fetching it with
a different user-agent just gets a 403 Forbidden and the whole render dies. so now we do a
proper yt-dlp download of the clip to `temp/<post_id>_gameplay.mp4` FIRST, let yt-dlp deal
with all the auth/headers nonsense itself, then render off that local file. costs disk and a
wait, but it actually works. the download gets deleted again as soon as were done with it.

**the js runtime thing.** newer yt-dlp wants a javascript runtime (node/deno) to properly
rip youtube. without one it quietly drops to a crippled client and youll get those 403s or
missing formats. the code auto-wires node if its on the box.

## THE YOUTUBE UPLOAD   [modules/youtube_upload.py]

uses the youtube data api v3 with oauth. first run opens a browser so you can log in once,
then it caches the login in `token.pickle` and reuses it forever (refreshing silently when
it expires). uploads are resumable with backoff so a flaky connection doesnt nuke a big
upload halfway.

## RUNNING IT FOR REAL (and what bites you)

- **it runs on a schedule.** `.github/workflows/pipeline.yml` fires it twice a day. you can
  also just `docker compose up` or run `python main.py` locally.

- **youtube WILL block you eventually.** if youre running from a datacenter IP (github
  actions, aws, a cheap vps) youtubes bot detection will start 403ing your downloads. the
  fix is cookies: export your youtube cookies and the bot uses them. see the link in the
  README. this isnt a bug in the bot, its just youtube being youtube.

- **secrets live in `.env`** (reddit keys, R2 keys, etc) and its gitignored. the youtube
  login is `token.pickle` + `client_secrets.json`, also never committed.

- **a FAILED post is never retried.** it stays in the state db so the dedupe skips it next
  time. if you want it picked up again, delete its row from the db.

## WHERE EVERYTHING LIVES

```
main.py                      the conductor, runs one full pass
config.py                    paths, video size, encoder choice
game_play_source.json        the gameplay playlists to pull from
modules/
  reddit_ingest.py           step 1: find candidate stories
  state_db.py                 the sqlite-on-R2 dedupe/claim logic
  audio_generator.py         step 3: text -> robot voice mp3
  video_processor.py         step 5: download gameplay + render the short
  cloud_storage.py           R2 bucket: video archive + the state db
  youtube_upload.py          step 6: oauth + resumable upload
docs/ARCHITECTURE.md         the formal, detailed writeup
```
