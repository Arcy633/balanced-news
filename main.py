from flask import Flask, render_template, request
import sqlite3
import feedparser
import threading
import time
import os

app = Flask(__name__)

# Persistent DB path
DB_FILE = "/opt/render/project/src/data/news.db"

# RSS feeds mapped to bias
RSS_FEEDS = {
    "left": [
        "https://rss.cnn.com/rss/edition.rss"
    ],
    "center": [
        "https://feeds.bbci.co.uk/news/rss.xml"
    ],
    "right": [
        "https://www.espn.com/espn/rss/news"  # Example, replace with actual right-leaning feed
    ]
}

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
                    bias TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

def fetch_news():
    """Fetch news from all feeds and store unique ones."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for bias, feeds in RSS_FEEDS.items():
        for feed_url in feeds:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                thumbnail = ""
                if "media_content" in entry and len(entry.media_content) > 0:
                    thumbnail = entry.media_content[0]["url"]
                elif "links" in entry:
                    for link in entry.links:
                        if link.get("type", "").startswith("image"):
                            thumbnail = link["href"]
                            break
                try:
                    c.execute("""INSERT OR IGNORE INTO news 
                                 (title, link, published, thumbnail, bias) 
                                 VALUES (?, ?, ?, ?, ?)""",
                              (entry.title, entry.link, entry.published, thumbnail, bias))
                except Exception as e:
                    print("Error inserting:", e)
    conn.commit()
    conn.close()

def auto_refresh():
    """Fetch news every 30 minutes."""
    while True:
        fetch_news()
        time.sleep(1800)

@app.route("/", methods=["GET"])
def index():
    query = request.args.get("q", "").strip()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    articles = {}
    for bias in ["left", "center", "right"]:
        if query:
            c.execute("""SELECT title, link, published, thumbnail, bias
                         FROM news 
                         WHERE bias=? AND (title LIKE ? OR published LIKE ?)
                         ORDER BY date_added DESC LIMIT 5""",
                      (bias, f"%{query}%", f"%{query}%"))
        else:
            c.execute("""SELECT title, link, published, thumbnail, bias
                         FROM news 
                         WHERE bias=?
                         ORDER BY date_added DESC LIMIT 5""", (bias,))
        rows = c.fetchall()
        articles[bias] = rows

    conn.close()
    return render_template("compare.html", articles=articles, query=query)

# Initialize DB and start fetching
init_db()
fetch_news()
threading.Thread(target=auto_refresh, daemon=True).start()

if __name__ == "__main__":
    # Local run
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
