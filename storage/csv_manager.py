"""CSV dataset loading, validation, incremental logging, and result export management."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

import config

_SAFE_FILENAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_DEFAULT_EXPORTS_DIR: Path = getattr(
    config,
    "EXPORTS_DIR",
    getattr(config, "DATA_DIR", Path(__file__).resolve().parent.parent / "data") / "exports",
)


def _slugify(name: str, fallback: str = "export") -> str:
    """Convert an arbitrary label into a filesystem-safe filename prefix."""
    cleaned = _SAFE_FILENAME_PATTERN.sub("_", name.strip().lower()).strip("_")
    return cleaned[:48] or fallback


def _serialize_cell(value: Any) -> str:
    """Normalize arbitrary Python values into clean CSV cell strings."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _infer_fieldnames(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Build an ordered union of column names across all records."""
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            col = str(key).strip()
            if col and col not in seen:
                seen.add(col)
                ordered.append(col)
    return ordered


class CSVManager:
    """Handles reading input CSV datasets and exporting workflow execution records."""

    def __init__(self, exports_dir: Path | str | None = None) -> None:
        self.exports_dir: Path = Path(exports_dir) if exports_dir else Path(_DEFAULT_EXPORTS_DIR)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _detect_dialect(sample: str) -> type[csv.Dialect] | csv.Dialect:
        """Sniff CSV delimiter from a text sample, falling back to standard comma-separated."""
        if not sample.strip():
            return csv.excel
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            return csv.excel

    def load_csv(
        self,
        file_path: Path | str,
        encoding: str = "utf-8-sig",
        skip_empty_rows: bool = True,
    ) -> tuple[list[str], list[dict[str, str]]]:
        """Load headers and rows from a CSV file as cleaned dictionaries."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        if not path.is_file():
            raise ValueError(f"Expected a file path, got directory: {path}")

        with path.open("r", encoding=encoding, newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            dialect = self._detect_dialect(sample)
            reader = csv.DictReader(handle, dialect=dialect)

            raw_headers = reader.fieldnames or []
            headers = [h.strip() for h in raw_headers if h is not None and h.strip()]
            if not headers:
                return [], []

            rows: list[dict[str, str]] = []
            for raw_row in reader:
                cleaned_row: dict[str, str] = {}
                for header in headers:
                    raw_val = raw_row.get(header, "")
                    cleaned_row[header] = raw_val.strip() if isinstance(raw_val, str) else ""

                if skip_empty_rows and not any(cleaned_row.values()):
                    continue
                rows.append(cleaned_row)

        return headers, rows

    def read_rows(self, file_path: Path | str, encoding: str = "utf-8-sig") -> list[dict[str, str]]:
        """Return only the data rows from a CSV file."""
        _, rows = self.load_csv(file_path=file_path, encoding=encoding)
        return rows

    def get_headers(self, file_path: Path | str, encoding: str = "utf-8-sig") -> list[str]:
        """Return the cleaned column headers of a CSV file."""
        headers, _ = self.load_csv(file_path=file_path, encoding=encoding)
        return headers

    def preview_csv(
        self,
        file_path: Path | str,
        limit: int = 10,
        encoding: str = "utf-8-sig",
    ) -> tuple[list[str], list[dict[str, str]], int]:
        """Return `(headers, sample_rows, total_row_count)` for UI dataset previews."""
        headers, rows = self.load_csv(file_path=file_path, encoding=encoding)
        safe_limit = max(0, limit)
        return headers, rows[:safe_limit], len(rows)

    def validate_columns(
        self,
        file_path: Path | str,
        required_columns: Sequence[str],
        encoding: str = "utf-8-sig",
    ) -> list[str]:
        """Return a list of required column names missing from the target CSV file."""
        headers = set(self.get_headers(file_path=file_path, encoding=encoding))
        return [col for col in required_columns if col.strip() and col.strip() not in headers]

    def build_export_path(
        self,
        prefix: str = "nexora_export",
        include_timestamp: bool = True,
    ) -> Path:
        """Construct a destination path inside `exports_dir`."""
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify(prefix, fallback="nexora_export")
        if include_timestamp:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{slug}_{stamp}.csv"
        else:
            filename = f"{slug}.csv"
        return self.exports_dir / filename

    def export_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        destination_path: Path | str | None = None,
        fieldnames: Sequence[str] | None = None,
        prefix: str = "nexora_export",
        include_timestamp: bool = True,
        encoding: str = "utf-8",
    ) -> Path:
        """Write a sequence of record dictionaries to a CSV file and return its path."""
        resolved_fields = (
            [str(col).strip() for col in fieldnames if str(col).strip()]
            if fieldnames is not None
            else _infer_fieldnames(rows)
        )
        if not resolved_fields:
            raise ValueError("Cannot export CSV: no columns or rows were provided.")

        target = (
            Path(destination_path)
            if destination_path is not None
            else self.build_export_path(prefix=prefix, include_timestamp=include_timestamp)
        )
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=resolved_fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                serialized = {col: _serialize_cell(row.get(col, "")) for col in resolved_fields}
                writer.writerow(serialized)

        return target

    def export_run_results(
        self,
        workflow_name: str,
        records: Sequence[Mapping[str, Any]],
        destination_path: Path | str | None = None,
        fieldnames: Sequence[str] | None = None,
    ) -> Path:
        """Export extracted data or step logs from a workflow execution."""
        return self.export_rows(
            rows=records,
            destination_path=destination_path,
            fieldnames=fieldnames,
            prefix=f"{workflow_name}_results",
            include_timestamp=True,
        )

    def append_row(
        self,
        file_path: Path | str,
        row: Mapping[str, Any],
        fieldnames: Sequence[str] | None = None,
        encoding: str = "utf-8",
    ) -> Path:
        """Append a single record to a CSV file, writing headers if the file is new or empty."""
        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_exists_with_data = target.exists() and target.stat().st_size > 0

        if file_exists_with_data:
            existing_headers = self.get_headers(target, encoding="utf-8-sig")
            resolved_fields = existing_headers or _infer_fieldnames([row])
        else:
            resolved_fields = (
                [str(col).strip() for col in fieldnames if str(col).strip()]
                if fieldnames is not None
                else _infer_fieldnames([row])
            )

        if not resolved_fields:
            raise ValueError("Cannot append CSV row: no column names could be determined.")

        mode = "a" if file_exists_with_data else "w"
        with target.open(mode, encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=resolved_fields, extrasaction="ignore")
            if not file_exists_with_data:
                writer.writeheader()
            serialized = {col: _serialize_cell(row.get(col, "")) for col in resolved_fields}
            writer.writerow(serialized)

        return target

    def create_template_csv(
        self,
        destination_path: Path | str,
        headers: Sequence[str],
        sample_rows: Sequence[Mapping[str, Any]] | None = None,
        encoding: str = "utf-8",
    ) -> Path:
        """Generate a starter input CSV template with headers and optional example rows."""
        cleaned_headers = [str(h).strip() for h in headers if str(h).strip()]
        if not cleaned_headers:
            raise ValueError("Template CSV requires at least one non-empty column header.")

        target = Path(destination_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=cleaned_headers, extrasaction="ignore")
            writer.writeheader()
            for row in sample_rows or []:
                serialized = {col: _serialize_cell(row.get(col, "")) for col in cleaned_headers}
                writer.writerow(serialized)

        return target

    def list_exports(self) -> list[Path]:
        """Return all CSV files in `exports_dir`, sorted most recent first."""
        if not self.exports_dir.exists():
            return []
        files = [p for p in self.exports_dir.glob("*.csv") if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return files

    def delete_export(self, file_path: Path | str) -> bool:
        """Delete a CSV file if it exists. Returns True when removed."""
        target = Path(file_path)
        if target.exists() and target.is_file():
            target.unlink()
            return True
        return False