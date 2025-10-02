import logging
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, Browser, Page
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages a stealthed Playwright browser, using an optional session file for auth.
    """

    def __init__(self, user_agent: str, headless: bool = True):
        self.user_agent = user_agent
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self.stealth = Stealth()

    async def __aenter__(self) -> "BrowserManager":
        logger.info("Starting browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser shut down.")

    async def new_page(self, session_file: Optional[str] = None) -> Page:
        if not self._browser:
            raise RuntimeError("Browser is not running. Use within 'async with' block.")

        context = None
        if session_file and Path(session_file).exists():
            logger.info(f"Loading session state from {session_file}")
            context = await self._browser.new_context(
                storage_state=session_file, user_agent=self.user_agent
            )
        else:
            if session_file:
                logger.warning(f"Session file not found at '{session_file}'. Creating unauthenticated context.")
            else:
                logger.info("No session file configured. Creating unauthenticated context.")
            context = await self._browser.new_context(user_agent=self.user_agent)

        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """)
        return page
