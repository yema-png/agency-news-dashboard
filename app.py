"""
AndIron Group — Weekly News Dashboard
======================================
Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and add your API keys
  3. python app.py
  4. Open http://localhost:5000
"""

from flask import Flask, render_template, jsonify, redirect, url_for, request
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CACHE_FILE = os.path.join(os.path.dirname(__file__), "news_cache.json")


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_config():
    with open(os.path.join(os.path.dirname(__file__), "config.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"cache": {}, "last_refresh": None, "status": {}}


def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_top_stories(cache_data, client_colors, client_names, n=5):
    """Return top-N articles across all clients by relevance score."""
    all_articles = []
    for client_id, articles in cache_data.get("cache", {}).items():
        for article in articles:
            a = article.copy()
            a["client_id"] = client_id
            a["client_name"] = client_names.get(client_id, client_id)
            a["client_color"] = client_colors.get(client_id, "#4f8ef5")
            all_articles.append(a)
    all_articles.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return all_articles[:n]


def current_week_label():
    today = datetime.now()
    return today.strftime("Week of %-d %B %Y") if os.name != "nt" else today.strftime(f"Week of {today.day} %B %Y")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def overview():
    config = load_config()
    cache_data = load_cache()

    client_names = {c["id"]: c["name"] for c in config["clients"]}
    client_colors = {c["id"]: c.get("color", "#4f8ef5") for c in config["clients"]}

    top_stories = get_top_stories(cache_data, client_colors, client_names)
    client_previews = {
        c["id"]: cache_data["cache"].get(c["id"], [])[:3]
        for c in config["clients"]
    }

    return render_template(
        "overview.html",
        agency=config["agency"],
        clients=config["clients"],
        top_stories=top_stories,
        client_previews=client_previews,
        client_names=client_names,
        client_colors=client_colors,
        last_refresh=cache_data.get("last_refresh"),
        status=cache_data.get("status", {}),
        week_label=current_week_label(),
    )


@app.route("/client/<client_id>")
def client_page(client_id):
    config = load_config()
    client = next((c for c in config["clients"] if c["id"] == client_id), None)
    if not client:
        return redirect(url_for("overview"))

    cache_data = load_cache()
    articles = cache_data["cache"].get(client_id, [])

    return render_template(
        "client.html",
        agency=config["agency"],
        clients=config["clients"],
        client=client,
        articles=articles,
        last_refresh=cache_data.get("last_refresh"),
    )


# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/refresh", methods=["POST"])
def refresh_all():
    from news_fetcher import NewsFetcher
    from ai_processor import AIProcessor

    config = load_config()
    news_api_key = os.getenv("NEWS_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if not news_api_key:
        return jsonify({"success": False, "error": "NEWS_API_KEY is not set in your .env file."}), 400
    if not anthropic_api_key:
        return jsonify({"success": False, "error": "ANTHROPIC_API_KEY is not set in your .env file."}), 400

    try:
        fetcher = NewsFetcher(news_api_key)
        processor = AIProcessor(anthropic_api_key, config.get("ai_model", "claude-haiku-4-5-20251001"))
        cache_data = load_cache()
        status = {}

        for client in config["clients"]:
            cid = client["id"]
            try:
                articles = fetcher.fetch_articles(client, config)
                processed = processor.process_articles(articles, client) if articles else []
                cache_data["cache"][cid] = processed
                status[cid] = {"fetched": len(articles), "processed": len(processed), "error": None}
            except Exception as e:
                status[cid] = {"fetched": 0, "processed": 0, "error": str(e)}

        now = datetime.now()
        cache_data["last_refresh"] = f"{now.day} {now.strftime('%B %Y, %I:%M %p')}"
        cache_data["status"] = status
        save_cache(cache_data)

        return jsonify({"success": True, "last_refresh": cache_data["last_refresh"], "status": status})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/refresh/<client_id>", methods=["POST"])
def refresh_client(client_id):
    from news_fetcher import NewsFetcher
    from ai_processor import AIProcessor

    config = load_config()
    client = next((c for c in config["clients"] if c["id"] == client_id), None)
    if not client:
        return jsonify({"success": False, "error": "Client not found."}), 404

    news_api_key = os.getenv("NEWS_API_KEY")
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

    if not news_api_key or not anthropic_api_key:
        return jsonify({"success": False, "error": "API keys not configured in .env file."}), 400

    try:
        fetcher = NewsFetcher(news_api_key)
        processor = AIProcessor(anthropic_api_key, config.get("ai_model", "claude-haiku-4-5-20251001"))

        articles = fetcher.fetch_articles(client, config)
        processed = processor.process_articles(articles, client) if articles else []

        cache_data = load_cache()
        cache_data["cache"][client_id] = processed
        cache_data.setdefault("status", {})[client_id] = {
            "fetched": len(articles),
            "processed": len(processed),
            "error": None,
        }
        now = datetime.now()
        cache_data["last_refresh"] = f"{now.day} {now.strftime('%B %Y, %I:%M %p')}"
        save_cache(cache_data)

        return jsonify({"success": True, "count": len(processed), "last_refresh": cache_data["last_refresh"]})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
