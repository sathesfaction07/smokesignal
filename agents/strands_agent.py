"""
agents/strands_agent.py — Bedrock AgentCore via Strands SDK.

Demonstrates proper AgentCore patterns:
  - Agent with system prompt and model configuration
  - Tool definitions with @tool decorator
  - Structured output parsing
  - Conversation lifecycle management

This module wraps the Assessment (Stage 3) in a proper AgentCore agent,
showing how agents orchestrate tool use for complex reasoning.
"""

import json
import logging
import re

from strands import Agent
from strands.models.bedrock import BedrockModel

from config import AWS_REGION, MODEL_ID_AGENT

logger = logging.getLogger("vista.agentcore")

# ─── Model Configuration ──────────────────────────────────────────────────────
# BedrockModel wraps the Converse API with AgentCore lifecycle management
_bedrock_model = BedrockModel(
    model_id=MODEL_ID_AGENT,
    region_name=AWS_REGION,
    max_tokens=512,
    temperature=0.1,
)

# ─── System Prompt ────────────────────────────────────────────────────────────
_ASSESSMENT_SYSTEM_PROMPT = """You are a product quality assessment agent for Amazon marketplace.

Your job: Evaluate customer review data and determine overall product risk.

You have access to the following tools:
- classify_risk_level: Determines risk level from negative review percentage
- check_safety_keywords: Checks if safety-critical keywords are present

Process:
1. Use classify_risk_level with the negative percentage
2. Use check_safety_keywords with the top concern category
3. Synthesize both results into a final assessment

Always provide your final answer as JSON:
{
  "level": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW",
  "primary_concern": "safety" | "quality" | "packaging" | "misleading" | "disappointment" | "none",
  "reasoning": "2-3 sentence explanation",
  "is_life_safety_risk": true | false
}"""


# ─── Tool Definitions ─────────────────────────────────────────────────────────
# Tools give the agent structured capabilities beyond free-form text generation.
# AgentCore orchestrates when to call which tool based on the system prompt.

def classify_risk_level(negative_pct: float, total_reviews: int) -> dict:
    """Classify product risk level based on negative review percentage.

    Args:
        negative_pct: Percentage of reviews with negative signals (0.0 to 1.0)
        total_reviews: Total number of reviews analyzed

    Returns:
        Risk classification with confidence score
    """
    if negative_pct >= 0.40:
        level = "CRITICAL"
        confidence = min(0.95, 0.7 + (negative_pct - 0.40))
    elif negative_pct >= 0.25:
        level = "HIGH"
        confidence = min(0.90, 0.6 + (negative_pct - 0.25) * 2)
    elif negative_pct >= 0.15:
        level = "MEDIUM"
        confidence = min(0.80, 0.5 + (negative_pct - 0.15) * 2)
    else:
        level = "LOW"
        confidence = min(0.95, 0.8 + (0.15 - negative_pct))

    # Lower confidence if too few reviews
    if total_reviews < 5:
        confidence *= 0.7

    return {
        "level": level,
        "confidence": round(confidence, 2),
        "sample_size": "sufficient" if total_reviews >= 10 else "limited",
    }


def check_safety_keywords(top_concern: str, category_counts: dict) -> dict:
    """Check if the product has life-safety implications.

    Args:
        top_concern: The highest-frequency concern category
        category_counts: Dict of category -> count (e.g. {'safety': 3, 'quality': 5})

    Returns:
        Safety assessment result
    """
    safety_count = category_counts.get("safety", 0)
    total_negative = sum(category_counts.values())
    safety_pct = safety_count / total_negative if total_negative > 0 else 0.0

    return {
        "is_life_safety_risk": top_concern == "safety" or safety_pct > 0.3,
        "safety_mention_count": safety_count,
        "safety_percentage": round(safety_pct * 100, 1),
        "recommendation": (
            "URGENT: Safety-critical product requires immediate review"
            if safety_pct > 0.3
            else "No immediate safety concern identified"
        ),
    }


# ─── Agent Instance ───────────────────────────────────────────────────────────
# The Agent combines model + system prompt + tools into an orchestration unit.
# AgentCore handles the tool-use loop automatically.

assessment_agent = Agent(
    model=_bedrock_model,
    system_prompt=_ASSESSMENT_SYSTEM_PROMPT,
    tools=[classify_risk_level, check_safety_keywords],
)


# ─── Public API ───────────────────────────────────────────────────────────────

def run_agentcore_assessment(triage: dict, patterns: list) -> dict:
    """
    Run the Assessment stage using Bedrock AgentCore (Strands SDK).

    This is the AgentCore equivalent of run_safety_agent() in review_analyzer.py.
    The agent autonomously decides which tools to call and in what order.

    Args:
        triage: Output from Stage 1 (keyword scan results)
        patterns: Output from Stage 2 (recurring themes)

    Returns:
        Assessment dict with level, primary_concern, reasoning, is_life_safety_risk
    """
    logger.info("AgentCore assessment starting...")

    # Build the user message with all context
    user_message = (
        f"Assess this product's risk level.\n\n"
        f"Triage data:\n"
        f"- Total reviews: {triage.get('total_reviews', 0)}\n"
        f"- Average rating: {triage.get('avg_rating', 0)}★\n"
        f"- Negative reviews: {triage.get('negative_review_count', 0)} "
        f"({triage.get('negative_review_pct', 0) * 100:.0f}%)\n"
        f"- Top concern: {triage.get('top_concern', 'none')}\n"
        f"- Category breakdown: {json.dumps(triage.get('category_breakdown', {}))}\n\n"
        f"Recurring complaint patterns:\n"
        + "\n".join(f"- {p}" for p in patterns)
        + "\n\nUse classify_risk_level and check_safety_keywords tools, "
        "then provide your final JSON assessment."
    )

    try:
        # Invoke the agent — AgentCore handles the tool-use loop
        result = assessment_agent(user_message)
        response_text = str(result)

        # Parse the JSON response
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            logger.info(f"AgentCore assessment: {parsed.get('level', 'UNKNOWN')}")
            return {
                "level": parsed.get("level", "LOW"),
                "primary_concern": parsed.get("primary_concern", "none"),
                "reasoning": parsed.get("reasoning", ""),
                "is_life_safety_risk": parsed.get("is_life_safety_risk", False),
            }
    except Exception as e:
        logger.warning(f"AgentCore assessment failed: {e}, falling back to rule-based")

    # Fallback: rule-based (same as review_analyzer.py)
    from agents.review_analyzer import _rule_based_assessment
    return _rule_based_assessment(triage)
