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
from datetime import datetime
from ..utils.reporting import get_git_commit_hash
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
        """Main execution method with discovery, concurrency, and unified output."""
        page = None
        try:
            page = await self.browser_manager.new_page(self.config.auth.session_file)

            if self.config.module.discovery:
                logger.info("--- Starting Discovery Phase ---")
                discovered_urls = await self._discover_urls(page)
                self.data_store["discovered_links"] = [{"url": url} for url in discovered_urls]
                logger.info("--- Finished Discovery Phase ---")

            for entity in self.config.module.entities:
                await self._process_entity_concurrently(entity)

            self._save_final_output()

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
        """Handles scraping for a single entity concurrently."""
        semaphore = asyncio.Semaphore(self.config.runtime.concurrency)
        items_to_process = []

        if entity.url:
            items_to_process.append({"url": urljoin(self.config.site.base_url, entity.url)})
        elif entity.follow_from:
            source_entity, source_field = entity.follow_from.split(".")
            if source_entity in self.data_store:
                items_to_process = [
                    {**row, "url": urljoin(self.config.site.base_url, row[source_field])}
                    for row in self.data_store[source_entity] if row.get(source_field)
                ]

        if not items_to_process:
            logger.warning(f"No URLs to scrape for entity: {entity.name}")
            self.data_store[entity.name] = []
            return

        tasks = [asyncio.create_task(self._scrape_url_task(item, entity, semaphore)) for item in items_to_process]
        results_from_tasks = await asyncio.gather(*tasks)

        flat_results = [item for sublist in results_from_tasks for item in sublist]
        self.data_store[entity.name] = flat_results
        logger.info(f"--- Finished entity: {entity.name}. Found {len(flat_results)} items. ---")

    async def _scrape_url_task(self, item: Dict[str, Any], entity: Entity, semaphore: asyncio.Semaphore) -> List[
        Dict[str, Any]]:
        """Scrapes a single URL, respecting the semaphore and merging data."""
        async with semaphore:
            if self.error_count >= self.config.runtime.stop_after_n_errors:
                return []

            page = await self.browser_manager.new_page(self.config.auth.session_file)
            results = []
            url = item["url"]
            initial_data = {k: v for k, v in item.items() if k != "url"}

            try:
                if entity.paginate:
                    page_num = entity.paginate.start
                    while True:
                        paginated_url = url.format(page=page_num)
                        rows_data = await self._scrape_page(page, paginated_url, entity, initial_data)
                        if not rows_data: break
                        results.extend(rows_data)
                        page_num += 1
                        await asyncio.sleep(self.config.runtime.sleep_ms_between_pages / 1000)
                else:
                    rows_data = await self._scrape_page(page, url, entity, initial_data)
                    results.extend(rows_data)
            except Exception as e:
                logger.error(f"Task for URL {url} failed: {e}")
                self.error_count += 1
                self.errors.append({"url": url, "entity": entity.name, "error": str(e)})
            finally:
                if page and not page.is_closed():
                    await page.context.close()
            return results

    # --- UPDATE THIS METHOD TO RECORD TIME ---
    async def _scrape_page(self, page: Page, url: str, entity: Entity, initial_data: Dict[str, Any]) -> List[
        Dict[str, Any]]:
        try:
            start_time = time.time()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector(entity.row_selector, timeout=15000)
            self.extraction_times.append(time.time() - start_time)
        except PlaywrightTimeoutError as e:
            self.errors.append({"url": url, "entity": entity.name, "error": str(e)})
            return []

        soup = BeautifulSoup(await page.content(), "lxml")
        rows = soup.select(entity.row_selector)
        return [self._extract_data_from_row(row, entity.fields, initial_data) for row in rows]

    def _extract_data_from_row(self, soup: Tag, fields: Dict[str, str], initial_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts all configured fields from a single HTML element (row),
        merges it with initial data, and handles errors gracefully.
        """
        # Start with the data passed from the previous entity (e.g., ProductList)
        row_data = initial_data.copy()

        for field_name, selector_str in fields.items():
            try:
                parts = selector_str.split('@')
                selector = parts[0]
                attribute = parts[1] if len(parts) > 1 else None

                element = soup.select_one(selector)

                if element:
                    if attribute:
                        row_data[field_name] = (element.get(attribute) or '').strip()
                    else:
                        row_data[field_name] = element.get_text(strip=True)
                else:
                    # Log a warning for non-critical missing elements
                    logger.warning(f"Selector '{selector}' not found for field '{field_name}'.")
                    row_data[field_name] = None

            except Exception as e:
                # Log a critical error and add it to the final report
                msg = f"Error extracting field '{field_name}' with selector '{selector_str}': {e}"
                logger.error(msg)
                self.errors.append({"field": field_name, "selector": selector_str, "error": str(e)})
                row_data[field_name] = None

        return row_data

    def _save_output(self):
        """
        Saves the final, merged data from the last entity in the chain to
        timestamped files, handling deduplication as configured.
        """
        output_config = self.config.output
        output_dir = Path(output_config.dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Get the name of the last entity, which holds the final merged data
        final_entity_name = self.config.module.entities[-1].name
        final_data = self.data_store.get(final_entity_name)

        if not final_data:
            logger.warning("No final data was produced to save.")
            return

        df = pd.DataFrame(final_data)
        logger.info(f"Preparing to save {len(df)} final items from entity '{final_entity_name}'.")

        # 2. Perform deduplication on the final DataFrame
        if output_config.primary_key:
            pk_list = [key for key in output_config.primary_key if key in df.columns]
            if pk_list:
                initial_count = len(df)
                df.drop_duplicates(subset=pk_list, keep='first', inplace=True)
                deduplicated_count = initial_count - len(df)
                if deduplicated_count > 0:
                    logger.info(f"Removed {deduplicated_count} duplicate items using primary key: {pk_list}")

        # 3. Generate the advanced, timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        commit_hash = get_git_commit_hash()
        base_filename = f"{self.config.site.name}_{self.config.module.name}_{final_entity_name}_{timestamp}_{commit_hash}"

        # 4. Save the cleaned DataFrame to all specified formats
        for format_str in output_config.formats:
            file_path = output_dir / f"{base_filename}.{format_str.lower()}"
            try:
                logger.info(f"Saving {len(df)} items to {file_path}")
                if format_str.lower() == 'csv':
                    df.to_csv(file_path, index=False)
                elif format_str.lower() == 'json':
                    df.to_json(file_path, orient="records", indent=4)
                elif format_str.lower() == 'xlsx':
                    df.to_excel(file_path, index=False)
                else:
                    logger.warning(f"Unsupported format: {format_str}")
            except Exception as e:
                logger.error(f"Failed to save output to {format_str}: {e}")
