# scraper.py (REVISED)

import logging
import asyncio
import time
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag
import pandas as pd
from typing import Any, Dict, List, Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from datetime import datetime

from ..utils.reporting import get_git_commit_hash
from ..config.models import JobConfig, Entity
from .browser_manager import BrowserManager

logger = logging.getLogger(__name__)


class ScraperEngine:
    def __init__(self, config: JobConfig, browser_manager: BrowserManager):
        self.config = config
        self.browser_manager = browser_manager
        self.data_store: Dict[str, List[Dict[str, Any]]] = {}
        self.extraction_times: List[float] = []
        self.errors: List[Dict[str, Any]] = []
        self.error_count: int = 0

    async def run(self):
        """Main entry point: scrape all entities defined in the config sequentially."""
        logger.info("Starting scraper engine run.")
        for entity in self.config.module.entities:
            await self._process_entity_concurrently(entity)
        logger.info("Scraper engine run finished.")
        self._save_output()

    async def _process_entity_concurrently(self, entity: Entity):
        """
        Scrape a single entity. If it follows from another, it uses the previous
        entity's results as a source for URLs. Handles concurrency.
        """
        semaphore = asyncio.Semaphore(self.config.runtime.concurrency)
        items_to_process = []

        if entity.url:
            # This is a starting entity. It has its own URL.
            full_url = urljoin(self.config.site.base_url, entity.url)
            items_to_process.append({"url": full_url})
        elif entity.follow_from:
            # This entity depends on a previous one.
            try:
                source_entity_name, source_field = entity.follow_from.split(".")
            except ValueError:
                logger.error(f"Invalid 'follow_from' format: {entity.follow_from}. Should be 'EntityName.fieldName'.")
                return

            if source_entity_name in self.data_store:
                source_data = self.data_store[source_entity_name]
                for row in source_data:
                    if row.get(source_field):
                        # Inherit data from the source row and add the new URL to scrape
                        item = row.copy()
                        item["url"] = urljoin(self.config.site.base_url, row[source_field])
                        items_to_process.append(item)
            else:
                logger.warning(f"Source entity '{source_entity_name}' for '{entity.name}' not found or has no data.")

        if not items_to_process:
            logger.warning(f"No URLs to scrape for entity: {entity.name}")
            self.data_store[entity.name] = []
            return

        logger.info(f"Processing {len(items_to_process)} items for entity: {entity.name}")
        tasks = [asyncio.create_task(self._scrape_url_task(item, entity, semaphore)) for item in items_to_process]
        results_nested = await asyncio.gather(*tasks)

        # Flatten the list of lists into a single list of results
        self.data_store[entity.name] = [item for sublist in results_nested for item in sublist]
        logger.info(f"Finished entity: {entity.name}. Found {len(self.data_store[entity.name])} total items.")

    async def _scrape_url_task(self, item: Dict[str, Any], entity: Entity, semaphore: asyncio.Semaphore) -> List[
        Dict[str, Any]]:
        """
        A single scraping task. It handles one URL, but that URL might have multiple pages
        if pagination is configured for the entity.
        """
        async with semaphore:
            if self.error_count >= self.config.runtime.stop_after_n_errors:
                return []

            page = await self.browser_manager.new_page(self.config.auth.session_file)
            all_results_for_task = []
            current_url = item["url"]
            initial_data = {k: v for k, v in item.items() if k != "url"}
            pages_scraped_in_task = 0

            try:
                # This loop handles pagination within a single task.
                while current_url:
                    if entity.paginate and entity.paginate.max_pages and pages_scraped_in_task >= entity.paginate.max_pages:
                        logger.info(f"Reached max_pages limit for {current_url}")
                        break

                    rows_on_page, next_page_url = await self._scrape_page(page, current_url, entity, initial_data)
                    all_results_for_task.extend(rows_on_page)
                    pages_scraped_in_task += 1

                    # Decide if we should continue to the next page
                    if entity.paginate and entity.paginate.type == "next_button":
                        current_url = next_page_url
                        if current_url:
                            await asyncio.sleep(self.config.runtime.sleep_ms_between_pages / 1000)
                    else:
                        # If no pagination or not 'next_button' type, stop looping.
                        break

            except Exception as e:
                logger.error(f"Error in scrape task for URL {item['url']}: {e}")
                self.errors.append({"url": item['url'], "entity": entity.name, "error": str(e)})
                self.error_count += 1
            finally:
                if page and not page.is_closed():
                    # Close the entire browser context to free up resources
                    await page.context.close()

            return all_results_for_task

    async def _scrape_page(self, page: Page, url: str, entity: Entity, initial_data: Dict[str, Any]) -> (
    List[Dict[str, Any]], Optional[str]):
        """Scrapes a single page and returns its data and the URL of the next page, if any."""
        logger.info(f"Scraping page: {url}")
        try:
            start_time = time.time()
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_selector(entity.row_selector, timeout=15000)
            self.extraction_times.append(time.time() - start_time)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout waiting for selector '{entity.row_selector}' on {url}")
            return [], None

        content = await page.content()
        soup = BeautifulSoup(content, "lxml")
        rows = soup.select(entity.row_selector)
        if not rows:
            logger.warning(f"Row selector '{entity.row_selector}' found no matches on {url}")

        # Extract data from all rows found on the page
        row_data = [self._extract_data_from_row(row, entity.fields, initial_data) for row in rows]

        # Find the URL for the next page
        next_page_url = None
        if entity.paginate and entity.paginate.type == "next_button" and entity.paginate.selector:
            next_link_element = soup.select_one(entity.paginate.selector)
            if next_link_element and next_link_element.get("href"):
                next_page_url = urljoin(self.config.site.base_url, next_link_element["href"])

        return row_data, next_page_url

    def _extract_data_from_row(self, soup: Tag, fields: Dict[str, str], initial_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extracts fields from a single row element (BeautifulSoup Tag)."""
        row_data = initial_data.copy()
        for field_name, selector_str in fields.items():
            try:
                parts = selector_str.split('@')
                selector = parts[0]
                attribute = parts[1] if len(parts) > 1 else None
                element = soup.select_one(selector)

                if element:
                    if attribute:
                        value = element.get(attribute)
                        row_data[field_name] = value.strip() if value else None
                    else:
                        row_data[field_name] = element.get_text(strip=True)
                else:
                    row_data[field_name] = None
            except Exception as e:
                row_data[field_name] = None
                self.errors.append({"field": field_name, "selector": selector_str, "error": str(e)})
        return row_data

    def _save_output(self):
        """Saves the final data to the specified formats."""
        output_config = self.config.output
        output_dir = Path(output_config.dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self.config.module.entities:
            logger.warning("No entities defined in config.")
            return

        final_entity_name = self.config.module.entities[-1].name
        final_data = self.data_store.get(final_entity_name)
        if not final_data:
            logger.warning(f"No final data was produced for entity '{final_entity_name}' to save.")
            return

        df = pd.DataFrame(final_data)
        if output_config.primary_key:
            pk_list = [key for key in output_config.primary_key if key in df.columns]
            if pk_list:
                df.drop_duplicates(subset=pk_list, keep='first', inplace=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        commit_hash = get_git_commit_hash()
        base_filename = f"{self.config.site.name}_{self.config.module.name}_{final_entity_name}_{timestamp}_{commit_hash}"

        for format_str in output_config.formats:
            file_path = output_dir / f"{base_filename}.{format_str.lower()}"
            try:
                if format_str.lower() == 'csv':
                    df.to_csv(file_path, index=False, encoding='utf-8')
                elif format_str.lower() == 'json':
                    df.to_json(file_path, orient="records", indent=4)
                elif format_str.lower() == 'xlsx':
                    df.to_excel(file_path, index=False)
                logger.info(f"Successfully saved output to {file_path}")
            except Exception as e:
                logger.error(f"Failed to save output to {format_str}: {e}")