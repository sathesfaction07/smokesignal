"""
agents/review_fetcher.py — Selenium-based Amazon review scraper.

Uses Chrome headless with multi-tab parallel loading for speed.
Includes graceful browser cleanup on unexpected termination.
"""

import sys
import time
import atexit
import signal
import weakref

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import MARKETPLACES

# ─────────────────────────────────────────────────────────────────────────────
# Global driver registry for graceful cleanup on unexpected termination
# ─────────────────────────────────────────────────────────────────────────────
_active_drivers = weakref.WeakSet()


def _cleanup_all_drivers():
    """Kill ALL active browser instances. Called on exit/signal."""
    for driver in list(_active_drivers):
        try:
            driver.quit()
            print("[Fetcher] Graceful shutdown: browser closed.")
        except Exception:
            pass


# Register cleanup for normal exit
atexit.register(_cleanup_all_drivers)

# Register cleanup for SIGTERM/SIGINT
def _signal_handler(signum, frame):
    _cleanup_all_drivers()
    sys.exit(0)


try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
except (OSError, ValueError):
    pass  # Signals can't be set in non-main threads


# ─────────────────────────────────────────────────────────────────────────────
# Browser setup
# ─────────────────────────────────────────────────────────────────────────────

def _create_driver():
    """Create a headless Chrome browser instance optimized for speed."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
    # Speed: don't wait for every asset — DOM-interactive is enough for
    # our selectors, and images are never needed for text extraction.
    options.page_load_strategy = "eager"
    options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(25)
    _active_drivers.add(driver)  # Register for graceful cleanup
    return driver


# ─────────────────────────────────────────────────────────────────────────────
# Extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_product_info(driver, asin):
    """Extract product name, rating, and review count from the page."""
    info = {"name": "Unknown Product", "rating": 0.0, "review_count": 0, "category": "Unknown"}

    try:
        title_el = driver.find_element(By.ID, "productTitle")
        info["name"] = title_el.text.strip()
    except Exception:
        pass

    try:
        rating_el = driver.find_element(By.CSS_SELECTOR, "span[data-hook='rating-out-of-text']")
        info["rating"] = float(rating_el.text.split()[0])
    except Exception:
        try:
            rating_el = driver.find_element(By.CSS_SELECTOR, "i.a-icon-star span.a-icon-alt")
            info["rating"] = float(rating_el.get_attribute("textContent").split()[0])
        except Exception:
            pass

    try:
        count_el = driver.find_element(By.ID, "acrCustomerReviewCount")
        text = count_el.text.replace(",", "").split()[0]
        info["review_count"] = int(text)
    except Exception:
        pass

    try:
        breadcrumb = driver.find_element(By.ID, "wayfinding-breadcrumbs_feature_div")
        info["category"] = breadcrumb.text.strip().split("\n")[0]
    except Exception:
        pass

    return info


def _extract_reviews(driver):
    """Extract review divs from the product page (/dp/ or /product-reviews/)."""
    reviews = []
    try:
        review_divs = driver.find_elements(By.CSS_SELECTOR, "div[data-hook='review']")
        for div in review_divs[:20]:  # Cap at 20 reviews
            review = {}
            # Title: multiple selector patterns for /dp/ vs /product-reviews/ pages
            try:
                title_els = div.find_elements(
                    By.CSS_SELECTOR,
                    "a[data-hook='review-title'] span:not([class*='a-letter-space']), "
                    "span[data-hook='review-title'] span:not([class*='a-letter-space']), "
                    "[data-hook='review-title']"
                )
                review["title"] = title_els[-1].get_attribute("textContent").strip() if title_els else ""
            except Exception:
                review["title"] = ""
            # Body: /dp/ uses review-body or reviewRichContentContainer
            try:
                body_els = div.find_elements(
                    By.CSS_SELECTOR,
                    "span[data-hook='review-body'], "
                    "[data-hook='reviewRichContentContainer']"
                )
                if body_els:
                    text = body_els[-1].get_attribute("textContent").strip()
                    # Strip expander UI noise
                    for noise in ("Read moreRead less", "Read more", "Read less"):
                        text = text.replace(noise, "").strip()
                    review["body"] = text
                else:
                    review["body"] = ""
            except Exception:
                review["body"] = ""
            # Rating
            try:
                rating_els = div.find_elements(
                    By.CSS_SELECTOR,
                    "i[data-hook='review-star-rating'] span, "
                    "i[data-hook='cmps-review-star-rating'] span"
                )
                if rating_els:
                    review["rating"] = float(rating_els[0].get_attribute("textContent").split()[0])
                else:
                    review["rating"] = 0.0
            except Exception:
                review["rating"] = 0.0
            if review.get("title") or review.get("body"):
                reviews.append(review)
    except Exception:
        pass
    return reviews


# ─────────────────────────────────────────────────────────────────────────────
# Single ASIN fetch
# ─────────────────────────────────────────────────────────────────────────────

def fetch_reviews(asin: str, marketplace: str = "US") -> dict:
    """Fetch reviews for a single ASIN. Returns a result dict."""
    domain = MARKETPLACES.get(marketplace, MARKETPLACES["US"])
    url = f"https://{domain}/dp/{asin}"
    driver = _create_driver()

    try:
        driver.get(url)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='review'], #productTitle"))
            )
        except TimeoutException:
            pass

        product_info = _extract_product_info(driver, asin)
        reviews = _extract_reviews(driver)

        return {
            "marketplace": domain.replace("www.", ""),
            "marketplace_domain": domain.replace("www.", ""),
            "region": marketplace,
            "asin": asin,
            "product_name": product_info["name"],
            "category": product_info.get("category", "Unknown"),
            "average_rating": product_info["rating"],
            "total_reviews": product_info["review_count"],
            "reviews": reviews,
        }
    finally:
        driver.quit()


# ─────────────────────────────────────────────────────────────────────────────
# Batch fetch (all tabs at once)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_reviews_batch(asins: list, marketplace: str = "US") -> list:
    """
    Fetch reviews for MULTIPLE ASINs using a single browser with multiple tabs.
    All tabs load in parallel — significantly faster than sequential.
    """
    domain = MARKETPLACES.get(marketplace, MARKETPLACES["US"])
    driver = _create_driver()
    results = []

    try:
        # Open all tabs in parallel
        for i, asin in enumerate(asins):
            url = f"https://{domain}/dp/{asin}"
            if i == 0:
                driver.get(url)
            else:
                driver.execute_script(f"window.open('{url}')")

        # Wait for tabs to become usable
        handles = driver.window_handles
        for i, (asin, handle) in enumerate(zip(asins, handles)):
            driver.switch_to.window(handle)
            try:
                WebDriverWait(driver, 10 if i == 0 else 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='review'], #productTitle"))
                )
            except TimeoutException:
                pass

            product_info = _extract_product_info(driver, asin)
            reviews = _extract_reviews(driver)

            results.append({
                "marketplace": domain.replace("www.", ""),
                "marketplace_domain": domain.replace("www.", ""),
                "region": marketplace,
                "asin": asin,
                "product_name": product_info["name"],
                "category": product_info.get("category", "Unknown"),
                "average_rating": product_info["rating"],
                "total_reviews": product_info["review_count"],
                "reviews": reviews,
            })
    finally:
        driver.quit()

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Streaming fetch (generator — opens all tabs, yields results one by one)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_reviews_streaming(asins: list, marketplace: str = "US"):
    """
    Generator: opens all tabs at once, then yields results one by one.
    Used by the SSE streaming endpoint for real-time UI updates.
    """
    domain = MARKETPLACES.get(marketplace, MARKETPLACES["US"])
    driver = _create_driver()

    try:
        # Open all tabs in parallel
        for i, asin in enumerate(asins):
            url = f"https://{domain}/dp/{asin}"
            if i == 0:
                driver.get(url)
            else:
                driver.execute_script(f"window.open('{url}')")

        # Wait for first tab, then extract from each
        handles = driver.window_handles
        for i, (asin, handle) in enumerate(zip(asins, handles)):
            driver.switch_to.window(handle)
            try:
                WebDriverWait(driver, 10 if i == 0 else 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-hook='review'], #productTitle"))
                )
            except TimeoutException:
                pass

            try:
                product_info = _extract_product_info(driver, asin)
                reviews = _extract_reviews(driver)
                yield {
                    "asin": asin,
                    "success": True,
                    "data": {
                        "marketplace": domain.replace("www.", ""),
                        "marketplace_domain": domain.replace("www.", ""),
                        "region": marketplace,
                        "asin": asin,
                        "product_name": product_info["name"],
                        "category": product_info.get("category", "Unknown"),
                        "average_rating": product_info["rating"],
                        "total_reviews": product_info["review_count"],
                        "reviews": reviews,
                    },
                }
            except Exception as e:
                yield {"asin": asin, "success": False, "error": str(e)}
    finally:
        driver.quit()
