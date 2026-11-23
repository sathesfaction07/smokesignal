from unittest.mock import patch

from botocore.exceptions import ClientError

from agents.review_analyzer import (
    _fallback_patterns,
    _rule_based_assessment,
    run_pattern_agent,
    run_safety_agent,
)


class TestPatternFallback:
    def test_fallback_groups_by_keyword_category(self, sample_reviews):
        patterns = _fallback_patterns(sample_reviews)
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        for pattern in patterns:
            assert "review" in pattern

    def test_fallback_sorts_by_frequency(self, sample_reviews):
        patterns = _fallback_patterns(sample_reviews)
        counts = []
        for p in patterns:
            if "(" in p and "review" in p:
                count_str = p.split("(")[1].split()[0]
                counts.append(int(count_str))
        if len(counts) > 1:
            assert counts == sorted(counts, reverse=True)

    def test_fallback_returns_empty_for_positive_reviews(self, positive_reviews):
        patterns = _fallback_patterns(positive_reviews)
        assert patterns == []

    def test_pattern_agent_uses_fallback_on_bedrock_failure(self, sample_reviews):
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova:
            mock_nova.side_effect = ClientError(
                {"Error": {"Code": "ServiceUnavailable", "Message": "Service down"}},
                "converse",
            )
            patterns = run_pattern_agent({"reviews": sample_reviews})
            assert isinstance(patterns, list)
            assert len(patterns) > 0

    def test_pattern_agent_uses_fallback_on_json_parse_error(self, sample_reviews):
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova:
            mock_nova.return_value = "This is not JSON at all"
            patterns = run_pattern_agent({"reviews": sample_reviews})
            assert isinstance(patterns, list)
            assert len(patterns) > 0

    def test_pattern_agent_uses_fallback_on_malformed_json(self, sample_reviews):
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova:
            mock_nova.return_value = '{"wrong_key": ["item"]}'
            patterns = run_pattern_agent({"reviews": sample_reviews})
            assert isinstance(patterns, list)

    def test_pattern_agent_uses_fallback_on_timeout(self, sample_reviews):
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova:
            mock_nova.side_effect = Exception("Connection timeout")
            patterns = run_pattern_agent({"reviews": sample_reviews})
            assert isinstance(patterns, list)
            assert len(patterns) > 0


