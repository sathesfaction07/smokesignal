import json
from unittest.mock import patch

from agents.review_analyzer import analyze_reviews_data


class TestFullPipeline:
    def test_pipeline_completes_all_four_stages(self, sample_reviews):
        data = {
            "asin": "B08RWPHMZF",
            "product_name": "Test Product",
            "marketplace": "amazon.com",
            "reviews": sample_reviews,
        }
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova, patch(
            "agents.review_analyzer._call_haiku"
        ) as mock_haiku, patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_nova.return_value = json.dumps(
                {"patterns": ["Safety concerns (2 reviews)", "Quality issues (3 reviews)"]}
            )
            mock_haiku.return_value = json.dumps(
                {
                    "level": "HIGH",
                    "primary_concern": "quality",
                    "positive_observations": "Some positive feedback",
                    "negative_observations": "Multiple complaints",
                    "reasoning": "Significant quality issues reported",
                    "is_life_safety_risk": False,
                }
            )
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            result = analyze_reviews_data(data)
            assert "product" in result
            assert "review_stats" in result
            assert "patterns" in result
            assert "assessment" in result
            assert "decision" in result

    def test_pipeline_uses_deterministic_stages(self, sample_reviews):
        data = {
            "asin": "B08RWPHMZF",
            "product_name": "Test Product",
            "marketplace": "amazon.com",
            "reviews": sample_reviews,
        }
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova, patch(
            "agents.review_analyzer._call_haiku"
        ) as mock_haiku, patch("agents.review_analyzer._sns"), patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_nova.return_value = json.dumps({"patterns": ["Test pattern"]})
            mock_haiku.return_value = json.dumps(
                {
                    "level": "LOW",
                    "primary_concern": "none",
                    "positive_observations": "Good",
                    "negative_observations": "None",
                    "reasoning": "Good product",
                    "is_life_safety_risk": False,
                }
            )
            mock_cw.put_metric_data.return_value = {}
            result = analyze_reviews_data(data)
            assert result["review_stats"]["total"] == len(sample_reviews)
            assert "category_breakdown" in result["review_stats"]

    def test_pipeline_uses_fallbacks_when_ai_fails(self, sample_reviews):
        data = {
            "asin": "B08RWPHMZF",
            "product_name": "Test Product",
            "marketplace": "amazon.com",
            "reviews": sample_reviews,
        }
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova, patch(
            "agents.review_analyzer._call_haiku"
        ) as mock_haiku, patch("agents.review_analyzer._cw") as mock_cw:
            mock_nova.side_effect = Exception("Bedrock unavailable")
            mock_haiku.side_effect = Exception("Bedrock unavailable")
            mock_cw.put_metric_data.return_value = {}
            result = analyze_reviews_data(data)
            assert "decision" in result
            assert result["decision"] in [
                "APPROVE",
                "MONITOR",
                "FLAG_FOR_REVIEW",
                "FLAG_FOR_REMOVAL",
            ]

    def test_pipeline_routes_critical_products_correctly(self, all_negative_reviews):
        data = {
            "asin": "B08RWPHMZF",
            "product_name": "Dangerous Product",
            "marketplace": "amazon.com",
            "reviews": all_negative_reviews,
        }
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova, patch(
            "agents.review_analyzer._call_haiku"
        ) as mock_haiku, patch("agents.review_analyzer._sns") as mock_sns, patch(
            "agents.review_analyzer._cw"
        ) as mock_cw:
            mock_nova.return_value = json.dumps({"patterns": ["Safety issues"]})
            mock_haiku.return_value = json.dumps(
                {
                    "level": "CRITICAL",
                    "primary_concern": "safety",
                    "positive_observations": "None",
                    "negative_observations": "Life-threatening failures",
                    "reasoning": "Product is dangerous",
                    "is_life_safety_risk": True,
                }
            )
            mock_sns.publish.return_value = {}
            mock_cw.put_metric_data.return_value = {}
            result = analyze_reviews_data(data)
            assert result["decision"] == "FLAG_FOR_REMOVAL"
            assert result["assessment"]["level"] == "CRITICAL"

    def test_pipeline_routes_safe_products_correctly(self, positive_reviews):
        data = {
            "asin": "B08RWPHMZF",
            "product_name": "Great Product",
            "marketplace": "amazon.com",
            "reviews": positive_reviews,
        }
        with patch("agents.review_analyzer._call_nova_micro") as mock_nova, patch(
            "agents.review_analyzer._call_haiku"
        ) as mock_haiku, patch("agents.review_analyzer._cw") as mock_cw:
            mock_nova.return_value = json.dumps({"patterns": []})
            mock_haiku.return_value = json.dumps(
                {
                    "level": "LOW",
                    "primary_concern": "none",
                    "positive_observations": "Excellent reviews",
                    "negative_observations": "None",
                    "reasoning": "Product is excellent",
                    "is_life_safety_risk": False,
                }
            )
            mock_cw.put_metric_data.return_value = {}
            result = analyze_reviews_data(data)
            assert result["decision"] == "APPROVE"
