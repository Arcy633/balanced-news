from flask import Flask, render_template
import feedparser
import sqlite3
import threading
import time
from datetime import datetime

app = Flask(__name__)

DB_FILE = "news.db"

# RSS Feeds list
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://rss.cnn.com/rss/edition.rss",
    "https://feeds.npr.org/1001/rss.xml"
]

# ---------- DB INIT ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            link TEXT UNIQUE,
            image_url TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# ---------- FETCH NEWS ----------
def fetch_news():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries:
            title = entry.title
            link = entry.link
            image_url = ""
            if "media_content" in entry and entry.media_content:
                image_url = entry.media_content[0].get("url", "")
            elif "links" in entry:
                for l in entry.links:
                    if l.get("type", "").startswith("image/"):
                        image_url = l.get("href", "")
                        break
            try:
                c.execute("INSERT OR IGNORE INTO news (title, link, image_url) VALUES (?, ?, ?)",
                          (title, link, image_url))
            except sqlite3.Error as e:
                print("DB Error:", e)
    conn.commit()
    conn.close()

# ---------- AUTO REFRESH THREAD ----------
def auto_refresh():
    while True:
        print(f"[{datetime.now()}] Fetching latest news...")
        fetch_news()
        time.sleep(1800)  # 30 minutes

# ---------- ROUTES ----------
@app.route("/")
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, link, image_url, date_added FROM news ORDER BY date_added DESC")
    articles = c.fetchall()
    conn.close()
    return render_template("index.html", articles=articles)

# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()
    fetch_news()
    threading.Thread(target=auto_refresh, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
else:
    # For Render deployment
    init_db()
    fetch_news()
    threading.Thread(target=auto_refresh, daemon=True).start()
