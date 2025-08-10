from flask import Flask, render_template, request
import requests
import os
import logging

app = Flask(__name__)

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Example article fetch function with timeout and error handling
def fetch_articles(url):
    try:
        response = requests.get(url, timeout=5)  # timeout in seconds
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching data from {url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching data from {url}: {e}")
    return []


@app.route("/", methods=["GET", "POST"])
def index():
    search_query = request.form.get("search", "")

    # Example API URLs (replace with your actual sources)
    left_url = "https://example.com/left.json"
    center_url = "https://example.com/center.json"
    right_url = "https://example.com/right.json"

    # Fetch articles
    left_articles = fetch_articles(left_url)
    center_articles = fetch_articles(center_url)
    right_articles = fetch_articles(right_url)

    # Filter by search query
    if search_query:
        left_articles = [a for a in left_articles if search_query.lower() in a["title"].lower()]
        center_articles = [a for a in center_articles if search_query.lower() in a["title"].lower()]
        right_articles = [a for a in right_articles if search_query.lower() in a["title"].lower()]

    return render_template(
        "index.html",
        left_articles=left_articles,
        center_articles=center_articles,
        right_articles=right_articles,
        search_query=search_query
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
