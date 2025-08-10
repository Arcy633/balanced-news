from flask import Flask, render_template, request
import requests
import os
import logging
import traceback

app = Flask(__name__)

# Enable logging to Render logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Example article fetch function with timeout and error handling
def fetch_articles(url):
    try:
        logger.info(f"Fetching articles from {url}")
        response = requests.get(url, timeout=8)  # Increased timeout for reliability
        response.raise_for_status()
        data = response.json()

        # Ensure we always return a list of articles
        if isinstance(data, dict) and "articles" in data:
            return data["articles"]
        elif isinstance(data, list):
            return data
        else:
            logger.warning(f"Unexpected JSON format from {url}")
            return []
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching data from {url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data from {url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching data from {url}: {traceback.format_exc()}")
    return []

@app.route("/", methods=["GET", "POST"])
def index():
    try:
        search_query = request.form.get("search", "").strip()

        # API URLs (replace with your real sources)
        left_url = "https://example.com/left.json"
        center_url = "https://example.com/center.json"
        right_url = "https://example.com/right.json"

        # Fetch articles
        left_articles = fetch_articles(left_url)
        center_articles = fetch_articles(center_url)
        right_articles = fetch_articles(right_url)

        # Filter by search query (case-insensitive) and keep multiple results
        if search_query:
            logger.info(f"Filtering results for search query: {search_query}")
            left_articles = [a for a in left_articles if search_query.lower() in a.get("title", "").lower()]
            center_articles = [a for a in center_articles if search_query.lower() in a.get("title", "").lower()]
            right_articles = [a for a in right_articles if search_query.lower() in a.get("title", "").lower()]

        return render_template(
            "index.html",
            left_articles=left_articles,
            center_articles=center_articles,
            right_articles=right_articles,
            search_query=search_query
        )
    except Exception as e:
        logger.error(f"Unhandled error in index route: {traceback.format_exc()}")
        return "Internal Server Error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
