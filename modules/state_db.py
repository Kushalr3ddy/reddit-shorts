"""Pipeline state: which Reddit posts have been claimed/processed.

This replaces the old Supabase/Postgres `reddit_shorts_pipeline` table. The state is a tiny
SQLite file that lives in the R2/S3 bucket (see cloud_storage.STATE_DB_KEY):

    run start  -> download the .db from R2 (or start with an empty one if it doesn't exist yet)
    during run -> read/write it locally with plain sqlite3
    after claim, and again at the end of the run -> upload it back, replacing the one in R2

Why upload right after claiming too: the claim is only "real" for other runs once it is in R2,
so uploading immediately keeps the window for two overlapping runs picking the same post small.
It is NOT a real lock though - two runs started at the same moment can still race. The workflows
run twice a day so that's fine; if it ever matters, use a conditional put (If-Match on the ETag).
"""
import logging
import os
import sqlite3

from config import TEMP_DIR
from modules.cloud_storage import download_state_db, upload_state_db

logger = logging.getLogger(__name__)

# local working copy of the db. lives in temp/ but main.cleanup() only deletes files that start
# with a post id, so this survives until the process exits
LOCAL_DB_PATH = os.path.join(TEMP_DIR, "reddit_shorts_state.db")

_conn = None  # opened lazily by init_db()

# reddit_id is the PRIMARY KEY on purpose: a second INSERT for the same post raises
# IntegrityError, and that is exactly how claim_post() knows someone already took it
SCHEMA = """
CREATE TABLE IF NOT EXISTS reddit_shorts_pipeline (
    reddit_id  TEXT PRIMARY KEY,
    title      TEXT,
    subreddit  TEXT,
    status     TEXT NOT NULL,                       -- PROCESSING | DONE | FAILED
    youtube_id TEXT,                                -- filled in once the upload succeeds
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def init_db():
    """Pull the db from R2 (if there is one) and open it. Safe to call more than once."""
    global _conn
    if _conn is not None:
        return _conn

    os.makedirs(os.path.dirname(LOCAL_DB_PATH), exist_ok=True)
    # a stale local copy from a previous run must not win over what's in the bucket
    if os.path.exists(LOCAL_DB_PATH):
        os.remove(LOCAL_DB_PATH)

    if download_state_db(LOCAL_DB_PATH):
        logger.info("State db downloaded from R2.")
    else:
        logger.info("No state db in R2 yet, starting a fresh one.")

    # isolation_level=None = autocommit, same reasoning as the old psycopg2 setup:
    # every statement is its own transaction so one failed insert can't poison later queries
    _conn = sqlite3.connect(LOCAL_DB_PATH, isolation_level=None)
    _conn.execute(SCHEMA)
    return _conn


def push_db():
    """Upload the local db to R2, replacing the remote copy. Returns True on success."""
    if _conn is None:
        return False
    # fold any WAL/journal state into the main file so the single uploaded file is complete
    _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return upload_state_db(LOCAL_DB_PATH)


def get_processed_ids(reddit_ids):
    """Which of these ids are already in the table? One query for the whole list.

    Returns a set so the caller can filter locally. Status doesn't matter: anything we ever
    claimed (even a FAILED one) is skipped, same as the old postgres behaviour.
    """
    if not reddit_ids:
        return set()
    try:
        conn = init_db()
        ids = list(reddit_ids)
        found = set()
        # sqlite caps bound variables per statement (999 on old builds), so go in chunks
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            marks = ",".join("?" * len(chunk))
            rows = conn.execute(
                f"SELECT reddit_id FROM reddit_shorts_pipeline WHERE reddit_id IN ({marks})",
                chunk,
            )
            found.update(r[0] for r in rows)
        return found
    except Exception as e:
        logger.error(f"state db batch check failed: {e}")
        return set()


def claim_post(post_data):
    """Insert the post as PROCESSING so no other run takes it. False if it was already claimed.

    On success the db is pushed to R2 straight away so the claim is visible to other runs.
    """
    try:
        conn = init_db()
        conn.execute(
            "INSERT INTO reddit_shorts_pipeline (reddit_id, title, status, subreddit) "
            "VALUES (?, ?, 'PROCESSING', ?)",
            (post_data['id'], post_data['title'], post_data['subreddit']),
        )
    except sqlite3.IntegrityError:
        # primary key hit = already claimed. normal, not an error
        logger.info(f"post {post_data['id']} already claimed, skipping")
        return False
    except Exception as e:
        logger.error(f"couldn't claim post {post_data['id']}: {e}")
        return False

    if not push_db():
        # if the claim never reached R2 another run could grab the same post, so don't proceed
        logger.error("claimed locally but could not upload the state db; releasing claim")
        conn.execute("DELETE FROM reddit_shorts_pipeline WHERE reddit_id = ?", (post_data['id'],))
        return False
    return True


def mark_status(reddit_id, status, youtube_id=None):
    """Update a claimed post to DONE / FAILED (optionally with its YouTube id) and push to R2."""
    try:
        conn = init_db()
        conn.execute(
            "UPDATE reddit_shorts_pipeline "
            "SET status = ?, youtube_id = COALESCE(?, youtube_id), updated_at = CURRENT_TIMESTAMP "
            "WHERE reddit_id = ?",
            (status, youtube_id, reddit_id),
        )
        push_db()
    except Exception as e:
        logger.error(f"couldn't mark {reddit_id} as {status}: {e}")
