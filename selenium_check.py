"""Run on your Mac:  ./venv/bin/python selenium_check.py
Opens a real Chrome (Selenium downloads the matching driver itself), searches, prints the titles."""
import integrations as ig
try:
    r = ig.selenium_search("latest AI news", headless=False)
    print("OK" if r else "Chrome opened but no results (site layout/captcha)", r)
except Exception as e:
    print("FAILED:", str(e)[:300])
