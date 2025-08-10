# main.py
from flask import Flask, render_template, redirect
import feedparser
import sqlite3
import datetime
import os
import threading
import time
from bs4 import BeautifulSoup

# OpenAI compatibility: prefer new OpenAI client, fallback to old openai lib
try:
    from openai import OpenAI as OpenAIClient
    OPENAI_CLIENT = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    def ai_chat(prompt, model="gpt-3.5-turbo", max_tokens=400):
        resp = OPENAI_CLIENT.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message["content"].strip()
except Exception:
    import openai
    openai.api_key = os.getenv("OPENAI_API_KEY")
    def ai_chat(prompt, model="gpt-3.5-turbo", max_tokens=400):
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message["content"].strip()

app = Flask(__name__)
DB_FILE = os.getenv("DB_FILE", "news.db")

# Create DB if missing
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary TEXT,
            credibility TEXT,
            category TEXT,
            date_added TEXT,
            image TEXT,
            UNIQUE(title)
        )
    """)
    conn.commit()
    conn.close()

def save_article(title, detailed, credibility, category, image):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO news (title, summary, credibility, category, date_added, image)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, detailed, credibility, category,
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), image))
        conn.commit()
    except sqlite3.IntegrityError:
        # duplicate title (already stored) - skip
        pass
    finally:
        conn.close()

def expand_with_ai(title, summary):
    prompt = f"""
    Provide:
    1. Neutral factual explanation
    2. Left-leaning perspective
    3. Right-leaning perspective

    Headline: {title}
    Summary: {summary}
    """
    try:
        return ai_chat(prompt)
    except Exception as e:
        # log quietly, but return fallback text
        print("OpenAI API Error:", e)
        return "AI explanation unavailable."

def get_thumbnail_from_entry(entry):
    # feedparser often exposes media_content/media_thumbnail
    if "media_thumbnail" in entry:
        thumbs = entry.media_thumbnail
        if isinstance(thumbs, list) and len(thumbs) > 0:
            return thumbs[0].get("url")
        elif isinstance(thumbs, dict):
            return thumbs.get("url")
    if "media_content" in entry:
        mc = entry.media_content
        if isinstance(mc, list) and len(mc) > 0:
            return mc[0].get("url")
    # some feeds put an "image" field
    if "image" in entry:
        img = entry.image
        if isinstance(img, dict):
            return img.get("href") or img.get("url")
    # fallback: parse summary/html for first <img>
    html = entry.get("summary") or entry.get("content", [{}])[0].get("value", "")
    if html:
        soup = BeautifulSoup(html, "html.parser")
        img_tag = soup.find("img")
        if img_tag and img_tag.get("src"):
            return img_tag.get("src")
    # No thumbnail found
    return None

# RSS sources
FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.reuters.com/reuters/politicsNews",
]

# fetch -> for each article check duplicate by title (DB UNIQUE prevents duplicates)
def fetch_and_process_news(max_per_feed=5):
    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print("Feed parse error for", url, e)
            continue
        entries = getattr(feed, "entries", [])[:max_per_feed]
        for entry in entries:
            title = entry.get("title", "No title")
            summary = entry.get("summary", "") or entry.get("description", "")
            image = get_thumbnail_from_entry(entry)
            # Expand via AI (may fail gracefully)
            ai_text = expand_with_ai(title, summary)
            save_article(title, ai_text, "Verified", "Politics", image)

# Background thread to auto-refresh every 30 minutes
def start_background_refresh(interval_minutes=30):
    def loop():
        while True:
            try:
                print("Background fetch starting:", datetime.datetime.now())
                fetch_and_process_news()
                print("Background fetch complete:", datetime.datetime.now())
            except Exception as e:
                print("Background fetch error:", e)
            time.sleep(interval_minutes * 60)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

# Flask routes
@app.route("/")
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, summary, credibility, category, date_added, image FROM news ORDER BY date_added DESC")
    news_items = c.fetchall()
    conn.close()
    # transform tuples into dicts for template ease
    items = []
    for r in news_items:
        items.append({
            "id": r[0],
            "title": r[1],
            "summary": r[2],
            "cred": r[3],
            "category": r[4],
            "date": r[5],
            "image": r[6]
        })
    return render_template("index.html", news_items=items)

@app.route("/refresh")
def refresh():
    # manual refresh endpoint
    fetch_and_process_news()
    return redirect("/")

# Initialize DB and start background refresh when module imported
init_db()
# Immediately fetch once at startup
try:
    fetch_and_process_news()
except Exception as e:
    print("Initial fetch error:", e)

# Start background refresher (30 minutes)
start_background_refresh(interval_minutes=int(os.getenv("REFRESH_MINUTES", "30")))

if __name__ == "__main__":
    # Allow running locally with: python main.py
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
