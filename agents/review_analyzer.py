"""
agents/review_analyzer.py — Multi-agent product review intelligence.

Pipeline (4 stages):
  1. Review Triage      — keyword scan across ALL sentiment categories (no LLM cost)
  2. Pattern Analysis   — Nova Micro finds recurring themes
  3. Quality Assessment — Claude Haiku 4.5 reasons about overall product health
  4. Action Decision    — rule-based decision + AWS actions

Sentiment categories analyzed:
  - Safety (hazards, injury, malfunction)
  - Quality (defective, broke quickly, poor materials)
  - Packaging (damaged in transit, poor packaging)
  - Misleading (not as described, fake, scam)
  - Disappointment (waste of money, returned, regret)
"""

import json
import logging
import os
import re

import boto3

from config import AWS_REGION, CLOUDWATCH_NAMESPACE, MODEL_ID_AGENT, MODEL_ID_TOOLS

logger = logging.getLogger("vista.analyzer")

# ── AWS clients ────────────────────────────────────────────────────────────────
SNS_TOPIC_ARN = os.environ.get(
    "SNS_TOPIC_ARN",
    "arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:bedrock-processor-alerts",
)
_sns = boto3.client("sns", region_name=AWS_REGION)
_cw  = boto3.client("cloudwatch", region_name=AWS_REGION)

# ── Sentiment keyword categories ──────────────────────────────────────────────
SENTIMENT_KEYWORDS = {
    "safety": [
        "never went off", "did not go off", "didn't go off", "no alarm",
        "failed to detect", "failed to alarm", "failed to sound",
        "does not detect", "doesn't detect", "not detecting",
        "sat silent", "sat there silently", "completely silent",
        "dangerous", "danger", "hazardous", "hazard", "life-threatening",
        "unsafe", "risk to life", "caught fire", "burned", "electric shock",
        "electrocuted", "injured", "injury", "harmful", "toxic",
        "choking hazard", "sharp edges", "overheated", "melted",
    ],
    "quality": [
        "broke after", "broke within", "broke in", "fell apart",
        "stopped working", "stop working", "quit working", "dead",
        "ceased to function", "stopped functioning", "no longer works",
        "defective", "faulty", "cheap quality", "cheap material",
        "poorly made", "flimsy", "fragile", "cracked", "scratched",
        "peeling", "rusted", "rusting", "worn out", "deteriorated",
        "doesn't last", "didn't last", "won't last", "poor build",
        "low quality", "terrible quality", "horrible quality",
    ],
    "packaging": [
        "arrived damaged", "arrived broken", "arrived cracked",
        "poor packaging", "bad packaging", "no packaging",
        "not packaged", "poorly packaged", "box was crushed",
        "box was torn", "box was open", "came open",
        "missing parts", "missing pieces", "incomplete",
        "wrong item", "wrong product", "wrong color", "wrong size",
        "dented", "leaked", "spilled", "smashed",
    ],
    "misleading": [
        "not as described", "not as shown", "not as pictured",
        "looks nothing like", "completely different", "false advertising",
        "misleading", "deceptive", "fake", "counterfeit", "knockoff",
        "knock-off", "not genuine", "not authentic", "not original",
        "smaller than", "bigger than", "different from",
        "scam", "fraud", "ripoff", "rip-off", "rip off",
    ],
    "disappointment": [
        "waste of money", "waste of time", "complete waste",
        "returning", "returned it", "sent it back", "refund",
        "want my money back", "regret", "disappointed", "disappointing",
        "not worth", "overpriced", "too expensive for",
        "would not recommend", "do not buy", "don't buy", "avoid",
        "terrible", "horrible", "awful", "worst", "useless",
        "threw it away", "binned it", "garbage", "trash", "junk",
    ],
}

CRITICAL_THRESHOLD = 0.40
HIGH_THRESHOLD     = 0.25
WARNING_THRESHOLD  = 0.15

_DECISION_RULES = {
    "CRITICAL": "FLAG_FOR_REMOVAL",
    "HIGH":     "FLAG_FOR_REVIEW",
    "MEDIUM":   "MONITOR",
    "LOW":      "APPROVE",
}

