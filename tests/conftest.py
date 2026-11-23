from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_reviews():
    return [
        {
            "title": "Never went off during CO leak",
            "body": (
                "Had an actual carbon monoxide leak confirmed by fire dept. "
                "This detector sat there silently. Dangerous product."
            ),
            "rating": 1.0,
        },
        {
            "title": "Stopped working after 3 months",
            "body": (
                "Broke after just 3 months. Cheap quality plastic, "
                "fell apart when I tried to change battery."
            ),
            "rating": 1.0,
        },
        {
            "title": "Arrived damaged",
            "body": "Box was crushed, missing parts inside. Poor packaging for a safety device.",
            "rating": 2.0,
        },
        {
            "title": "Not as described",
            "body": (
                "Product looks nothing like the picture. "
                "Smaller than expected, feels like a knockoff."
            ),
            "rating": 2.0,
        },
        {
            "title": "Waste of money",
            "body": "Returned it after a week. Terrible quality, would not recommend to anyone.",
            "rating": 1.0,
        },
        {
            "title": "Does the job",
            "body": "Works fine so far. Easy to install on the ceiling.",
            "rating": 4.0,
        },
        {
            "title": "Good value",
            "body": "Affordable and seems reliable. Time will tell.",
            "rating": 4.0,
        },
        {
            "title": "Life saver",
            "body": "Detected a small gas leak early. Very happy with this purchase.",
            "rating": 5.0,
        },
    ]


@pytest.fixture
def positive_reviews():
    return [
        {"title": "Great product", "body": "Works perfectly. Very happy.", "rating": 5.0},
        {"title": "Love it", "body": "Excellent quality, fast shipping.", "rating": 5.0},
        {"title": "Good value", "body": "Does what it says. No complaints.", "rating": 4.0},
        {"title": "Satisfied", "body": "Works as expected. Good purchase.", "rating": 4.0},
    ]


@pytest.fixture
def all_negative_reviews():
    return [
        {
            "title": "Dangerous",
            "body": "Failed to detect smoke. Life-threatening product.",
            "rating": 1.0,
        },
        {
            "title": "Broke immediately",
            "body": "Stopped working after one day. Defective.",
            "rating": 1.0,
        },
        {
            "title": "Scam",
            "body": "Not as described. Complete waste of money.",
            "rating": 1.0,
        },
    ]


@pytest.fixture
def mock_boto3_client(monkeypatch):
    mock_client = MagicMock()

    def mock_client_factory(*args, **kwargs):
        return mock_client

    monkeypatch.setattr("boto3.client", mock_client_factory)
    return mock_client


@pytest.fixture
def sample_triage_result():
    return {
        "total_reviews": 8,
        "avg_rating": 2.8,
        "negative_review_count": 5,
        "negative_review_pct": 0.625,
        "category_breakdown": {
            "safety": 2,
            "quality": 3,
            "packaging": 1,
            "misleading": 1,
            "disappointment": 2,
        },
        "top_concern": "quality",
        "severity": "CRITICAL",
        "reasoning": (
            "5/8 reviews (62%) contain negative signals. Breakdown: safety: 2 | quality: 3 | "
            "packaging: 1 | misleading: 1 | disappointment: 2. Top concern: quality."
        ),
    }


@pytest.fixture
def sample_product_info():
    return {
        "asin": "B08RWPHMZF",
        "name": "SafeGuard CO Detector Pro",
        "marketplace": "amazon.com",
    }


@pytest.fixture
def sample_patterns():
    return [
        "Safety concerns (2 reviews)",
        "Quality/durability complaints (3 reviews)",
        "Packaging issues (1 review)",
    ]
