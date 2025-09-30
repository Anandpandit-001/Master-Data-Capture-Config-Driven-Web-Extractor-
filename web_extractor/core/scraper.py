import logging
import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
import pandas as pd
import re
import json
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from ..config.models import JobConfig, Entity
from .browser_manager import BrowserManager

logger = logging.getLogger(__name__)


class ScraperEngine:
    def __init__(self, config: JobConfig, browser_manager: BrowserManager):
        """
        Initializes the ScraperEngine with the job configuration.
        """
        self.config = config
        self.browser_manager = browser_manager

        # This dictionary will store the scraped data for each entity,
        # e.g., {"ProductList": [...], "ProductDetail": [...]}
        self.data_store: Dict[str, List[Dict[str, Any]]] = {}

        # This list will store the time taken to scrape each page for p95 calculation.
        self.extraction_times: List[float] = []

        # This list will store details about any errors encountered during the scrape.
        self.errors: List[Dict[str, Any]] = []

        # This counter tracks errors for the 'stop_after_n_errors' runtime feature.
        self.error_count: int = 0

    async def run(self):
        """
        Main execution method with stealth applied automatically for all pages.
        """
        page = None
        try:
            # Use BrowserManager to create a page; stealth is applied in new_page()
            page = await self.browser_manager.new_page(self.config.auth.session_file)

            # --- Discovery Phase ---
            if self.config.module.discovery:
                logger.info("--- Starting Discovery Phase ---")
                discovered_urls = await self._discover_urls(page)
                self.data_store["discovered_links"] = [{"url": url} for url in discovered_urls]
                logger.info("--- Finished Discovery Phase ---")

            # --- Entity Scraping Phase ---
            for entity in self.config.module.entities:
                await self._process_entity_concurrently(entity)

            # --- Save output ---
            self._save_output()

        except Exception as e:
            logger.error(f"A critical error occurred in run(): {e}", exc_info=True)
        finally:
            if page and not page.is_closed():
                await page.context.close()

    async def _discover_urls(self, page: Page) -> List[str]:
        """Navigates to a start page and discovers all detail page URLs using advanced logic."""
        discovery_config = self.config.module.discovery
        if not discovery_config: return []

        logger.info(f"Starting URL discovery at: {discovery_config.start_page}")
        await page.goto(discovery_config.start_page, wait_until="domcontentloaded")

        if discovery_config.wait_for_selectors:
            found = False
            for selector in discovery_config.wait_for_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=10000)
                    found = True;
                    break
                except PlaywrightTimeoutError:
                    logger.warning(f"Selector '{selector}' not found, trying next one.")
            if not found:
                logger.error("None of the discovery selectors appeared. Skipping discovery.");
                return []

        soup = BeautifulSoup(await page.content(), "lxml")
        elements = soup.select(discovery_config.link_selector)
        discovered_urls = set()

        for element in elements:
            attr_to_get = discovery_config.attribute or 'href'
            attr_value = element.get(attr_to_get)
            if not attr_value: continue

            if discovery_config.extract_regex and discovery_config.url_template:
                match = re.search(discovery_config.extract_regex, attr_value)
                if match:
                    extracted_id = match.group(1)
                    discovered_urls.add(discovery_config.url_template.format(id=extracted_id))
            else:
                discovered_urls.add(urljoin(self.config.site.base_url, attr_value))

        logger.info(f"Discovered {len(discovered_urls)} unique URLs.")
        return list(discovered_urls)

    async def _process_entity_concurrently(self, entity: Entity):
        """
        Handles scraping for a single entity concurrently, with stealth applied automatically.
        """
        semaphore = asyncio.Semaphore(self.config.runtime.concurrency)
        urls_to_scrape = []

        if entity.url:
            urls_to_scrape.append(urljoin(self.config.site.base_url, entity.url))
        elif entity.follow_from:
            source_entity, source_field = entity.follow_from.split(".")
            if source_entity in self.data_store:
                urls_to_scrape = [
                    urljoin(self.config.site.base_url, row[source_field])
                    for row in self.data_store[source_entity] if row.get(source_field)
                ]

        if not urls_to_scrape:
            logger.warning(f"No URLs to scrape for entity: {entity.name}")
            self.data_store[entity.name] = []
            return

        tasks = [asyncio.create_task(self._scrape_url_task(url, entity, semaphore)) for url in urls_to_scrape]
        results_from_tasks = await asyncio.gather(*tasks)

        flat_results = [item for sublist in results_from_tasks for item in sublist]
        self.data_store[entity.name] = flat_results
        logger.info(f"--- Finished entity: {entity.name}. Found {len(flat_results)} items. ---")
    async def _scrape_url_task(self, url: str, entity: Entity, semaphore: asyncio.Semaphore) -> List[Dict[str, Any]]:
        """A single, concurrent scraping task that respects the semaphore."""
        async with semaphore:
            # Check if we should stop due to too many errors
            if self.error_count >= self.config.runtime.stop_after_n_errors:
                logger.warning(
                    f"Stopping job due to exceeding error limit of {self.config.runtime.stop_after_n_errors}.")
                return []

            # Create a new page for each concurrent task to ensure isolation
            page = await self.browser_manager.new_page(self.config.auth.session_file)
            entity_results = []

            try:
                if entity.paginate:
                    page_num = entity.paginate.start
                    current_url = url
                    while True:
                        paginated_url = current_url.format(page=page_num)
                        rows_data = await self._scrape_page(page, paginated_url, entity)
                        if not rows_data: break
                        entity_results.extend(rows_data)
                        page_num += 1
                        # Respect the delay between page loads
                        await asyncio.sleep(self.config.runtime.sleep_ms_between_pages / 1000)
                else:
                    rows_data = await self._scrape_page(page, url, entity)
                    entity_results.extend(rows_data)

            except Exception as e:
                logger.error(f"Task for URL {url} failed: {e}")
                self.error_count += 1
            finally:
                if page and not page.is_closed():
                    await page.context.close()

            return entity_results

    # --- UPDATE THIS METHOD TO RECORD TIME ---
    async def _scrape_page(self, page: Page, url: str, entity: Entity) -> List[Dict[str, Any]]:
        """
        Scrapes a single page, extracts all item rows, records performance,
        and logs any errors.
        """
        try:
            start_time = time.time()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector(entity.row_selector, timeout=15000)

            # Record the successful page load time for performance metrics
            self.extraction_times.append(time.time() - start_time)

        except PlaywrightTimeoutError:
            msg = f"Timeout waiting for row selector '{entity.row_selector}' on {url}."
            logger.warning(msg)

            # Add detailed error information to the errors list for reporting
            self.errors.append({"url": url, "stage": "navigation", "error": msg})
            return []

        soup = BeautifulSoup(await page.content(), "lxml")
        rows = soup.select(entity.row_selector)

        # Extract data from each row found on the page
        return [self._extract_data_from_row(row_soup, entity.fields) for row_soup in rows]

    def _extract_data_from_row(self, soup: Tag, fields: Dict[str, str]) -> Dict[str, Any]:
        """
        Extracts all configured fields from a single HTML element (row).
        Supports 'selector@attribute' syntax for flexibility.
        """
        row_data = {}
        for field_name, selector_str in fields.items():
            try:
                # Split the selector from the attribute, if specified (e.g., "a@href")
                parts = selector_str.split('@')
                selector = parts[0]
                attribute = parts[1] if len(parts) > 1 else None

                element = soup.select_one(selector)

                if element:
                    if attribute:
                        # If an attribute is specified (like 'href', 'src'), get its value.
                        row_data[field_name] = (element.get(attribute) or '').strip()
                    else:
                        # Otherwise, get the clean text content of the element.
                        row_data[field_name] = element.get_text(strip=True)
                else:
                    # If the element is not found, record it as None.
                    logger.warning(f"Selector '{selector}' not found for field '{field_name}'.")
                    row_data[field_name] = None

            except Exception as e:
                # Catch any unexpected errors during extraction for this field
                logger.error(f"Error extracting field '{field_name}' with selector '{selector_str}': {e}")
                row_data[field_name] = None

        return row_data

    def _save_output(self):
        """
        Saves the data for each scraped entity, handling deduplication and ensuring
        correct serialization for all file formats.
        """
        output_config = self.config.output
        output_dir = Path(output_config.dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Preparing to save output in '{output_dir}' directory...")

        for entity_name, data in self.data_store.items():
            if not data:
                logger.info(f"No data for entity '{entity_name}'. Skipping output.")
                continue

            # Create the DataFrame once
            df = pd.DataFrame(data)

            # Deduplication logic
            if output_config.primary_key:
                pk_list = [k for k in output_config.primary_key if k in df.columns]
                if pk_list:
                    initial_count = len(df)
                    df.drop_duplicates(subset=pk_list, keep='first', inplace=True)
                    deduplicated_count = initial_count - len(df)
                    if deduplicated_count > 0:
                        logger.info(
                            f"Removed {deduplicated_count} duplicate items for entity '{entity_name}' using primary key: {pk_list}"
                        )

            base_filename = f"{self.config.site.name}_{self.config.module.name}_{entity_name}"

            for fmt in output_config.formats:
                file_path = output_dir / f"{base_filename}.{fmt.lower()}"
                try:
                    logger.info(f"Saving {len(df)} items for entity '{entity_name}' to {file_path}")
                    if fmt.lower() == "csv":
                        df.to_csv(file_path, index=False)
                    # --- THIS IS THE CORRECTED PART ---
                    # Use pandas's built-in JSON exporter
                    elif fmt.lower() == "json":
                        df.to_json(file_path, orient="records", indent=4)
                    elif fmt.lower() == "xlsx":
                        df.to_excel(file_path, index=False)
                    else:
                        logger.warning(f"Unsupported format: {fmt}")

                except Exception as e:
                    logger.error(f"Failed to save {entity_name} data to {fmt}: {e}")