_ASSESSMENT_SYSTEM_PROMPT = """You are a product quality assessor for Amazon marketplace.
You evaluate customer review patterns to determine overall product health and risk level.

Consider ALL types of feedback:
POSITIVE signals: durability praise, value for money, works as described, fast delivery, exceeded expectations
NEGATIVE signals:
- Safety risks (injury, fire, electrical, choking hazards)
- Quality defects (broke quickly, cheap materials, stops working)
- Packaging issues (arrived damaged, missing parts)
- Misleading listings (not as described, counterfeit)
- Customer disappointment (waste of money, returns, regret)

Risk levels:
- CRITICAL: Product poses safety risk OR majority of reviews report serious defects
- HIGH: Significant quality/packaging issues OR misleading listing claims
- MEDIUM: Some complaints but mixed reviews, worth monitoring
- LOW: Generally positive, minor isolated complaints only

Output ONLY valid JSON:
{
  "level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "primary_concern": "safety" | "quality" | "packaging" | "misleading" | "disappointment" | "none",
  "positive_observations": "what customers liked (1-2 sentences)",
  "negative_observations": "what customers complained about (1-2 sentences, or 'none' if no complaints)",
  "reasoning": "2-3 sentence overall assessment balancing positives and negatives",
  "is_life_safety_risk": true | false
}
No prose, just JSON."""  # noqa: E501 -- prompt text; wrapping it changes what the model reads


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _call_nova_micro(user_message: str, max_tokens: int = 512) -> str:
    from monitoring.token_tracker import tracker
    tracker.check_budget()
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    response = client.converse(
        modelId=MODEL_ID_TOOLS,
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1},
    )
    usage = response.get("usage", {})
    tracker.record(MODEL_ID_TOOLS, usage.get("inputTokens", 0), usage.get("outputTokens", 0))
    return response["output"]["message"]["content"][0]["text"].strip()


