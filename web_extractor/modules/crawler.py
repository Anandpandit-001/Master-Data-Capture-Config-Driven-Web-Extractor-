import logging
import asyncio
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import Page
from ..config.models import JobConfig

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, config: JobConfig, page: Page):
        self.config = config
        self.page = page
        self.base_url = config.static_config.base_url
        self.download_path = Path(config.static_config.download_path.format(job_name=config.static_config.job_name))
        self.processed_urls = set()

    async def run(self):
        """Discovers and downloads all accessible pages from the start_urls."""
        self.download_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Starting crawl. HTML files will be saved to: {self.download_path}")

        for url in self.config.static_config.start_urls:
            await self._crawl_page(url)

        logger.info(f"Crawl complete. Downloaded {len(self.processed_urls)} pages.")

    async def _crawl_page(self, url: str):
        """Recursively crawls and downloads pages, handling 'next_button' pagination."""
        if url in self.processed_urls:
            return

        logger.info(f"Downloading page: {url}")
        try:
            await self.page.goto(url, wait_until="domcontentloaded")

            # Wait for the main item selector to ensure content is loaded
            if self.config.dynamic_config.item_selector:
                item_selector = self.config.dynamic_config.item_selector
                if isinstance(item_selector, list):
                    item_selector = item_selector[0]
                await self.page.wait_for_selector(item_selector, timeout=15000)

            html_content = await self.page.content()
            filename = f"{url.replace('https://', '').replace('http://', '').replace('/', '_')}.html"
            with open(self.download_path / filename, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.processed_urls.add(url)

            # Follow to the next page if pagination is configured
            pagination_config = self.config.static_config.pagination
            if pagination_config and pagination_config.type == 'next_button':
                soup = BeautifulSoup(html_content, "lxml")
                next_element = soup.select_one(pagination_config.selector)
                if next_element and next_element.get('href'):
                    next_url = urljoin(self.base_url, next_element.get('href'))
                    await asyncio.sleep(2)
                    await self._crawl_page(next_url)
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {e}")