from flask import Flask, render_template, redirect
import feedparser
import sqlite3
import datetime
import os
import openai

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
DB_FILE = "news.db"

# ------------------ DATABASE SETUP ------------------

def init_db():
    """Create the news table if it doesn't exist."""
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
            neutral TEXT,
            left TEXT,
            right TEXT
        )
    """)
    conn.commit()
    conn.close()

def migrate_db():
    """Ensure all required columns exist (safe for redeploys)."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    columns_to_add = [
        ("neutral", "TEXT"),
        ("left", "TEXT"),
        ("right", "TEXT"),
        ("credibility", "TEXT"),
        ("category", "TEXT"),
        ("image", "TEXT")
    ]

    for col, col_type in columns_to_add:
        try:
            c.execute(f"ALTER TABLE news ADD COLUMN {col} {col_type}")
            print(f"Added column: {col}")
        except sqlite3.OperationalError:
            # Happens if the column already exists
            pass

    conn.commit()
    conn.close()

# ------------------ DATA STORAGE ------------------

def save_article(title, detailed, credibility, category, image):
    """Save an article to the database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO news (title, summary, credibility, category, date_added, image)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, detailed, credibility, category,
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), image))
    conn.commit()
    conn.close()

# ------------------ AI PROCESSING ------------------

def expand_with_ai(title, summary):
    """Use OpenAI to generate perspectives."""
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
        print(f"AI Error: {e}")
        return "AI explanation unavailable."

# ------------------ FETCHING NEWS ------------------

def fetch_and_process_news():
    """Fetch news from RSS feeds and store with AI expansion."""
    feeds = [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://www.reutersagency.com/feed/?best-topics=politics"
    ]
    for url in feeds:
        feed = feedparser.parse(url)
        for entry in feed.entries[:3]:
            ai_text = expand_with_ai(entry.title, entry.summary)
            save_article(entry.title, ai_text, "Verified", "Politics", None)

# ------------------ ROUTES ------------------

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

# ------------------ APP START ------------------

if __name__ == "__main__":
    init_db()        # Create table if not exists
    migrate_db()     # Ensure all columns exist
    fetch_and_process_news()  # Initial fetch
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT automatically
    app.run(host="0.0.0.0", port=port)
