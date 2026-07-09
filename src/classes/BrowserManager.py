# ----- library import -----
from playwright.async_api import async_playwright

# ----- local import -----
from src.config.constants import HEADLESS, SESSION_DIR


class BrowserManager:
    playwright = None
    browser = None
    context = None
    _default_page_closed = False

    @classmethod
    async def start(cls):
        if cls.context is None:
            if cls.playwright is None:
                cls.playwright = await async_playwright().start()

            cls.context = await cls.playwright.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=HEADLESS,
            )

            cls.context.on("close", cls._reset)

            cls.browser = cls.context.browser
            cls._default_page_closed = False

        return cls.context

    @classmethod
    async def new_page(cls):
        context = await cls.start()
        page = await context.new_page()

        if not cls._default_page_closed:
            cls._default_page_closed = True
            for stale in context.pages:
                if stale is not page and stale.url == "about:blank":
                    await stale.close()

        return page

    @classmethod
    def _reset(cls, *_args):
        cls.context = None
        cls.browser = None
        cls._default_page_closed = False

    @classmethod
    async def close(cls):
        if cls.context is not None:
            await cls.context.close()
            cls.context = None
            cls.browser = None
            cls._default_page_closed = False

        if cls.playwright is not None:
            await cls.playwright.stop()
            cls.playwright = None
