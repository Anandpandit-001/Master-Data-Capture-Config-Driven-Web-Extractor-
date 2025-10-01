import logging
import asyncio
from pathlib import Path
import yaml
import typer
import nest_asyncio
from typing import Dict, List, Optional, Any, Union
# Use the new V2 configuration model
from .config.models import JobConfig
from .core.browser_manager import BrowserManager
from .core.scraper import ScraperEngine
from .utils.logging_config import setup_logging
from .utils.reporting import ReportGenerator
from datetime import datetime

nest_asyncio.apply()
app = typer.Typer()
logger = logging.getLogger(__name__)

def load_job_config(job_name: str) -> JobConfig:
    """Loads and validates the V2 YAML configuration file for a job."""
    config_path = Path(f"jobs/{job_name}.yml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file '{config_path}' not found.")
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    # Return an instance of the new JobConfig model
    return JobConfig(**data)

@app.command()
def run(
    job_name: str = typer.Argument(..., help="Base name of the job's YAML file in the 'jobs/' folder."),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode."),
):
    """Runs a V2 multi-entity web scraping job."""
    setup_logging()
    logger.info(f"Initiating job: {job_name}")
    try:
        config = load_job_config(job_name)
    except Exception as e:
        logger.error(f"Failed to load or validate configuration: {e}", exc_info=True)
        raise typer.Exit(code=1)

    asyncio.run(run_scrape(config, headless))
    logger.info(f"Job '{job_name}' completed.")


async def run_scrape(config: JobConfig, headless: bool):
    """Initializes and runs the V2 scraper engine and generates reports."""

    # 1. Capture the start time before the scrape begins
    start_time = datetime.now()
    engine = None

    async with BrowserManager(user_agent=config.runtime.user_agent, headless=headless) as browser_manager:
        engine = ScraperEngine(config, browser_manager)
        await engine.run()

    # 2. Generate the reports after the scrape is done
    if engine:
        report_gen = ReportGenerator(
            job_name=config.site.name,
            all_results=engine.data_store,
            errors=engine.errors,
            extraction_times=engine.extraction_times,
            start_time=start_time,  # 3. Pass the start_time to the reporter
            p95_target=config.reporting.p95_target_seconds
        )
        report_gen.generate_all_reports()


if __name__ == "__main__":
    app()