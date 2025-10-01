import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd
from datetime import datetime
import uuid
import git

logger = logging.getLogger(__name__)


def get_git_commit_hash() -> str:
    """Gets the short hash of the current git commit."""
    try:
        repo = git.Repo(search_parent_directories=True)
        return repo.head.object.hexsha[:7]
    except (git.InvalidGitRepositoryError, ValueError):
        return "nogit"


class NumpyJSONEncoder(json.JSONEncoder):
    """A custom JSON encoder to handle NumPy-specific data types."""

    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super(NumpyJSONEncoder, self).default(obj)


class ReportGenerator:
    def __init__(self, job_name: str, all_results: Dict[str, List[Dict[str, Any]]], errors: List[Dict[str, Any]],
                 extraction_times: List[float], start_time: datetime, p95_target: Optional[int] = None):
        self.job_name = job_name
        self.all_results = all_results
        self.errors = errors
        self.extraction_times = extraction_times
        self.start_time = start_time
        self.end_time = datetime.now()
        self.p95_target = p95_target
        self.run_id = f"{self.start_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.reports_dir = Path("./reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_all_reports(self):
        """Generates all the final report files."""
        self._generate_run_metrics_json()
        self._generate_error_report_csv()
        self._generate_run_summary_md()
        logger.info(f"All reports generated in: {self.reports_dir}")

    def _generate_run_metrics_json(self):
        """Generates a single, comprehensive run_metrics.json file."""
        if not self.extraction_times:
            p50, p95, avg_time, total_duration = 0, 0, 0, 0
        else:
            p50 = round(np.percentile(self.extraction_times, 50), 2)
            p95 = round(np.percentile(self.extraction_times, 95), 2)
            avg_time = round(np.mean(self.extraction_times), 2)
            total_duration = round(sum(self.extraction_times), 2)

        errors_by_type = {}
        if self.errors:
            df_errors = pd.DataFrame(self.errors)
            # Use 'error' column if it exists, otherwise use 'exception'
            error_col = 'error' if 'error' in df_errors.columns else 'exception'
            if error_col in df_errors.columns:
                errors_by_type = df_errors.groupby(error_col).size().to_dict()

        metrics_data = {
            "run_id": self.run_id,
            "job_name": self.job_name,
            "git_commit": get_git_commit_hash(),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": round((self.end_time - self.start_time).total_seconds(), 2),
            "pages_total": len(self.extraction_times),
            "items_total": sum(len(data) for data in self.all_results.values()),
            "p50_seconds": p50,
            "p95_seconds": p95,
            "errors_total": len(self.errors),
            "errors_by_type": errors_by_type,
        }

        if self.p95_target:
            metrics_data["target_p95_seconds"] = self.p95_target
            metrics_data["target_met"] = p95 <= self.p95_target

        report_path = self.reports_dir / "run_metrics.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(metrics_data, f, indent=4, cls=NumpyJSONEncoder)

    def _generate_error_report_csv(self):
        """Generates errors.csv with details on each failure."""
        if not self.errors:
            logger.info("No errors to report.");
            return

        df = pd.DataFrame(self.errors)
        possible_columns = ["url", "entity", "selector", "exception", "retries", "stage", "error", "field"]
        df = df.reindex(columns=[col for col in possible_columns if col in df.columns])
        report_path = self.reports_dir / "errors.csv"
        df.to_csv(report_path, index=False)

    def _generate_run_summary_md(self):
        """Generates a markdown summary of the run."""
        p95 = round(np.percentile(self.extraction_times, 95), 2) if self.extraction_times else 0
        total_items = sum(len(data) for data in self.all_results.values())

        summary_content = f"""
# Run Summary: {self.job_name}

- **Run ID:** `{self.run_id}`
- **Git Commit:** `{get_git_commit_hash()}`
- **Start Time:** `{self.start_time.isoformat()}`
- **End Time:** `{self.end_time.isoformat()}`
- **Total Duration:** `{round((self.end_time - self.start_time).total_seconds(), 2)} seconds`
- **Total Items Scraped:** `{total_items}`
- **Total Errors:** `{len(self.errors)}`
- **p95 Page Load Time:** `{p95} seconds`
"""
        if self.p95_target:
            summary_content += f"- **Target p95 (s):** {self.p95_target} → {'✅ Met' if p95 <= self.p95_target else '❌ Not Met'}\n"

        if self.errors:
            summary_content += "\n## Top Errors:\n"
            error_col = 'error' if 'error' in pd.DataFrame(self.errors).columns else 'exception'
            error_summary = pd.DataFrame(self.errors).groupby(error_col).size().nlargest(5)
            for error_msg, count in error_summary.items():
                summary_content += f"- `{error_msg}`: {count} times\n"

        report_path = self.reports_dir / "run_summary.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(summary_content.strip())