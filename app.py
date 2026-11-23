"""
app.py — Flask web server for Vista.

Endpoints:
  GET  /           — Serves the frontend (static/index.html)
  POST /analyze    — SSE streaming endpoint for real-time analysis
"""

import json
import os
import re as _re

from flask import Flask, Response, request, send_from_directory

from agents.review_analyzer import (
    run_action_decision,
    run_pattern_analysis,
    run_safety_assessment,
    run_triage,
)
from agents.review_fetcher import fetch_reviews_streaming
from monitoring.daily_cache import get_cached_result, save_result
from monitoring.logger import setup_logging
from monitoring.token_tracker import BudgetExceededError

# Initialize structured logging
setup_logging("INFO")


# Amazon ASIN pattern: 10 alphanumeric characters starting with B0 or a digit
_ASIN_PATTERN = _re.compile(r'\b([A-Z0-9]{10})\b')
_URL_ASIN_PATTERN = _re.compile(r'/(?:dp|product-reviews|gp/product)/([A-Z0-9]{10})')


def _parse_asin_input(raw: str) -> list[str]:
    """
    Flexible ASIN parser. Accepts:
      - Single ASIN: B0GXYH3B95
      - Comma-separated: B0GXYH3B95, B07XJ8C8F7
      - Newline/space-separated: B0GXYH3B95\nB07XJ8C8F7
      - Full URLs: https://www.amazon.com/dp/B0GXYH3B95#customer-reviews
      - Mixed: B0GXYH3B95, https://amazon.com/dp/B07XJ8C8F7
    Returns deduplicated list of valid 10-char ASINs.
    """
    asins = []
    # Split on commas, newlines, spaces, tabs
    tokens = _re.split(r'[,\s]+', raw.strip())
    for token in tokens:
        if not token:
            continue
        # Try extracting ASIN from URL first
        url_match = _URL_ASIN_PATTERN.search(token)
        if url_match:
            asins.append(url_match.group(1))
            continue
        # Try matching bare ASIN (10 alphanumeric chars)
        asin_match = _ASIN_PATTERN.search(token.upper())
        if asin_match:
            asins.append(asin_match.group(1))
    # Deduplicate while preserving order
    seen = set()
    result = []
    for a in asins:
        if a not in seen:
            seen.add(a)
            result.append(a)
    return result


app = Flask(__name__, static_folder="static")


