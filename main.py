from flask import Flask, render_template
import sqlite3
import feedparser
import threading
import time
import os

app = Flask(__name__)

# Persistent DB path (Render persistent disk mount)
DB_FILE = "/opt/render/project/src/data/news.db"

# Your RSS feeds
RSS_FEEDS = [
    "https://rss.cnn.com/rss/edition.rss",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://www.espn.com/espn/rss/news"
]

# Ensure data directory exists
os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

def init_db():
    """Create news table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    link TEXT UNIQUE,
                    published TEXT,
                    thumbnail TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

def fetch_news():
    """Fetch news from all feeds and store unique ones."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            thumbnail = ""
            # Try to find image
            if "media_content" in entry and len(entry.media_content) > 0:
                thumbnail = entry.media_content[0]["url"]
            elif "links" in entry:
                for link in entry.links:
                    if link.get("type", "").startswith("image"):
                        thumbnail = link["href"]
                        break
            try:
                c.execute("INSERT OR IGNORE INTO news (title, link, published, thumbnail) VALUES (?, ?, ?, ?)",
                          (entry.title, entry.link, entry.published, thumbnail))
            except Exception as e:
                print("Error inserting:", e)
    conn.commit()
    conn.close()

def auto_refresh():
    """Fetch news every 30 minutes."""
    while True:
        fetch_news()
        time.sleep(1800)  # 30 minutes

@app.route("/")
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, link, published, thumbnail FROM news ORDER BY date_added DESC")
    articles = c.fetchall()
    conn.close()
    return render_template("index.html", articles=articles)

# Run on startup (for gunicorn on Render)
init_db()
fetch_news()
threading.Thread(target=auto_refresh, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
