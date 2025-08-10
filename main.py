from flask import Flask, render_template, redirect
import feedparser
import sqlite3
import datetime
import os
import openai
import re

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
DB_FILE = "news.db"

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

def expand_with_ai(title, summary):
    prompt = f"""
    Provide the following perspectives on the news headline and summary.
    Format your response exactly like this:
    NEUTRAL: <text>
    LEFT: <text>
    RIGHT: <text>

    Headline: {title}
    Summary: {summary}
    """
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400
        )
        content = resp.choices[0].message["content"].strip()

        neutral, left, right = "", "", ""
        for line in content.split("\n"):
            if line.startswith("NEUTRAL:"):
                neutral = line.replace("NEUTRAL:", "").strip()
            elif line.startswith("LEFT:"):
                left = line.replace("LEFT:", "").strip()
            elif line.startswith("RIGHT:"):
                right = line.replace("RIGHT:", "").strip()

        return f"{neutral}|||{left}|||{right}"
    except Exception as e:
        return "Unable to get AI output||| |||"

def extract_image(entry):
    # Try 'media_content'
    if "media_content" in entry and entry.media_content:
        return entry.media_content[0].get("url")

    # Try 'media_thumbnail'
    if "media_thumbnail" in entry and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url")

    # Try to find image in summary/detail HTML
    if hasattr(entry, "summary"):
        match = re.search(r'<img[^>]+src="([^"]+)"', entry.summary)
        if match:
            return match.group(1)

    # No image found, use placeholder
    return "https://via.placeholder.com/600x400?text=No+Image"

def fetch_and_process_news():
    feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.reutersagency.com/feed/?best-topics=politics"
    ]
    for url in feeds:
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            ai_text = expand_with_ai(entry.title, entry.summary)
            img_url = extract_image(entry)
            save_article(entry.title, ai_text, "Verified", "Politics", img_url)

@app.route("/")
def index():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM news ORDER BY date_added DESC")
    news_items = c.fetchall()
    conn.close()
    return render_template("index.html", news_items=news_items, current_year=datetime.datetime.now().year)

@app.route("/refresh")
def refresh():
    fetch_and_process_news()
    return redirect("/")

if __name__ == "__main__":
    init_db()
    fetch_and_process_news()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
