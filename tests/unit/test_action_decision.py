from unittest.mock import patch

from agents.review_analyzer import _DECISION_RULES, run_action_agent


class TestActionDecisionRules:
    def test_critical_level_flags_for_removal(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {
            "level": "CRITICAL",
            "primary_concern": "safety",
            "positive_observations": "Some positive reviews",
            "negative_observations": "Life-threatening failures",
            "reasoning": "Multiple safety failures reported",
            "is_life_safety_risk": True,
        }
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == "FLAG_FOR_REMOVAL"
            assert result["primary_concern"] == "safety"
            assert len(result["actions_taken"]) > 0

    def test_high_level_flags_for_review(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {
            "level": "HIGH",
            "primary_concern": "quality",
            "positive_observations": "Some positive feedback",
            "negative_observations": "Significant quality issues",
            "reasoning": "Multiple defect reports",
            "is_life_safety_risk": False,
        }
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == "FLAG_FOR_REVIEW"
            assert result["primary_concern"] == "quality"

    def test_medium_level_monitors(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {
            "level": "MEDIUM",
            "primary_concern": "packaging",
            "positive_observations": "Generally positive",
            "negative_observations": "Some packaging complaints",
            "reasoning": "Mixed reviews",
            "is_life_safety_risk": False,
        }
        with patch("agents.review_analyzer._cw") as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == "MONITOR"

    def test_low_level_approves(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {
            "level": "LOW",
            "primary_concern": "none",
            "positive_observations": "Excellent reviews",
            "negative_observations": "No significant complaints",
            "reasoning": "Product looks good",
            "is_life_safety_risk": False,
        }
        with patch("agents.review_analyzer._cw") as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == "APPROVE"


class TestThresholdBoundaries:
    def test_exactly_critical_level(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "CRITICAL", "primary_concern": "safety", "reasoning": "Test"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == _DECISION_RULES["CRITICAL"]

    def test_exactly_high_level(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "HIGH", "primary_concern": "quality", "reasoning": "Test"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == _DECISION_RULES["HIGH"]

    def test_exactly_medium_level(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "MEDIUM", "primary_concern": "packaging", "reasoning": "Test"}
        with patch("agents.review_analyzer._cw") as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == _DECISION_RULES["MEDIUM"]

    def test_exactly_low_level(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "LOW", "primary_concern": "none", "reasoning": "Test"}
        with patch("agents.review_analyzer._cw") as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            assert result["decision"] == _DECISION_RULES["LOW"]


class TestSNSIntegration:
    def test_critical_sends_sns_alert(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {
            "level": "CRITICAL",
            "primary_concern": "safety",
            "reasoning": "Dangerous",
            "is_life_safety_risk": True,
        }
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert mock_sns.publish.called
            call_args = mock_sns.publish.call_args
            assert "CRITICAL" in call_args[1]["Subject"]

    def test_high_sends_sns_alert(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "HIGH", "primary_concern": "quality", "reasoning": "Issues"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert mock_sns.publish.called

    def test_medium_does_not_send_sns_alert(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "MEDIUM", "primary_concern": "packaging", "reasoning": "Minor"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert not mock_sns.publish.called

    def test_low_does_not_send_sns_alert(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "LOW", "primary_concern": "none", "reasoning": "Good"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert not mock_sns.publish.called

    def test_sns_failure_shows_warning_in_actions(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "CRITICAL", "primary_concern": "safety", "reasoning": "Test"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.side_effect = Exception("SNS error")
            mock_cw.put_metric_data.return_value = {}
            result = run_action_agent(
                sample_product_info, sample_triage_result, sample_patterns, safety
            )
            actions_text = " ".join(result["actions_taken"])
            assert "failed" in actions_text.lower() or "skipped" in actions_text.lower()


class TestCloudWatchMetrics:
    def test_critical_publishes_metrics(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "CRITICAL", "primary_concern": "safety", "reasoning": "Test"}
        with patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert mock_cw.put_metric_data.called

    def test_monitor_publishes_metric(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "MEDIUM", "primary_concern": "packaging", "reasoning": "Test"}
        with patch("agents.review_analyzer._cw") as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert mock_cw.put_metric_data.called

    def test_approve_publishes_metric(
        self, sample_product_info, sample_triage_result, sample_patterns
    ):
        safety = {"level": "LOW", "primary_concern": "none", "reasoning": "Test"}
        with patch("agents.review_analyzer._cw") as mock_cw:
            mock_cw.put_metric_data.return_value = {}
            run_action_agent(sample_product_info, sample_triage_result, sample_patterns, safety)
            assert mock_cw.put_metric_data.called
