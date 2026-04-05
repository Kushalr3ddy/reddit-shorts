import praw
import os
from dotenv import load_dotenv
import logging


load_dotenv()

SUBREDDITS = ["AskReddit","TwoSentenceHorror","AmItheAsshole","Showerthoughts","TodayILearned","UnpopularOpinion"]
REDDIT_CLIENT_ID = os.getenv("client_id")
REDDIT_CLIENT_SECRET = os.getenv("secret")


def get_reddit_posts():

    reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent="my user agent",
    )
    posts =[]
    for sub_reddit in SUBREDDITS:
        cur_sub = reddit.subreddit(sub_reddit)
        for submission in cur_sub.top(time_filter="day", limit=10):
                if not submission.is_self or len(submission.selftext) < 100:
                    continue  # Skip image posts or very short ones
                
                posts.append({
                    "id": submission.id,
                    "title": submission.title,
                    "content": submission.selftext,
                    "score": submission.score
                })
    return posts[0] if posts else None
    

if __name__ == "__main__":
    reddit_posts = get_reddit_posts()
    