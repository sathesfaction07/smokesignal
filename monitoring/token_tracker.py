"""
monitoring/token_tracker.py — Active token usage tracking + budget guard.

Tracks every model invocation, calculates costs in real-time,
and enforces a daily budget limit to prevent cost overruns.

CloudWatch metrics published:
  - TokensUsedTotal (daily cumulative)
  - CostUSD (daily cumulative)
  - BudgetUtilizationPct (0-100)
"""

import logging
from datetime import date

import boto3

from config import AWS_REGION, CLOUDWATCH_NAMESPACE, PRICING

logger = logging.getLogger("vista.finops")

# Daily budget in USD — prevents runaway costs
DAILY_BUDGET_USD = float(__import__("os").environ.get("DAILY_BUDGET_USD", "1.00"))


class BudgetExceededError(Exception):
    """Raised when daily token budget is exceeded."""
    pass


class TokenTracker:
    """Tracks token usage, costs, and enforces budget limits."""

    def __init__(self):
        self.usage = []
        self._today = date.today()
        self._cw = boto3.client("cloudwatch", region_name=AWS_REGION)

    def _reset_if_new_day(self):
        """Auto-reset on calendar day change."""
        if date.today() != self._today:
            logger.info(f"New day detected, resetting tracker (previous: ${self.total_cost:.4f})")
            self.usage.clear()
            self._today = date.today()

    def record(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Record a model invocation and return its cost."""
        self._reset_if_new_day()

        pricing = PRICING.get(model_id, {"input": 0.001, "output": 0.005})
        cost = (input_tokens / 1000) * pricing["input"] + (output_tokens / 1000) * pricing["output"]

        self.usage.append({
            "model": model_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
        })

        logger.info(f"Token usage: {model_id.split('.')[-1]} | "
                    f"in={input_tokens} out={output_tokens} | "
                    f"cost=${cost:.5f} | daily_total=${self.total_cost:.4f}")

        return cost

    @property
    def total_cost(self) -> float:
        return sum(u["cost_usd"] for u in self.usage)

    @property
    def total_tokens(self) -> int:
        return sum(u["input_tokens"] + u["output_tokens"] for u in self.usage)

    @property
    def budget_remaining(self) -> float:
        return max(0.0, DAILY_BUDGET_USD - self.total_cost)

    @property
    def budget_utilization_pct(self) -> float:
        return min(100.0, (self.total_cost / DAILY_BUDGET_USD) * 100)

    def check_budget(self):
        """Raise BudgetExceededError if daily budget is exhausted."""
        if self.total_cost >= DAILY_BUDGET_USD:
            raise BudgetExceededError(
                f"Daily budget of ${DAILY_BUDGET_USD:.2f} exceeded "
                f"(spent: ${self.total_cost:.4f}). "
                f"Processing halted to prevent cost overrun."
            )

    def publish_metrics(self):
        """Publish token and cost metrics to CloudWatch."""
        try:
            self._cw.put_metric_data(
                Namespace=CLOUDWATCH_NAMESPACE,
                MetricData=[
                    {"MetricName": "TokensUsedTotal", "Value": self.total_tokens, "Unit": "Count"},
                    {"MetricName": "CostUSD", "Value": self.total_cost, "Unit": "None"},
                    {
                        "MetricName": "BudgetUtilizationPct",
                        "Value": self.budget_utilization_pct,
                        "Unit": "Percent",
                    },
                ],
            )
            logger.info(
                f"CloudWatch metrics published: tokens={self.total_tokens}, "
                f"cost=${self.total_cost:.4f}"
            )
        except Exception as e:
            logger.warning(f"CloudWatch publish failed (non-fatal): {e}")

    def summary(self) -> str:
        return (f"Tokens: {self.total_tokens:,} | Cost: ${self.total_cost:.4f} | "
                f"Budget: {self.budget_utilization_pct:.0f}% used")


# Singleton instance — shared across the application
tracker = TokenTracker()
