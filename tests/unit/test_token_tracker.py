from datetime import date
from unittest.mock import patch

import pytest

from config import MODEL_ID_AGENT, MODEL_ID_TOOLS, PRICING
from monitoring.token_tracker import (
    DAILY_BUDGET_USD,
    BudgetExceededError,
    TokenTracker,
)


class TestTokenAccounting:
    def test_records_single_invocation(self):
        tracker = TokenTracker()
        cost = tracker.record(MODEL_ID_TOOLS, 100, 50)
        assert cost > 0
        assert len(tracker.usage) == 1
        assert tracker.usage[0]["model"] == MODEL_ID_TOOLS
        assert tracker.usage[0]["input_tokens"] == 100
        assert tracker.usage[0]["output_tokens"] == 50

    def test_accumulates_multiple_invocations(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        tracker.record(MODEL_ID_AGENT, 200, 100)
        assert len(tracker.usage) == 2
        assert tracker.total_tokens == 450

    def test_calculates_cost_correctly_for_nova_micro(self):
        tracker = TokenTracker()
        cost = tracker.record(MODEL_ID_TOOLS, 1000, 1000)
        expected = (1000 / 1000) * PRICING[MODEL_ID_TOOLS]["input"] + (
            1000 / 1000
        ) * PRICING[MODEL_ID_TOOLS]["output"]
        assert abs(cost - expected) < 0.000001

    def test_calculates_cost_correctly_for_haiku(self):
        tracker = TokenTracker()
        cost = tracker.record(MODEL_ID_AGENT, 1000, 1000)
        expected = (1000 / 1000) * PRICING[MODEL_ID_AGENT]["input"] + (
            1000 / 1000
        ) * PRICING[MODEL_ID_AGENT]["output"]
        assert abs(cost - expected) < 0.000001

    def test_total_cost_sums_all_invocations(self):
        tracker = TokenTracker()
        cost1 = tracker.record(MODEL_ID_TOOLS, 100, 50)
        cost2 = tracker.record(MODEL_ID_AGENT, 200, 100)
        assert abs(tracker.total_cost - (cost1 + cost2)) < 0.000001

    def test_total_tokens_sums_input_and_output(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        tracker.record(MODEL_ID_AGENT, 200, 100)
        assert tracker.total_tokens == 450


class TestBudgetEnforcement:
    def test_check_budget_passes_when_below_limit(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        tracker.check_budget()

    def test_check_budget_raises_when_exceeded(self):
        tracker = TokenTracker()
        large_tokens = int(DAILY_BUDGET_USD * 1000000)
        tracker.record(MODEL_ID_AGENT, large_tokens, large_tokens)
        with pytest.raises(BudgetExceededError):
            tracker.check_budget()

    def test_check_budget_raises_exactly_at_limit(self):
        tracker = TokenTracker()
        input_tokens = int((DAILY_BUDGET_USD / PRICING[MODEL_ID_AGENT]["input"]) * 1000)
        tracker.record(MODEL_ID_AGENT, input_tokens, 0)
        with pytest.raises(BudgetExceededError):
            tracker.check_budget()

    def test_budget_remaining_calculates_correctly(self):
        tracker = TokenTracker()
        cost = tracker.record(MODEL_ID_TOOLS, 100, 50)
        assert abs(tracker.budget_remaining - (DAILY_BUDGET_USD - cost)) < 0.000001

    def test_budget_remaining_never_negative(self):
        tracker = TokenTracker()
        large_tokens = int(DAILY_BUDGET_USD * 1000000)
        tracker.record(MODEL_ID_AGENT, large_tokens, large_tokens)
        assert tracker.budget_remaining == 0.0

    def test_budget_utilization_percentage(self):
        tracker = TokenTracker()
        tokens = int((DAILY_BUDGET_USD * 0.5 / PRICING[MODEL_ID_AGENT]["input"]) * 1000)
        tracker.record(MODEL_ID_AGENT, tokens, 0)
        assert 45 <= tracker.budget_utilization_pct <= 55

    def test_budget_utilization_capped_at_100(self):
        tracker = TokenTracker()
        large_tokens = int(DAILY_BUDGET_USD * 1000000)
        tracker.record(MODEL_ID_AGENT, large_tokens, large_tokens)
        assert tracker.budget_utilization_pct == 100.0


class TestDayRollover:
    def test_resets_on_new_day(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        assert len(tracker.usage) == 1
        with patch("monitoring.token_tracker.date") as mock_date:
            mock_date.today.return_value = date(2025, 1, 2)
            tracker._today = date(2025, 1, 1)
            tracker._reset_if_new_day()
            assert len(tracker.usage) == 0

    def test_does_not_reset_on_same_day(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        tracker._reset_if_new_day()
        assert len(tracker.usage) == 1

    def test_record_checks_day_rollover(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        assert len(tracker.usage) == 1
        with patch.object(tracker, "_reset_if_new_day") as mock_reset:
            tracker.record(MODEL_ID_AGENT, 200, 100)
            assert mock_reset.called


class TestCloudWatchMetrics:
    def test_publishes_all_metrics(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        with patch.object(tracker, "_cw") as mock_cw:
            tracker.publish_metrics()
            assert mock_cw.put_metric_data.called
            call_args = mock_cw.put_metric_data.call_args
            metric_data = call_args[1]["MetricData"]
            metric_names = {m["MetricName"] for m in metric_data}
            assert "TokensUsedTotal" in metric_names
            assert "CostUSD" in metric_names
            assert "BudgetUtilizationPct" in metric_names

    def test_publish_handles_cloudwatch_failure(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        with patch.object(tracker, "_cw") as mock_cw:
            mock_cw.put_metric_data.side_effect = Exception("CloudWatch error")
            tracker.publish_metrics()


class TestSummary:
    def test_summary_includes_key_metrics(self):
        tracker = TokenTracker()
        tracker.record(MODEL_ID_TOOLS, 100, 50)
        summary = tracker.summary()
        assert "Tokens:" in summary
        assert "Cost:" in summary
        assert "Budget:" in summary
        assert str(tracker.total_tokens) in summary


class TestUnknownModelPricing:
    def test_uses_default_pricing_for_unknown_model(self):
        tracker = TokenTracker()
        cost = tracker.record("unknown.model.id", 1000, 1000)
        default_pricing = {"input": 0.001, "output": 0.005}
        expected = (1000 / 1000) * default_pricing["input"] + (
            1000 / 1000
        ) * default_pricing["output"]
        assert abs(cost - expected) < 0.000001