class TestSafetyFallback:
    def test_fallback_returns_critical_for_high_percentage(self):
        triage = {
            "severity": "CRITICAL",
            "negative_review_pct": 0.6,
            "top_concern": "safety",
            "avg_rating": 1.5,
            "total_reviews": 10,
            "negative_review_count": 6,
        }
        result = _rule_based_assessment(triage)
        assert result["level"] == "CRITICAL"
        assert result["primary_concern"] == "safety"
        assert result["is_life_safety_risk"] is True

    def test_fallback_returns_high_for_moderate_percentage(self):
        triage = {
            "severity": "HIGH",
            "negative_review_pct": 0.3,
            "top_concern": "quality",
            "avg_rating": 2.5,
            "total_reviews": 10,
            "negative_review_count": 3,
        }
        result = _rule_based_assessment(triage)
        assert result["level"] == "HIGH"
        assert result["primary_concern"] == "quality"

    def test_fallback_returns_medium_for_warning_severity(self):
        triage = {
            "severity": "WARNING",
            "negative_review_pct": 0.2,
            "top_concern": "packaging",
            "avg_rating": 3.5,
            "total_reviews": 10,
            "negative_review_count": 2,
        }
        result = _rule_based_assessment(triage)
        assert result["level"] == "MEDIUM"

    def test_fallback_returns_low_for_minimal_issues(self):
        triage = {
            "severity": "LOW",
            "negative_review_pct": 0.05,
            "top_concern": "none",
            "avg_rating": 4.5,
            "total_reviews": 20,
            "negative_review_count": 1,
        }
        result = _rule_based_assessment(triage)
        assert result["level"] == "LOW"
        assert result["primary_concern"] == "none"
        assert result["is_life_safety_risk"] is False

    def test_fallback_includes_all_required_fields(self):
        triage = {
            "severity": "HIGH",
            "negative_review_pct": 0.3,
            "top_concern": "quality",
            "avg_rating": 2.5,
            "total_reviews": 10,
            "negative_review_count": 3,
        }
        result = _rule_based_assessment(triage)
        assert "level" in result
        assert "primary_concern" in result
        assert "positive_observations" in result
        assert "negative_observations" in result
        assert "reasoning" in result
        assert "is_life_safety_risk" in result

    def test_safety_agent_uses_fallback_on_bedrock_failure(
        self, sample_triage_result, sample_patterns
    ):
        with patch("agents.review_analyzer._call_haiku") as mock_haiku:
            mock_haiku.side_effect = ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
                "converse",
            )
            result = run_safety_agent(sample_triage_result, sample_patterns)
            assert result["level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            assert "primary_concern" in result

    def test_safety_agent_uses_fallback_on_json_error(
        self, sample_triage_result, sample_patterns
    ):
        with patch("agents.review_analyzer._call_haiku") as mock_haiku:
            mock_haiku.return_value = "Not valid JSON output"
            result = run_safety_agent(sample_triage_result, sample_patterns)
            assert result["level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    def test_safety_agent_uses_fallback_on_invalid_response(
        self, sample_triage_result, sample_patterns
    ):
        with patch("agents.review_analyzer._call_haiku") as mock_haiku:
            mock_haiku.return_value = '{"wrong_structure": true}'
            result = run_safety_agent(sample_triage_result, sample_patterns)
            assert "level" in result


class TestFallbackOverAIComparison:
    def test_pattern_fallback_produces_usable_output(self, sample_reviews):
        patterns = _fallback_patterns(sample_reviews)
        assert len(patterns) > 0
        for p in patterns:
            assert isinstance(p, str)
            assert len(p) > 0

    def test_safety_fallback_is_conservative(self):
        high_risk = {
            "severity": "CRITICAL",
            "negative_review_pct": 0.5,
            "top_concern": "safety",
            "avg_rating": 1.8,
            "total_reviews": 20,
            "negative_review_count": 10,
        }
        result = _rule_based_assessment(high_risk)
        assert result["level"] in ["CRITICAL", "HIGH"]

    def test_fallback_reasoning_includes_context(self):
        triage = {
            "severity": "HIGH",
            "negative_review_pct": 0.35,
            "top_concern": "quality",
            "avg_rating": 2.5,
            "total_reviews": 20,
            "negative_review_count": 7,
        }
        result = _rule_based_assessment(triage)
        reasoning = result["reasoning"]
        assert isinstance(reasoning, str)
        assert len(reasoning) > 20


class TestBudgetExceededFallsBackGracefully:
    def test_pattern_agent_falls_back_on_budget_exceeded(self, sample_reviews):
        """Budget exhaustion triggers fallback, not error propagation.

        This test verifies cost control: after budget is hit, no further paid API
        calls occur, and the system degrades to deterministic keyword-based patterns.
        """
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova:
            from monitoring.token_tracker import BudgetExceededError

            mock_nova.side_effect = BudgetExceededError("Budget exceeded")
            # Should NOT raise — should fall back gracefully
            result = run_pattern_agent({"reviews": sample_reviews})

            # Verify fallback logic ran
            assert isinstance(result, list)
            assert len(result) > 0  # Deterministic fallback produces patterns

            # Verify no retry — only one attempted call proves budget guard worked
            assert mock_nova.call_count == 1

    def test_safety_agent_falls_back_on_budget_exceeded(
        self, sample_triage_result, sample_patterns
    ):
        """Budget exhaustion triggers rule-based assessment, not error propagation.

        This test verifies cost control: after budget is hit, no further paid API
        calls occur, and the system degrades to conservative rule-based risk scoring.
        """
        with patch("agents.review_analyzer._call_haiku") as mock_haiku:
            from monitoring.token_tracker import BudgetExceededError

            mock_haiku.side_effect = BudgetExceededError("Budget exceeded")
            # Should NOT raise — should fall back gracefully
            result = run_safety_agent(sample_triage_result, sample_patterns)

            # Verify fallback logic ran
            assert "level" in result
            assert result["level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            assert "primary_concern" in result
            assert "reasoning" in result

            # Verify no retry — only one attempted call proves budget guard worked
            assert mock_haiku.call_count == 1
