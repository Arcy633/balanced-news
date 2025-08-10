from flask import Flask, render_template, request
import sqlite3
import feedparser
import threading
import time
import os
from newspaper import Article
from nltk.tokenize import sent_tokenize

app = Flask(__name__)

DB_FILE = "/opt/render/project/src/data/news.db"

# Define RSS feeds for each bias
RSS_FEEDS = {
    "left": [
        "https://rss.cnn.com/rss/edition.rss",
        "https://www.theguardian.com/world/rss"
    ],
    "center": [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.reutersagency.com/feed/?best-topics=world&post_type=best"
    ],
    "right": [
        "https://www.foxnews.com/about/rss",
        "https://www.theepochtimes.com/feed"
    ]
}

os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    title TEXT,
                    content TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

def summarize_text(text, max_sentences=5):
    """Simple extractive summarization: pick first few sentences."""
    sentences = sent_tokenize(text)
    return " ".join(sentences[:max_sentences])

def rewrite_summary(summary):
    """Very simple rewrite — you can replace this with more advanced logic."""
    return summary.replace("According to", "Reports suggest").replace("said", "stated")

def fetch_and_process():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    for category, feeds in RSS_FEEDS.items():
        all_texts = []

        for feed_url in feeds:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:3]:  # Take top 3 from each feed
                try:
                    article = Article(entry.link)
                    article.download()
                    article.parse()
                    if len(article.text) > 200:
                        all_texts.append(article.text)
                except Exception as e:
                    print(f"Error processing {entry.link}: {e}")

        if all_texts:
            combined_text = " ".join(all_texts)
            summary = summarize_text(combined_text, max_sentences=6)
            rewritten = rewrite_summary(summary)

            c.execute("INSERT INTO news (category, title, content) VALUES (?, ?, ?)",
                      (category, f"{category.capitalize()} Perspective", rewritten))

    conn.commit()
    conn.close()

def auto_refresh():
    while True:
        fetch_and_process()
        time.sleep(1800)  # every 30 mins

@app.route("/", methods=["GET", "POST"])
def index():
    search_query = request.args.get("q", "")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if search_query:
        c.execute("SELECT category, title, content FROM news WHERE content LIKE ? ORDER BY date_added DESC",
                  (f"%{search_query}%",))
    else:
        c.execute("SELECT category, title, content FROM news ORDER BY date_added DESC")

    rows = c.fetchall()
    conn.close()

    left_articles = [row for row in rows if row[0] == "left"]
    center_articles = [row for row in rows if row[0] == "center"]
    right_articles = [row for row in rows if row[0] == "right"]

    return render_template("index.html",
                           left_articles=left_articles,
                           center_articles=center_articles,
                           right_articles=right_articles,
                           search_query=search_query)

# Init & start
init_db()
fetch_and_process()
threading.Thread(target=auto_refresh, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
