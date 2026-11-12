"""Playwright browser contexts. No stealth/evasion logic is used."""
from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@contextmanager
def browser(headless: bool = False):
    """Launch installed Chrome in a normal browser context."""
    with sync_playwright() as playwright:
        browser_instance = playwright.chromium.launch(
            channel="chrome", headless=headless
        )
        context = browser_instance.new_context(
            user_agent=USER_AGENT,
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        try:
            yield context
        finally:
            context.close()
            browser_instance.close()


@contextmanager
def persistent_chrome_context(user_data_dir: str, headless: bool = False):
    """Persistent Chrome profile for sources that require a user login."""
    Path(user_data_dir).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir,
            channel="chrome",
            headless=headless,
            user_agent=USER_AGENT,
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        try:
            yield context
        finally:
            context.close()
