# main.py
from flask import Flask, render_template, request
import sqlite3
import feedparser
import threading
import time
import os
import requests
import trafilatura
import re
from collections import Counter
import html

app = Flask(__name__)

# Persistent DB path (Render persistent disk mount)
DB_FILE = "/opt/render/project/src/data/news.db"

# RSS feeds mapped into bias categories
RSS_FEEDS_BY_BIAS = {
    "left": [
        "https://rss.cnn.com/rss/edition.rss",
    ],
    "center": [
        "https://feeds.bbci.co.uk/news/rss.xml",
    ],
    "right": [
        "https://www.espn.com/espn/rss/news"
    ]
}

# Ensure data directory exists
os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)

# --- DB utilities ----------------------------------------------------------------
def get_conn():
    return sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)

def init_db():
    """Create news table if it doesn't exist, and add missing columns."""
    conn = get_conn()
    c = conn.cursor()
    # Basic table (keeps previously-used columns plus new ones)
    c.execute('''CREATE TABLE IF NOT EXISTS news (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    link TEXT,
                    published TEXT,
                    thumbnail TEXT,
                    content TEXT,
                    category TEXT,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    # Ensure unique index on title to avoid duplicates (no double inserts)
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_news_title ON news(title)")
    conn.commit()
    conn.close()

# --- Text utilities ---------------------------------------------------------------
_SPLIT_SENT_RE = re.compile(r'(?<=[.!?])\s+')

# small set of english stopwords (expand if you want)
STOPWORDS = {
    "the","and","a","an","to","of","in","on","for","with","is","are","was","were","be",
    "that","this","it","by","as","at","from","or","has","have","had","its","their","they"
}

def clean_text(raw):
    if not raw:
        return ""
    # trafilatura returns cleaned text, but ensure whitespace and html-unescape
    t = html.unescape(raw)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def split_sentences(text):
    if not text:
        return []
    return [s.strip() for s in _SPLIT_SENT_RE.split(text) if s.strip()]

def top_keywords(text, n=3):
    words = re.findall(r'\w+', text.lower())
    words = [w for w in words if len(w) > 2 and w not in STOPWORDS]
    counts = Counter(words)
    keys = [w for w,_ in counts.most_common(n)]
    return keys

def summarize_by_scoring(text, max_sentences=6):
    """Simple extractive summarizer:
       score sentences by token frequency and pick top sentences (keeps order)."""
    text = clean_text(text)
    sentences = split_sentences(text)
    if not sentences:
        return "", ""
    tokens = re.findall(r'\w+', text.lower())
    freq = Counter(tokens)
    # Score each sentence
    sent_scores = []
    for s in sentences:
        s_tokens = re.findall(r'\w+', s.lower())
        score = sum(freq.get(t,0) for t in s_tokens)
        sent_scores.append((s, score))
    # pick top sentences
    top = sorted(sent_scores, key=lambda x: x[1], reverse=True)[:max_sentences]
    top_set = {s for s,_ in top}
    # preserve original order
    summary_sents = [s for s in sentences if s in top_set]
    summary = " ".join(summary_sents)
    # create a short generated headline based on keywords
    head_keys = top_keywords(summary, n=4)
    headline = " ".join(w.capitalize() for w in head_keys) or sentences[0][:60].strip()
    return headline.strip(), summary.strip()

# --- Fetch & Generate -------------------------------------------------------------
def fetch_full_text(url, timeout=10):
    """Download URL and extract article text using trafilatura."""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent":"Mozilla/5.0"})
        if resp.status_code != 200:
            return ""
        raw = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
        return raw or ""
    except Exception:
        return ""

def generate_article_for_category(category, feed_urls, items_per_feed=4):
    """Collects several articles per feed, extracts full text, and generates a single article (title+content)."""
    texts = []
    titles = []
    # parse each feed and collect top items
    for feed_url in feed_urls:
        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            continue
        entries = getattr(feed, "entries", [])[:items_per_feed]
        for entry in entries:
            # Some feeds provide full summary/content already, try that first
            candidate_text = ""
            if hasattr(entry, "content") and entry.content:
                candidate_text = " ".join([c.value for c in entry.content if hasattr(c, "value")])
            if not candidate_text and getattr(entry, "summary", None):
                candidate_text = entry.summary
            # If summary is short, try to fetch full article
            if not candidate_text or len(candidate_text.split()) < 80:
                full = fetch_full_text(getattr(entry, "link", "")) if getattr(entry, "link", None) else ""
                if full:
                    candidate_text = full
            candidate_text = clean_text(candidate_text)
            if candidate_text:
                texts.append(candidate_text)
                # Keep a short title candidate for fallback
                title_candidate = getattr(entry, "title", None) or ""
                if title_candidate:
                    titles.append(title_candidate)
    # Combine texts and summarize
    combined = "\n\n".join(texts)
    headline, summary = summarize_by_scoring(combined, max_sentences=6)
    # fallback headline
    if not headline and titles:
        headline = titles[0][:120]
    # final content: keep summary and a short disclosure-free expanded paragraph
    content = summary
    # If summary is short, add a bit more by taking the first 2 long paragraphs from combined
    if len(split_sentences(content)) < 3 and combined:
        paragraphs = [p for p in combined.split("\n\n") if len(p.split()) > 30]
        extra = "\n\n".join(paragraphs[:2])
        if extra:
            content = (content + "\n\n" + extra).strip()
    # ensure not empty
    if not content and texts:
        content = texts[0][:2000]
    if not headline:
        headline = (content.split(".")[0])[:120] if content else "News Update"
    return headline.strip(), content.strip()

def store_generated_article(title, content, category):
    """Insert generated article into DB if not already present (by unique title)."""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO news (title, link, published, thumbnail, content, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (title, "", "", "", content, category))
        conn.commit()
    except Exception as e:
        print("DB insert error:", e)
    finally:
        conn.close()

def fetch_news():
    """Main fetch loop: for each bias, generate an article and save it (no source attribution)."""
    print("Fetching & generating news articles...")
    for category, feeds in RSS_FEEDS_BY_BIAS.items():
        try:
            title, content = generate_article_for_category(category, feeds, items_per_feed=4)
            if title and content:
                store_generated_article(title, content, category)
                print(f"Stored generated article for [{category}]: {title[:60]}")
            else:
                print(f"No generated content for {category}")
        except Exception as e:
            print("Error generating for", category, e)

# --- Auto refresh thread ---------------------------------------------------------
def auto_refresh():
    """Fetch news every 30 minutes."""
    while True:
        try:
            fetch_news()
        except Exception as e:
            print("Auto refresh error:", e)
        time.sleep(1800)  # 30 minutes

# --- Flask routes ---------------------------------------------------------------
@app.route("/", methods=["GET"])
def index():
    q = request.args.get("q", "").strip()
    conn = get_conn()
    c = conn.cursor()
    # If there's a search query, search title + content and show multiple items per category
    if q:
        # simple full-text LIKE search (case-insensitive)
        pattern = f"%{q}%"
        c.execute("""
            SELECT title, content, category, date_added FROM news
            WHERE (title LIKE ? OR content LIKE ?)
            ORDER BY date_added DESC
        """, (pattern, pattern))
        rows = c.fetchall()
        # group results by category (allow multiple per category)
        grouped = {"left": [], "center": [], "right": []}
        for title, content, category, date_added in rows:
            cat = category if category in grouped else "center"
            grouped[cat].append({"title": title, "content": content, "date_added": date_added})
        conn.close()
        return render_template("compare.html", grouped=grouped, query=q)
    else:
        # Default: show latest by category (multiple articles per category)
        grouped = {"left": [], "center": [], "right": []}
        for cat in grouped.keys():
            c.execute("""
                SELECT title, content, date_added FROM news
                WHERE category = ?
                ORDER BY date_added DESC
                LIMIT 6
            """, (cat,))
            rows = c.fetchall()
            grouped[cat] = [{"title": r[0], "content": r[1], "date_added": r[2]} for r in rows]
        conn.close()
        return render_template("compare.html", grouped=grouped, query="")

# --- Start up -------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    # initial fetch so site has content immediately
    fetch_news()
    # start auto-refresh background thread
    threading.Thread(target=auto_refresh, daemon=True).start()
    # Render requires listening on PORT
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
else:
    # when imported by gunicorn - ensure DB/init and background thread still run
    init_db()
    fetch_news()
    threading.Thread(target=auto_refresh, daemon=True).start()
