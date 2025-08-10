from flask import Flask, render_template, redirect
import feedparser
import sqlite3
import datetime
import os
import openai

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
DB_FILE = "news.db"

# ---------- Database ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE,
            summary TEXT,
            credibility TEXT,
            category TEXT,
            date_added TEXT,
            image TEXT
        )
    """)
    conn.commit()
    conn.close()

def article_exists(title):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM news WHERE title = ?", (title,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

def save_article(title, detailed, credibility, category, image):
    if article_exists(title):
        print(f"Skipping duplicate: {title}")
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO news (title, summary, credibility, category, date_added, image)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, detailed, credibility, category,
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), image))
    conn.commit()
    conn.close()

# ---------- AI Expansion ----------
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
        print("AI Error:", e)
        return "AI explanation unavailable."

# ---------- News Fetching ----------
def fetch_and_process_news():
    feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.reutersagency.com/feed/?best-topics=politics"
    ]
    for url in feeds:
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            image_url = None
            if 'media_content' in entry:
                image_url = entry.media_content[0]['url']
            elif 'links' in entry:
                for link in entry.links:
                    if link.type.startswith('image'):
                        image_url = link.href
                        break

            ai_text = expand_with_ai(entry.title, entry.summary)
            save_article(entry.title, ai_text, "Verified", "Politics", image_url)

# ---------- Routes ----------
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

# ---------- Main ----------
if __name__ == "__main__":
    init_db()
    fetch_and_process_news()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
