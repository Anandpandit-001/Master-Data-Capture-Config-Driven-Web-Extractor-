
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Union
class SiteConfig(BaseModel):
    name: str
    base_url: str

class AuthConfig(BaseModel):
    """Used for session-based auth, can be null for public sites."""
    session_file: Optional[str] = None

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
    param: str
    start: int = 1
    stop_rule: str

class Entity(BaseModel):
    name: str
    url: Optional[str] = None
    follow_from: Optional[str] = None
    paginate: Optional[PaginateConfig] = None
    row_selector: str
    fields: Dict[str, str]

class DiscoveryConfig(BaseModel):
    """Defines rules for the initial URL discovery phase."""
    start_page: str
    link_selector: str
    wait_for_selectors: Optional[List[str]] = Field(
        None, description="A list of selectors to wait for before discovery."
    )
    attribute: Optional[str] = Field(
        None, description="Attribute to extract (defaults to href)."
    )
    extract_regex: Optional[str] = Field(
        None, description="Regex to extract an ID from the attribute."
    )
    url_template: Optional[str] = Field(
        None, description="Template to build the final URL, use {id}."
    )

class ModuleConfig(BaseModel):
    name: str
    discovery: Optional[DiscoveryConfig] = None
    entities: List[Entity]

class OutputConfig(BaseModel):
    dir: str = "./output"
    formats: List[str] = ["csv", "json"]
    primary_key: List[str] = []

class ReportingConfig(BaseModel):
    p95_target_seconds: Optional[int] = None

class JobConfig(BaseModel):
    """The root model for the scraper configuration."""
    site: SiteConfig
    auth: AuthConfig = Field(default_factory=AuthConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    module: ModuleConfig
    output: OutputConfig
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)