def _format_result(raw: dict) -> dict:
    """Format analyzer output for the frontend."""
    stats = raw.get("review_stats", {})
    safety = raw.get("assessment", raw.get("safety_assessment", {}))
    product = raw.get("product", {})

    return {
        "asin":               product.get("asin", "UNKNOWN"),
        "product_name":       product.get("name", "Unknown Product"),
        "marketplace_domain": product.get("marketplace", "amazon.com"),
        "total_reviews":      stats.get("total", 0),
        "avg_rating":         stats.get("avg_rating", 0.0),
        "negative_count":     stats.get("negative_count", 0),
        "category_breakdown": stats.get("category_breakdown", {}),
        "patterns":           raw.get("patterns", []),
        "risk_level":         safety.get("level", "LOW"),
        "primary_concern":    safety.get("primary_concern", "none"),
        "positive_observations": safety.get("positive_observations", ""),
        "negative_observations": safety.get("negative_observations", ""),
        "reasoning":          safety.get("reasoning", ""),
        "is_life_safety_risk": safety.get("is_life_safety_risk", False),
        "decision":           raw.get("decision", "APPROVE"),
        "actions_taken":      raw.get("actions_taken", []),
    }


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    """SSE streaming endpoint. Processes ASINs one by one with progress events."""
    data = request.get_json()
    raw_input = data.get("asins", "")
    asins = _parse_asin_input(raw_input)
    marketplace = data.get("marketplace", "US")

    if not asins:
        return Response("No ASINs provided", status=400)

    def generate():
        total = len(asins)
        yield f"event: start\ndata: {json.dumps({'total': total})}\n\n"

        # Separate cached vs uncached ASINs
        cached_results = {}
        uncached_asins = []
        for asin in asins:
            cached = get_cached_result(asin, marketplace)
            if cached:
                cached_results[asin] = cached
            else:
                uncached_asins.append(asin)

        # Serve cached results immediately
        for i, asin in enumerate(asins):
            if asin in cached_results:
                payload = json.dumps(
                    {
                        "current": i + 1,
                        "total": total,
                        "asin": asin,
                        "status": "cached",
                        "agent": None,
                    }
                )
                yield f"event: progress\ndata: {payload}\n\n"
                yield f"event: result\ndata: {json.dumps(cached_results[asin])}\n\n"

        # Fetch uncached ASINs (multi-tab parallel)
        if uncached_asins:
            fetcher = fetch_reviews_streaming(uncached_asins, marketplace)
            for fetch_result in fetcher:
                asin = fetch_result["asin"]
                i = asins.index(asin) + 1

                # Progress: fetching
                payload = json.dumps(
                    {
                        "current": i,
                        "total": total,
                        "asin": asin,
                        "status": "fetching",
                        "agent": None,
                    }
                )
                yield f"event: progress\ndata: {payload}\n\n"

                if not fetch_result["success"]:
                    payload = json.dumps({'asin': asin, 'error': fetch_result['error']})
                    yield f"event: error\ndata: {payload}\n\n"
                    continue

                review_data = fetch_result["data"]
                reviews = review_data.get("reviews", [])

                if not reviews:
                    payload = json.dumps(
                        {"asin": asin, "error": "No reviews found on product page"}
                    )
                    yield f"event: error\ndata: {payload}\n\n"
                    continue

                product_info = {
                    "asin": asin,
                    "name": review_data.get("product_name", "Unknown"),
                    "marketplace": review_data.get("marketplace", "amazon.com"),
                }

                try:
                    # Stage 1 — Triage
                    payload = json.dumps(
                        {
                            "current": i,
                            "total": total,
                            "asin": asin,
                            "status": "triage",
                            "agent": "\U0001f4cb Triage Agent: Scanning for negative signals...",
                        }
                    )
                    yield f"event: progress\ndata: {payload}\n\n"
                    triage = run_triage(reviews)

                    # Stage 2 — Patterns
                    payload = json.dumps(
                        {
                            "current": i,
                            "total": total,
                            "asin": asin,
                            "status": "patterns",
                            "agent": "\U0001f52c Pattern Agent (Nova Micro): Identifying themes...",
                        }
                    )
                    yield f"event: progress\ndata: {payload}\n\n"
                    patterns = run_pattern_analysis(reviews, triage)

                    # Stage 3 — Quality & Safety Assessment
                    payload = json.dumps(
                        {
                            "current": i,
                            "total": total,
                            "asin": asin,
                            "status": "safety",
                            "agent": (
                                "\U0001f6e1\ufe0f Quality Agent (Claude Haiku 4.5): "
                                "Assessing product health..."
                            ),
                        }
                    )
                    yield f"event: progress\ndata: {payload}\n\n"
                    safety = run_safety_assessment(reviews, patterns, triage)

                    # Stage 4 — Action
                    payload = json.dumps(
                        {
                            "current": i,
                            "total": total,
                            "asin": asin,
                            "status": "action",
                            "agent": "\u26a1 Action Agent: Deciding next steps...",
                        }
                    )
                    yield f"event: progress\ndata: {payload}\n\n"
                    actions = run_action_decision(product_info, triage, patterns, safety)

                    # Build result
                    result = _format_result({
                        "product": product_info,
                        "review_stats": {
                            "total": triage["total_reviews"],
                            "avg_rating": triage["avg_rating"],
                            "negative_count": triage["negative_review_count"],
                            "category_breakdown": triage.get("category_breakdown", {}),
                        },
                        "patterns": patterns,
                        "assessment": safety,
                        "decision": actions["decision"],
                        "actions_taken": actions["actions_taken"],
                    })

                    # Cache and emit
                    save_result(asin, marketplace, result)
                    yield f"event: result\ndata: {json.dumps(result)}\n\n"

                except BudgetExceededError as e:
                    yield f"event: error\ndata: {json.dumps({'asin': asin, 'error': str(e)})}\n\n"
                    continue

        yield f"event: done\ndata: {json.dumps({'total': total})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n━━━ Vista ━━━")
    print(f"    http://localhost:{port}")
    print("    Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=port, debug=False)
