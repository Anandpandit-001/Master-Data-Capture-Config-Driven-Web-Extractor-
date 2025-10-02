from pydantic import BaseModel, Field
from typing import Dict, List, Optional


class SiteConfig(BaseModel):
    name: str
    base_url: str

class AuthConfig(BaseModel):
    session_file: Optional[str] = Field(None, description="Path to a session file for authentication.")

class RuntimeConfig(BaseModel):
    sleep_ms_between_pages: int = 500
    concurrency: int = 2
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/108.0.0.0 Safari/537.36"
    )
    stop_after_n_errors: int = 50

class PaginateConfig(BaseModel):
    """Defines how to navigate through multiple pages for a single entity."""
    type: str  # Currently supports 'next_button'
    selector: Optional[str] = Field(None, description="CSS selector for the 'next' button or link.")
    max_pages: Optional[int] = Field(None, description="An optional limit on how many pages to scrape.")

class Entity(BaseModel):
    """
    Defines a data structure to be scraped. A job can have multiple entities
    that depend on each other (e.g., scrape a ProductList, then ProductDetail).
    """
    name: str = Field(..., description="Unique name for the entity, e.g., 'ProductList'.")
    url: Optional[str] = Field(None, description="The starting URL to scrape for this entity.")
    follow_from: Optional[str] = Field(None, description="The source of URLs from a previous entity, e.g., 'ProductList.detail_url'.")
    paginate: Optional[PaginateConfig] = Field(None, description="Pagination rules for this entity, if any.")
    row_selector: str = Field(..., description="CSS selector for the main container of each item.")
    fields: Dict[str, str] = Field(..., description="A dictionary of field names and their CSS selectors.")



class ModuleConfig(BaseModel):
    name: str
    entities: List[Entity]
class OutputConfig(BaseModel):
    dir: str = "./output"
    formats: List[str] = ["csv", "json"]
    primary_key: Optional[List[str]] = Field(None, description="List of columns to use for removing duplicates.")

class ReportingConfig(BaseModel):
    p95_target_seconds: Optional[int] = None

class JobConfig(BaseModel):
    """The complete, top-level configuration for a single scraping job file."""
    site: SiteConfig
    auth: AuthConfig = Field(default_factory=AuthConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    module: ModuleConfig
    output: OutputConfig = Field(default_factory=OutputConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)