# ----- library import -----
from playwright.async_api import async_playwright

# ----- local import -----
from src.config.constants import HEADLESS


class BrowserManager:
    playwright = None
    browser = None
    context = None

    @classmethod
    async def start(cls):
        if cls.browser is None:
            cls.playwright = await async_playwright().start()

            cls.browser = await cls.playwright.chromium.launch(headless=HEADLESS)

            cls.context = await cls.browser.new_context()

        return cls.context
