# main.py (REVISED)

import asyncio
import logging
from pathlib import Path
from datetime import datetime
import yaml
import typer
from pydantic import ValidationError

# --- Local Imports ---
from web_extractor.config.models import JobConfig
from web_extractor.core.browser_manager import BrowserManager
from web_extractor.core.scraper import ScraperEngine
from web_extractor.utils.reporting import ReportGenerator

# --- Basic Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- CLI Application using Typer ---
app = typer.Typer()


async def run_scrape(config: JobConfig, headless: bool):
    """
    Initializes and runs the scraper engine, then generates reports.
    (This function does not need any changes)
    """
    start_time = datetime.now()
    logger.info("Async scrape run started.")
    engine = None

    try:
        async with BrowserManager(user_agent=config.runtime.user_agent, headless=headless) as browser_manager:
            engine = ScraperEngine(config, browser_manager)
            await engine.run()
    except Exception as e:
        logger.error(f"An unexpected error occurred during the scraping process: {e}", exc_info=True)
    finally:
        if engine:
            logger.info("Generating reports...")
            try:
                report_gen = ReportGenerator(
                    job_name=f"{config.site.name}_{config.module.name}",
                    all_results=engine.data_store,
                    errors=engine.errors,
                    extraction_times=engine.extraction_times,
                    start_time=start_time,
                    p95_target=config.reporting.p95_target_seconds,
                )
                report_gen.generate_all_reports()
            except Exception as report_e:
                logger.error(f"Failed to generate reports: {report_e}", exc_info=True)

        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Async scrape run finished in {total_duration:.2f}s.")


@app.command()
def run(
        job_name: str = typer.Argument(
            ..., help="The job name, which corresponds to the '[job_name].yml' config file."
        ),
        headless: bool = typer.Option(
            True, "--headless/--no-headless", help="Run browser in headless or headed mode."
        ),
):
    """
    Runs the web extractor by dynamically finding the job's .yml file in the 'configs/' directory.
    """
    logger.info(f"Initiating job: {job_name}")

    # --- 1. Dynamically construct the config file path ---
    # This assumes you run the script from your project's root directory.
    config_path = Path(f"configs/{job_name}.yaml")
    logger.info(f"Attempting to load configuration from: {config_path}")

    if not config_path.exists():
        logger.error(f"Configuration file not found. Please ensure '{config_path}' exists.")
        raise typer.Exit(code=1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            # --- 2. Load the entire file as the job config ---
            # We no longer look for a job key; the whole file is the configuration.
            job_config_dict = yaml.safe_load(f)

        if not job_config_dict:
            logger.error(f"Config file '{config_path}' is empty or invalid.")
            raise typer.Exit(code=1)

        config = JobConfig(**job_config_dict)

    except (yaml.YAMLError, ValidationError) as e:
        logger.error(f"Error loading or validating config for job '{job_name}':\n{e}")
        raise typer.Exit(code=1)

    asyncio.run(run_scrape(config, headless))
    logger.info(f"Job '{job_name}' completed.")


if __name__ == "__main__":
    app()