def _call_haiku(system_prompt: str, user_message: str, max_tokens: int = 600) -> str:
    from monitoring.token_tracker import tracker
    tracker.check_budget()
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    response = client.converse(
        modelId=MODEL_ID_AGENT,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_message}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.1},
    )
    usage = response.get("usage", {})
    tracker.record(MODEL_ID_AGENT, usage.get("inputTokens", 0), usage.get("outputTokens", 0))
    return response["output"]["message"]["content"][0]["text"].strip()


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — Review Triage (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_scan(reviews: list) -> dict:
    total = len(reviews)
    category_counts = {cat: 0 for cat in SENTIMENT_KEYWORDS}
    negative_reviews = set()

    for idx, review in enumerate(reviews):
        text = (review.get("title", "") + " " + review.get("body", "")).lower()
        for category, keywords in SENTIMENT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                category_counts[category] += 1
                negative_reviews.add(idx)

    negative_count = len(negative_reviews)
    negative_pct = negative_count / total if total > 0 else 0.0

    if negative_pct >= CRITICAL_THRESHOLD:
        severity = "CRITICAL"
    elif negative_pct >= HIGH_THRESHOLD:
        severity = "HIGH"
    elif negative_pct >= WARNING_THRESHOLD:
        severity = "WARNING"
    else:
        severity = "LOW"

    top_category = max(category_counts, key=category_counts.get)
    top_count = category_counts[top_category]

    return {
        "category_breakdown": category_counts,
        "negative_review_count": negative_count,
        "negative_review_pct": round(negative_pct, 3),
        "severity": severity,
        "top_concern": top_category if top_count > 0 else "none",
        "top_concern_count": top_count,
    }


def run_triage_agent(review_data: dict) -> dict:
    logger.info("Stage 1 — Triage starting")
    reviews = review_data.get("reviews", [])
    total = len(reviews)
    avg_rating = sum(r.get("rating", 0) for r in reviews) / total if total > 0 else 0.0
    scan = _keyword_scan(reviews)

    pct_label = f"{scan['negative_review_pct'] * 100:.0f}%"
    cats_with_issues = [
        f"{cat}: {count}" for cat, count in scan["category_breakdown"].items() if count > 0
    ]
    cats_summary = " | ".join(cats_with_issues) if cats_with_issues else "none detected"

    reasoning = (
        f"{scan['negative_review_count']}/{total} reviews ({pct_label}) "
        f"contain negative signals. "
        f"Breakdown: {cats_summary}. "
        f"Top concern: {scan['top_concern']}."
    )

    print(f"\n[Review Triage] {total} reviews | {avg_rating:.1f}★ | "
          f"Negative: {scan['negative_review_count']} ({pct_label}) → {scan['severity']}")
    print(f"  Categories: {cats_summary}")

    return {
        "total_reviews": total,
        "avg_rating": round(avg_rating, 1),
        "negative_review_count": scan["negative_review_count"],
        "negative_review_pct": scan["negative_review_pct"],
        "category_breakdown": scan["category_breakdown"],
        "top_concern": scan["top_concern"],
        "severity": scan["severity"],
        "reasoning": reasoning,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Pattern Analysis (Nova Micro)
# ─────────────────────────────────────────────────────────────────────────────

def _fallback_patterns(reviews: list) -> list:
    pattern_counts = {}
    for review in reviews:
        text = (review.get("title", "") + " " + review.get("body", "")).lower()
        for category, keywords in SENTIMENT_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                label = {
                    "safety": "Product safety concerns reported",
                    "quality": "Quality/durability complaints",
                    "packaging": "Packaging or delivery issues",
                    "misleading": "Product not as described",
                    "disappointment": "General disappointment / returns",
                }[category]
                pattern_counts[label] = pattern_counts.get(label, 0) + 1

    return [f"{p} ({c} reviews)" for p, c in sorted(
        pattern_counts.items(), key=lambda x: x[1], reverse=True
    ) if c > 0]


def run_pattern_agent(review_data: dict) -> list:
    logger.info("Stage 2 — Pattern Analysis starting")
    print("\n[Pattern Analysis] Nova Micro identifying themes...")
    reviews = review_data.get("reviews", [])
    reviews_text = "\n---\n".join(
        f"Rating: {r.get('rating', '?')}★\nTitle: {r.get('title', '')}\nBody: {r.get('body', '')}"
        for r in reviews
    )

    try:
        prompt = (
            "Read these Amazon product reviews and identify the 3-5 most common "
            "recurring complaint themes. Look for ALL types of issues:\n"
            "- Safety problems (injury, hazard, malfunction)\n"
            "- Quality issues (broke quickly, cheap, defective)\n"
            "- Packaging problems (damaged in transit, missing parts)\n"
            "- Misleading listing (not as described, fake)\n"
            "- Disappointment (waste of money, returned)\n\n"
            "Group similar complaints together.\n\n"
            "Output ONLY valid JSON: "
            "{\"patterns\": [\"short theme description (N reviews)\", ...]}\n\n"
            f"Reviews:\n{reviews_text[:4000]}"
        )
        raw = _call_nova_micro(prompt, max_tokens=400)
        parsed = _extract_json(raw)
        patterns = parsed.get("patterns", [])
        if patterns:
            for i, p in enumerate(patterns, 1):
                print(f"  {i}. {p}")
            return patterns
    except Exception as e:
        print(f"  [Pattern] Nova Micro failed ({e}), using keyword fallback")

    patterns = _fallback_patterns(reviews)
    for i, p in enumerate(patterns, 1):
        print(f"  {i}. {p}")
    return patterns


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Quality & Safety Assessment (Claude Haiku 4.5)
# ─────────────────────────────────────────────────────────────────────────────

def _rule_based_assessment(triage: dict) -> dict:
    severity = triage.get("severity", "LOW")
    pct = triage.get("negative_review_pct", 0.0)
    top = triage.get("top_concern", "none")
    avg = triage.get("avg_rating", 0.0)
    total = triage.get("total_reviews", 0)
    pos_count = total - triage.get("negative_review_count", 0)

    positive_obs = (
        f"{pos_count}/{total} reviews are positive (avg {avg}★)."
        if total > 0
        else "No reviews available."
    )

    if severity == "CRITICAL":
        return {
            "level": "CRITICAL",
            "primary_concern": top,
            "positive_observations": positive_obs,
            "negative_observations": f"{pct * 100:.0f}% of reviews report serious {top} issues.",
            "reasoning": (
                f"{pct * 100:.0f}% of reviews contain negative signals. "
                f"Primary concern: {top}. {positive_obs}"
            ),
            "is_life_safety_risk": top == "safety",
        }
    elif severity == "HIGH":
        return {
            "level": "HIGH",
            "primary_concern": top,
            "positive_observations": positive_obs,
            "negative_observations": f"{pct * 100:.0f}% of reviews report {top} problems.",
            "reasoning": (
                f"{pct * 100:.0f}% of reviews report issues (primarily: {top}). {positive_obs}"
            ),
            "is_life_safety_risk": top == "safety",
        }
    elif severity == "WARNING":
        return {
            "level": "MEDIUM",
            "primary_concern": top,
            "positive_observations": positive_obs,
            "negative_observations": f"{pct * 100:.0f}% of reviews mention {top} concerns.",
            "reasoning": (
                f"Mixed reviews: {pct * 100:.0f}% mention concerns (top: {top}), "
                f"but {positive_obs}"
            ),
            "is_life_safety_risk": False,
        }
    return {
        "level": "LOW",
        "primary_concern": "none",
        "positive_observations": positive_obs,
        "negative_observations": "No significant complaints detected in review text.",
        "reasoning": (
            f"Generally positive product. {positive_obs} No recurring complaint patterns found."
        ),
        "is_life_safety_risk": False,
    }


def run_safety_agent(triage: dict, patterns: list) -> dict:
    logger.info("Stage 3 — Quality Assessment starting")
    print("\n[Quality Assessment] Claude Haiku 4.5 evaluating product health...")

    cats = triage.get("category_breakdown", {})
    cats_str = ", ".join(f"{k}: {v}" for k, v in cats.items() if v > 0) or "none"

    triage_summary = (
        f"Total reviews: {triage.get('total_reviews', 0)} | "
        f"Avg rating: {triage.get('avg_rating', 0.0):.1f}★ | "
        f"Negative reviews: {triage.get('negative_review_count', 0)} "
        f"({triage.get('negative_review_pct', 0) * 100:.0f}%) | "
        f"Issue categories: {cats_str} | "
        f"Top concern: {triage.get('top_concern', 'none')} | "
        f"Triage severity: {triage.get('severity', 'LOW')}"
    )
    patterns_json = json.dumps({"patterns": patterns})

    try:
        prompt = (
            f"Product review triage summary:\n{triage_summary}\n\n"
            f"Recurring complaint patterns:\n{patterns_json}\n\n"
            "Assess the overall product risk level considering safety, quality, "
            "packaging, listing accuracy, and customer satisfaction."
        )
        raw = _call_haiku(_ASSESSMENT_SYSTEM_PROMPT, prompt, max_tokens=400)
        result = _extract_json(raw)
        level = result.get("level", "LOW")
        concern = result.get("primary_concern", "none")
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(level, "⚪")
        print(f"  Risk Level: {icon} {level}")
        print(f"  Primary Concern: {concern}")
        print(f"  Reasoning: {result.get('reasoning', '')[:200]}")
        return {
            "level": level,
            "primary_concern": concern,
            "positive_observations": result.get("positive_observations", ""),
            "negative_observations": result.get("negative_observations", ""),
            "reasoning": result.get("reasoning", ""),
            "is_life_safety_risk": result.get("is_life_safety_risk", False),
        }
    except Exception as e:
        print(f"  [Assessment] Haiku failed ({e}), using rule-based fallback")
        result = _rule_based_assessment(triage)
        icon = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(
            result["level"], "⚪"
        )
        print(f"  Risk Level: {icon} {result['level']} (fallback)")
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 — Action Agent
# ─────────────────────────────────────────────────────────────────────────────

def _send_sns_alert(subject: str, message: str) -> str:
    try:
        _sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject[:100], Message=message)
        return f"SNS alert sent: \"{subject}\""
    except Exception as e:
        return f"SNS alert skipped (non-fatal): {e}"


def _publish_cw_metric(metric_name: str, value: float) -> str:
    try:
        _cw.put_metric_data(
            Namespace=CLOUDWATCH_NAMESPACE,
            MetricData=[{"MetricName": metric_name, "Value": value, "Unit": "Count"}],
        )
        return f"CloudWatch metric published: {metric_name}={value}"
    except Exception as e:
        return f"CloudWatch metric skipped (non-fatal): {e}"


def run_action_agent(product_info: dict, triage: dict, patterns: list, safety: dict) -> dict:
    logger.info("Stage 4 — Action Decision starting")
    print("\n[Action Agent] Taking actions...")

    asin        = product_info.get("asin", "UNKNOWN")
    name        = product_info.get("name", "Unknown Product")
    marketplace = product_info.get("marketplace", "amazon.com")
    level       = safety.get("level", "LOW")
    concern     = safety.get("primary_concern", "none")
    decision    = _DECISION_RULES.get(level, "MONITOR")

    # Internal AWS actions (logged but NOT shown to user)
    _internal_logs: list = []

    # User-friendly action summaries (shown on UI)
    user_actions: list = []

    if decision == "FLAG_FOR_REMOVAL":
        _internal_logs.append(_send_sns_alert(
            subject=f"CRITICAL Flag — {asin} — {concern.upper()} Issues",
            message=(
                f"Product flagged for removal: {name}\n"
                f"ASIN: {asin} | Marketplace: {marketplace}\n"
                f"Primary concern: {concern}\n"
                f"Reason: {safety.get('reasoning', '')}\n\n"
                f"Patterns:\n" + "\n".join(patterns)
            ),
        ))
        _internal_logs.append(_publish_cw_metric("ProductFlagCount", 1))
        _internal_logs.append(_publish_cw_metric("FlagForRemovalCount", 1))
        # Surface SNS status to user
        sns_result = _internal_logs[0] if _internal_logs else ""
        if "skipped" in sns_result:
            user_actions.append("⚠️ Email alert failed (AWS credentials not configured for SNS)")
        else:
            user_actions.append("Email alert sent to review team")
        user_actions.append(f"Primary issue: {concern}")

    elif decision == "FLAG_FOR_REVIEW":
        _internal_logs.append(_send_sns_alert(
            subject=f"HIGH Risk — {asin} — {concern.upper()} Issues",
            message=(
                f"Product flagged for review: {name}\n"
                f"ASIN: {asin} | Marketplace: {marketplace}\n"
                f"Primary concern: {concern}\n"
                f"Reason: {safety.get('reasoning', '')}\n\n"
                f"Patterns:\n" + "\n".join(patterns)
            ),
        ))
        _internal_logs.append(_publish_cw_metric("ProductFlagCount", 1))
        _internal_logs.append(_publish_cw_metric("FlaggedForReviewCount", 1))
        # Surface SNS status to user
        sns_result = _internal_logs[0] if _internal_logs else ""
        if "skipped" in sns_result:
            user_actions.append("⚠️ Email alert failed (AWS credentials not configured for SNS)")
        else:
            user_actions.append("Email alert sent to review team")
        user_actions.append(f"Needs attention — primary issue: {concern}")

    elif decision == "MONITOR":
        _internal_logs.append(_publish_cw_metric("MonitoredProductCount", 1))
        user_actions.append("Some concerns found but not critical")

    else:
        _internal_logs.append(_publish_cw_metric("ApprovedProductCount", 1))
        user_actions.append("No issues detected — product looks good")

    print(f"  Decision: {decision} (primary concern: {concern})")
    for a in _internal_logs:
        print(f"  [internal] {a}")
    for a in user_actions:
        print(f"  ✓ {a}")

    return {"decision": decision, "primary_concern": concern, "actions_taken": user_actions}


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def analyze_reviews_data(data: dict) -> dict:
    asin        = data.get("asin", "UNKNOWN")
    name        = data.get("product_name", "Unknown Product")
    marketplace = data.get("marketplace", "amazon.com")

    product_info = {"asin": asin, "name": name, "marketplace": marketplace}

    print(f"\n{'═' * 60}")
    print("  PRODUCT REVIEW INTELLIGENCE")
    print(f"  {name}")
    print(f"  ASIN: {asin} | {marketplace}")
    print(f"{'═' * 60}")

    triage   = run_triage_agent(data)
    patterns = run_pattern_agent(data)
    safety   = run_safety_agent(triage, patterns)
    actions  = run_action_agent(product_info, triage, patterns, safety)

    print(f"{'═' * 60}\n")

    return {
        "product": product_info,
        "review_stats": {
            "total":              triage["total_reviews"],
            "avg_rating":         triage["avg_rating"],
            "negative_count":     triage["negative_review_count"],
            "category_breakdown": triage["category_breakdown"],
        },
        "patterns":          patterns,
        "assessment":        safety,
        "decision":          actions["decision"],
        "primary_concern":   actions.get("primary_concern", "none"),
        "actions_taken":     actions["actions_taken"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Step-level API — used by streaming endpoint for per-agent progress events
# ─────────────────────────────────────────────────────────────────────────────

def run_triage(reviews: list) -> dict:
    return run_triage_agent({"reviews": reviews})


def run_pattern_analysis(reviews: list, triage: dict) -> list:
    return run_pattern_agent({"reviews": reviews})


def run_safety_assessment(reviews: list, patterns: list, triage: dict) -> dict:
    return run_safety_agent(triage, patterns)


def run_action_decision(product_info: dict, triage: dict, patterns: list, safety: dict) -> dict:
    return run_action_agent(product_info, triage, patterns, safety)
