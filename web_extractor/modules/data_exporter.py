import logging
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
import json

logger = logging.getLogger(__name__)

def make_json_serializable(data: Any) -> Any:
    """Recursively convert non-serializable objects to strings for JSON export."""
    if isinstance(data, dict):
        return {k: make_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [make_json_serializable(v) for v in data]
    elif isinstance(data, (str, int, float, bool)) or data is None:
        return data
    else:
        return str(data)

def export_data(data: List[Dict[str, Any]], job_name: str, formats: List[str] = ["csv", "json"]):
    """Exports scraped data to the specified formats safely."""
    if not data:
        logger.warning("No data to export.")
        return

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Ensure all data is JSON-serializable
    safe_data = make_json_serializable(data)
    df = pd.DataFrame(safe_data)

    for fmt in formats:
        file_path = output_dir / f"{job_name}_results.{fmt}"
        try:
            if fmt.lower() == "csv":
                df.to_csv(file_path, index=False)
            elif fmt.lower() == "json":
                df.to_json(file_path, orient="records", indent=4, force_ascii=False)
            elif fmt.lower() == "xlsx":
                df.to_excel(file_path, index=False)
            else:
                logger.error(f"Unsupported export format: {fmt}")
                continue
            logger.info(f"Exported {len(df)} items to {file_path}")
        except Exception as e:
            logger.error(f"Failed to export data to {fmt}: {e}")
