import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# --- THIS IS THE NEW HELPER CLASS ---
class NumpyJSONEncoder(json.JSONEncoder):
    """
    A custom JSON encoder to handle NumPy-specific data types.
    This teaches the json library how to convert numpy types to standard python types.
    """

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super(NumpyJSONEncoder, self).default(obj)


class ReportGenerator:
    def __init__(self, job_name: str, all_results: Dict[str, List[Dict[str, Any]]], errors: List[Dict[str, Any]],
                 extraction_times: List[float], p95_target: Optional[int]):
        self.job_name = job_name
        self.all_results = all_results
        self.errors = errors
        self.extraction_times = extraction_times
        self.p95_target = p95_target
        self.output_dir = Path(f"output/{self.job_name}_reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self):
        """Generates all report files."""
        self._generate_runtime_report()
        self._generate_error_report()
        logger.info(f"Performance and error reports generated in: {self.output_dir}")

    def _calculate_p95(self) -> float:
        if not self.extraction_times: return 0.0
        return round(np.percentile(self.extraction_times, 95), 2)

    def _generate_runtime_report(self):
        """Generates a JSON file with a high-level summary and performance metrics."""
        p95_runtime = self._calculate_p95()
        total_items = sum(len(results) for results in self.all_results.values())

        report_data = {
            "job_name": self.job_name,
            "total_items_scraped": total_items,
            "total_errors": len(self.errors),
            "performance_metrics": {
                "p95_extraction_time_seconds": p95_runtime,
                "average_extraction_time_seconds": round(np.mean(self.extraction_times),
                                                         2) if self.extraction_times else 0,
                "total_duration_seconds": round(sum(self.extraction_times), 2)
            }
        }

        if self.p95_target:
            report_data["performance_metrics"]["target_p95_seconds"] = self.p95_target
            report_data["performance_metrics"]["target_met"] = p95_runtime <= self.p95_target

        report_path = self.output_dir / "runtime_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            # --- USE THE NEW CUSTOM ENCODER HERE ---
            json.dump(report_data, f, indent=4, cls=NumpyJSONEncoder)

    def _generate_error_report(self):
        """Generates a CSV file logging all errors encountered during the scrape."""
        if not self.errors:
            logger.info("No errors to report.")
            return

        df = pd.DataFrame(self.errors)
        report_path = self.output_dir / "error_report.csv"
        # Ensure consistent column order
        df = df.reindex(columns=["url", "stage", "error", "field", "selector"])
        df.to_csv(report_path, index=False)
        logger.info(f"Error report with {len(self.errors)} entries saved to {report_path}")