from flask import Flask, render_template, redirect
import feedparser
import sqlite3
import datetime
import os
import openai

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
            neutral TEXT,
            left TEXT,
            right TEXT,
            credibility TEXT,
            category TEXT,
            date_added TEXT,
            image TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_article(title, neutral, left, right, credibility, category, image):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO news (title, neutral, left, right, credibility, category, date_added, image)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (title, neutral, left, right, credibility, category,
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), image))
    conn.commit()
    conn.close()

def expand_with_ai(title, summary):
    prompt = f"""
    Provide three separate sections:
    Neutral Explanation:
    [Your neutral factual explanation here]

    Left Perspective:
    [Your left-leaning perspective here]

    Right Perspective:
    [Your right-leaning perspective here]

    Headline: {title}
    Summary: {summary}
    """
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        text = resp.choices[0].message["content"].strip()

        neutral, left, right = "", "", ""
        for line in text.split("\n"):
            if line.lower().startswith("neutral"):
                current = "neutral"
                continue
            elif line.lower().startswith("left"):
                current = "left"
                continue
            elif line.lower().startswith("right"):
                current = "right"
                continue

            if current == "neutral":
                neutral += line + "\n"
            elif current == "left":
                left += line + "\n"
            elif current == "right":
                right += line + "\n"

        return neutral.strip(), left.strip(), right.strip()
    except:
        return "Unavailable", "Unavailable", "Unavailable"

def fetch_and_process_news():
    feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.reutersagency.com/feed/?best-topics=politics"
    ]
    for url in feeds:
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            image_url = None
            if 'media_content' in entry and len(entry.media_content) > 0:
                image_url = entry.media_content[0]['url']
            elif 'links' in entry:
                for link in entry.links:
                    if link.get('type', '').startswith('image'):
                        image_url = link['href']
                        break

            neutral, left, right = expand_with_ai(entry.title, entry.summary)
            save_article(entry.title, neutral, left, right, "Verified", "Politics", image_url)

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

if __name__ == "__main__":
    init_db()
    fetch_and_process_news()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
