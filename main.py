from flask import Flask, render_template, redirect
import feedparser
import sqlite3
import datetime
import os
import openai
import sys

app = Flask(__name__)

# --- API Key check ---
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    sys.stderr.write("ERROR: OPENAI_API_KEY environment variable not set.\n")
    sys.exit(1)

DB_FILE = "news.db"

# --- Database setup ---
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
            image TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_article(title, detailed, credibility, category, image):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO news (title, summary, credibility, category, date_added, image)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, detailed, credibility, category,
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), image))
    conn.commit()
    conn.close()

# --- AI Expansion ---
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
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        return resp.choices[0].message["content"].strip()
    except Exception as e:
        sys.stderr.write(f"OpenAI API Error: {e}\n")
        return "AI explanation unavailable."

# --- Fetch News ---
def fetch_and_process_news():
    feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://feeds.reuters.com/reuters/politicsNews"  # Fixed RSS feed
    ]
    for url in feeds:
        feed = feedparser.parse(url)
        if not feed.entries:
            sys.stderr.write(f"Warning: No entries found for feed {url}\n")
            continue
        for entry in feed.entries[:3]:
            ai_text = expand_with_ai(entry.title, entry.summary)
            save_article(entry.title, ai_text, "Verified", "Politics", None)

# --- Routes ---
@app.route("/")
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM news ORDER BY date_added DESC")
    news_items = c.fetchall()
    conn.close()
    return render_template("index.html", news_items=news_items)

@app.route("/refresh")
def refresh():
    fetch_and_process_news()
    return redirect("/")

# --- Main Entrypoint ---
if __name__ == "__main__":
    init_db()
    fetch_and_process_news()
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT dynamically
    app.run(host="0.0.0.0", port=port)
