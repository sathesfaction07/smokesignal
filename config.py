"""
config.py — Central configuration for Vista.

All settings can be overridden via environment variables.
"""

import os

# ── AWS Region ─────────────────────────────────────────────────────────────────
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# ── Bedrock Model IDs ──────────────────────────────────────────────────────────
# Nova Micro: cheap, fast — used for pattern detection ($0.035 / 1M input tokens)
MODEL_ID_TOOLS = "amazon.nova-micro-v1:0"

# Claude Haiku 4.5: smart reasoning — used for risk assessment ($1 / 1M input tokens)
# Cross-region inference profile required for invocation:
MODEL_ID_AGENT = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# ── CloudWatch ─────────────────────────────────────────────────────────────────
CLOUDWATCH_NAMESPACE = "BedrockReviewIntel"

# ── Token Pricing (per 1K tokens) ─────────────────────────────────────────────
PRICING = {
    MODEL_ID_TOOLS: {"input": 0.000035, "output": 0.00014},
    MODEL_ID_AGENT: {"input": 0.001, "output": 0.005},
}

# ── Supported Amazon Marketplaces ─────────────────────────────────────────────
# All 25 Amazon retail marketplaces in operation (amazon.cn excluded — Amazon
# closed its China domestic marketplace; the domain no longer serves search).
MARKETPLACES = {
    # Americas
    "US": "www.amazon.com",
    "CA": "www.amazon.ca",
    "MX": "www.amazon.com.mx",
    "BR": "www.amazon.com.br",
    "CO": "www.amazon.com.co",
    # Europe
    "UK": "www.amazon.co.uk",
    "DE": "www.amazon.de",
    "FR": "www.amazon.fr",
    "IT": "www.amazon.it",
    "ES": "www.amazon.es",
    "NL": "www.amazon.nl",
    "SE": "www.amazon.se",
    "PL": "www.amazon.pl",
    "BE": "www.amazon.com.be",
    "IE": "www.amazon.ie",
    "TR": "www.amazon.com.tr",
    # Middle East & Africa
    "AE": "www.amazon.ae",
    "SA": "www.amazon.sa",
    "EG": "www.amazon.eg",
    "ZA": "www.amazon.co.za",
    "NG": "www.amazon.com.ng",
    # Asia-Pacific
    "IN": "www.amazon.in",
    "JP": "www.amazon.co.jp",
    "SG": "www.amazon.sg",
    "AU": "www.amazon.com.au",
}
