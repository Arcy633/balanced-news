import os
from flask import Flask, render_template, request
import feedparser
from openai import OpenAI

# Flask app
app = Flask(__name__)

# OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# News RSS feeds
FEEDS = {
    "left": [
        "https://www.theguardian.com/world/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"
    ],
    "center": [
        "https://feeds.bbci.co.uk/news/world/rss.xml"
    ],
    "right": [
        "https://www.foxnews.com/about/rss",
        "https://www.washingtontimes.com/rss/headlines/news/world/"
    ]
}

def rewrite_article(text):
    """Rewrites text via GPT so it becomes unique and unbiased."""
    try:
        prompt = f"Rewrite the following news content in your own words, concise and neutral. Do not mention the original site:\n\n{text}"
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a journalist who rewrites articles clearly without bias."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print("Rewrite failed:", e)
        return text

def fetch_news(feed_urls, search_query=None):
    """Fetch and rewrite news articles from feed URLs."""
    articles = []
    for url in feed_urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:  # multiple per feed
            if search_query and search_query.lower() not in entry.title.lower():
                continue
            rewritten_title = rewrite_article(entry.title)
            rewritten_summary = rewrite_article(entry.summary)
            articles.append({
                "title": rewritten_title,
                "summary": rewritten_summary,
                "link": "#"  # Remove original link to make it your own
            })
    return articles

@app.route("/", methods=["GET", "POST"])
def index():
    search_query = request.args.get("q", "").strip()
    articles = {category: fetch_news(urls, search_query) for category, urls in FEEDS.items()}
    return render_template("index.html", articles=articles, search_query=search_query)

if __name__ == "__main__":
    app.run(debug=True)
