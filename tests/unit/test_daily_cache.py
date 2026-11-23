import json
from datetime import date
from unittest.mock import patch

from monitoring.daily_cache import (
    _cache_file,
    _purge_old_caches,
    get_cached_result,
    save_result,
)


class TestCacheKeyConstruction:
    def test_cache_key_includes_asin_and_marketplace(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            result_data = {"test": "data"}
            save_result("B08RWPHMZF", "amazon.com", result_data)
            cached = get_cached_result("B08RWPHMZF", "amazon.com")
            assert cached == result_data

    def test_different_asins_have_separate_cache_entries(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            save_result("ASIN1", "amazon.com", {"test": "asin1"})
            save_result("ASIN2", "amazon.com", {"test": "asin2"})
            assert get_cached_result("ASIN1", "amazon.com") == {"test": "asin1"}
            assert get_cached_result("ASIN2", "amazon.com") == {"test": "asin2"}

    def test_different_marketplaces_have_separate_cache_entries(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            save_result("B08RWPHMZF", "amazon.com", {"test": "us"})
            save_result("B08RWPHMZF", "amazon.co.uk", {"test": "uk"})
            assert get_cached_result("B08RWPHMZF", "amazon.com") == {"test": "us"}
            assert get_cached_result("B08RWPHMZF", "amazon.co.uk") == {"test": "uk"}


class TestCacheHitAndMiss:
    def test_cache_miss_returns_none(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            result = get_cached_result("NONEXISTENT", "amazon.com")
            assert result is None

    def test_cache_hit_after_save(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            data = {"decision": "APPROVE", "patterns": ["good quality"]}
            save_result("B08RWPHMZF", "amazon.com", data)
            cached = get_cached_result("B08RWPHMZF", "amazon.com")
            assert cached == data

    def test_multiple_saves_update_existing_entry(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            save_result("B08RWPHMZF", "amazon.com", {"version": 1})
            save_result("B08RWPHMZF", "amazon.com", {"version": 2})
            cached = get_cached_result("B08RWPHMZF", "amazon.com")
            assert cached == {"version": 2}


class TestSameDayBehavior:
    def test_cache_persists_across_multiple_reads(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            data = {"test": "persistence"}
            save_result("B08RWPHMZF", "amazon.com", data)
            first_read = get_cached_result("B08RWPHMZF", "amazon.com")
            second_read = get_cached_result("B08RWPHMZF", "amazon.com")
            third_read = get_cached_result("B08RWPHMZF", "amazon.com")
            assert first_read == data
            assert second_read == data
            assert third_read == data

    def test_cache_file_path_uses_today_date(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            cache_path = _cache_file()
            assert date.today().isoformat() in cache_path.name


class TestDifferentDayBehavior:
    def test_purge_removes_old_cache_files(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            old_cache = tmp_path / "results_2024-01-01.json"
            old_cache.write_text(json.dumps({"old": "data"}))
            today_cache = tmp_path / f"results_{date.today().isoformat()}.json"
            today_cache.write_text(json.dumps({"today": "data"}))
            _purge_old_caches()
            assert not old_cache.exists()
            assert today_cache.exists()

    def test_purge_preserves_today_cache(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            save_result("B08RWPHMZF", "amazon.com", {"test": "data"})
            _purge_old_caches()
            cached = get_cached_result("B08RWPHMZF", "amazon.com")
            assert cached == {"test": "data"}

    def test_get_cached_result_triggers_purge(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            old_cache = tmp_path / "results_2024-01-01.json"
            old_cache.write_text(json.dumps({"old": "data"}))
            get_cached_result("ANY", "amazon.com")
            assert not old_cache.exists()


class TestCacheFileStructure:
    def test_cache_creates_directory_if_missing(self, tmp_path):
        cache_dir = tmp_path / "nested" / "cache"
        with patch("monitoring.daily_cache.CACHE_DIR", cache_dir):
            save_result("B08RWPHMZF", "amazon.com", {"test": "data"})
            assert cache_dir.exists()

    def test_cache_file_is_valid_json(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            save_result("B08RWPHMZF", "amazon.com", {"test": "data"})
            cache_path = _cache_file()
            assert cache_path.exists()
            with open(cache_path) as f:
                data = json.load(f)
                assert isinstance(data, dict)

    def test_empty_cache_returns_empty_dict(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            result = get_cached_result("NONEXISTENT", "amazon.com")
            assert result is None


class TestComplexCacheData:
    def test_caches_nested_structures(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            complex_data = {
                "product": {"asin": "B08RWPHMZF", "name": "Test Product"},
                "review_stats": {"total": 10, "category_breakdown": {"safety": 2, "quality": 3}},
                "patterns": ["pattern1", "pattern2"],
                "assessment": {"level": "HIGH", "reasoning": "Multiple issues"},
            }
            save_result("B08RWPHMZF", "amazon.com", complex_data)
            cached = get_cached_result("B08RWPHMZF", "amazon.com")
            assert cached == complex_data

    def test_handles_unicode_in_cache(self, tmp_path):
        with patch("monitoring.daily_cache.CACHE_DIR", tmp_path):
            data = {"review": "Très bon produit! 好评!"}
            save_result("B08RWPHMZF", "amazon.fr", data)
            cached = get_cached_result("B08RWPHMZF", "amazon.fr")
            assert cached == data
