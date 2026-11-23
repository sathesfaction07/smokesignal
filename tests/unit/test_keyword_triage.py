from agents.review_analyzer import (
    _keyword_scan,
)


class TestKeywordDetection:
    def test_detects_safety_keywords(self):
        reviews = [{"title": "Dangerous", "body": "Failed to detect smoke.", "rating": 1.0}]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["safety"] == 1

    def test_detects_quality_keywords(self):
        reviews = [
            {"title": "Broke quickly", "body": "Stopped working after two days.", "rating": 1.0}
        ]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["quality"] == 1

    def test_detects_packaging_keywords(self):
        reviews = [
            {"title": "Bad box", "body": "Arrived damaged with missing parts.", "rating": 2.0}
        ]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["packaging"] == 1

    def test_detects_misleading_keywords(self):
        reviews = [
            {"title": "Fake", "body": "Not as described, looks like a knockoff.", "rating": 1.0}
        ]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["misleading"] == 1

    def test_detects_disappointment_keywords(self):
        reviews = [
            {"title": "Regret", "body": "Waste of money, returned it immediately.", "rating": 1.0}
        ]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["disappointment"] == 1

    def test_case_insensitive_matching(self):
        reviews = [
            {"title": "DANGEROUS PRODUCT", "body": "BROKE AFTER ONE WEEK", "rating": 1.0},
            {"title": "waste of MONEY", "body": "Not As Described", "rating": 1.0},
        ]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["safety"] >= 1
        assert result["category_breakdown"]["quality"] >= 1
        assert result["category_breakdown"]["disappointment"] >= 1
        assert result["category_breakdown"]["misleading"] >= 1

    def test_multiple_categories_in_single_review(self):
        reviews = [
            {
                "title": "Dangerous and broke",
                "body": "Failed to detect and stopped working. Not as described.",
                "rating": 1.0,
            }
        ]
        result = _keyword_scan(reviews)
        assert result["category_breakdown"]["safety"] == 1
        assert result["category_breakdown"]["quality"] == 1
        assert result["category_breakdown"]["misleading"] == 1

    def test_no_matches_returns_zero_counts(self, positive_reviews):
        result = _keyword_scan(positive_reviews)
        assert result["negative_review_count"] == 0
        assert result["negative_review_pct"] == 0.0
        assert all(count == 0 for count in result["category_breakdown"].values())


