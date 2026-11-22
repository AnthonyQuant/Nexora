"""Built-in workflow templates and sample CSV datasets for Nexora."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config
from models.workflow import Workflow
from models.workflow_step import WorkflowStep

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_DEMO_HTML_PATH: Path = (_PROJECT_ROOT / "demo_site" / "index.html").resolve()
DEMO_PORTAL_URL: str = _DEMO_HTML_PATH.as_uri()


@dataclass(frozen=True)
class WorkflowPreset:
    """Metadata and factory definition for a reusable Nexora workflow template."""

    preset_id: str
    name: str
    category: str
    description: str
    requires_csv: bool
    factory: Callable[[], Workflow]
    sample_csv_headers: list[str] = field(default_factory=list)
    sample_csv_rows: list[dict[str, str]] = field(default_factory=list)

    def build_workflow(self) -> Workflow:
        """Instantiate a fresh, independent `Workflow` copy from this preset."""
        return self.factory()


def _build_demo_single_intake() -> Workflow:
    """Single-record registration flow with conditional banner dismissal and approval gate."""
    return Workflow(
        name="Demo Portal: Client Intake & Verification",
        description=(
            "Opens the local Nexora demo portal, dismisses the notice banner if present, "
            "fills out the client intake form, pauses for approval before submitting, and extracts the confirmation."
        ),
        target_url=DEMO_PORTAL_URL,
        steps=[
            WorkflowStep(
                name="Open Demo Portal",
                action_type=config.ACTION_OPEN_URL,
                input_value=DEMO_PORTAL_URL,
            ),
            WorkflowStep(
                name="Dismiss Notice Banner (If Present)",
                action_type=config.ACTION_CLICK_ELEMENT,
                selector_strategy="id",
                selector_value="close-banner-btn",
                condition=config.CONDITION_SKIP_IF_MISSING,
                condition_target="close-banner-btn",
            ),
            WorkflowStep(
                name="Enter Full Name",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="full-name",
                input_value="Katherine Johnson",
            ),
            WorkflowStep(
                name="Enter Work Email",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="email-address",
                input_value="katherine@orbital.org",
            ),
            WorkflowStep(
                name="Select Department",
                action_type=config.ACTION_SELECT_OPTION,
                selector_strategy="id",
                selector_value="department-select",
                input_value="Research",
                options={"select_mode": "visible_text"},
            ),
            WorkflowStep(
                name="Enter Reference Note",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="notes-input",
                input_value="Trajectory verification lead",
            ),
            WorkflowStep(
                name="Submit Intake Form",
                action_type=config.ACTION_CLICK_ELEMENT,
                selector_strategy="id",
                selector_value="submit-btn",
                requires_approval=True,
            ),
            WorkflowStep(
                name="Wait for Registration Confirmation",
                action_type=getattr(config, "ACTION_WAIT", "wait"),
                selector_strategy="id",
                selector_value="status-badge",
                input_value="Registered NX-",
                options={"wait_condition": "text_present"},
            ),
            WorkflowStep(
                name="Extract Status Confirmation",
                action_type=config.ACTION_EXTRACT_TEXT,
                selector_strategy="id",
                selector_value="status-badge",
                output_key="registration_status",
                options={"field_name": "registration_status"},
            ),
        ],
    )


def _build_demo_csv_batch_intake() -> Workflow:
    """CSV-driven batch onboarding workflow iterating over rows of client records."""
    return Workflow(
        name="Demo Portal: CSV Batch Client Onboarding",
        description=(
            "Iterates over every row in an uploaded CSV dataset (`full_name`, `email`, `department`, `notes`), "
            "registers each client on the demo portal, and extracts confirmation statuses for CSV export."
        ),
        target_url=DEMO_PORTAL_URL,
        steps=[
            WorkflowStep(
                name="Open Demo Portal",
                action_type=config.ACTION_OPEN_URL,
                input_value=DEMO_PORTAL_URL,
            ),
            WorkflowStep(
                name="Dismiss Notice Banner (If Present)",
                action_type=config.ACTION_CLICK_ELEMENT,
                selector_strategy="id",
                selector_value="close-banner-btn",
                condition=config.CONDITION_SKIP_IF_MISSING,
                condition_target="close-banner-btn",
            ),
            WorkflowStep(
                name="Fill Full Name from CSV",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="full-name",
                csv_column="full_name",
            ),
            WorkflowStep(
                name="Fill Work Email from CSV",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="email-address",
                csv_column="email",
            ),
            WorkflowStep(
                name="Select Department from CSV",
                action_type=config.ACTION_SELECT_OPTION,
                selector_strategy="id",
                selector_value="department-select",
                csv_column="department",
                options={"select_mode": "visible_text"},
            ),
            WorkflowStep(
                name="Fill Reference Note from CSV",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="notes-input",
                csv_column="notes",
            ),
            WorkflowStep(
                name="Submit Client Record",
                action_type=config.ACTION_CLICK_ELEMENT,
                selector_strategy="id",
                selector_value="submit-btn",
            ),
            WorkflowStep(
                name="Wait for Registration Confirmation",
                action_type=getattr(config, "ACTION_WAIT", "wait"),
                selector_strategy="id",
                selector_value="status-badge",
                input_value="Registered NX-",
                options={"wait_condition": "text_present"},
            ),
            WorkflowStep(
                name="Capture Registration Receipt",
                action_type=config.ACTION_EXTRACT_TEXT,
                selector_strategy="id",
                selector_value="status-badge",
                output_key="batch_receipt",
                options={"field_name": "registration_receipt"},
            ),
        ],
    )


def _build_demo_report_download() -> Workflow:
    """Automated CSV report download and deterministic file rename workflow."""
    return Workflow(
        name="Demo Portal: Automated CSV Report Download",
        description=(
            "Opens the demo portal, clicks the report download trigger, waits for the browser "
            "download to complete, and saves the file as `nexora_client_directory.csv`."
        ),
        target_url=DEMO_PORTAL_URL,
        steps=[
            WorkflowStep(
                name="Open Demo Portal",
                action_type=config.ACTION_OPEN_URL,
                input_value=DEMO_PORTAL_URL,
            ),
            WorkflowStep(
                name="Download & Rename CSV Report",
                action_type=getattr(config, "ACTION_DOWNLOAD_FILE", "download_file"),
                selector_strategy="id",
                selector_value="download-report-btn",
                input_value="nexora_client_directory.csv",
                output_key="downloaded_report_path",
                options={"expected_extension": ".csv", "overwrite": True},
            ),
        ],
    )


def _build_demo_directory_scraper() -> Workflow:
    """Extracts portal directory links, waits for async status, and scrapes the client table."""
    return Workflow(
        name="Demo Portal: Links, Async Wait & Table Extraction",
        description=(
            "Extracts all hyperlinks in the portal directory, triggers an asynchronous status check, "
            "waits until the async banner becomes visible, and extracts the full client directory table."
        ),
        target_url=DEMO_PORTAL_URL,
        steps=[
            WorkflowStep(
                name="Open Demo Portal",
                action_type=config.ACTION_OPEN_URL,
                input_value=DEMO_PORTAL_URL,
            ),
            WorkflowStep(
                name="Extract Portal Directory Links",
                action_type=config.ACTION_EXTRACT_LINKS,
                selector_strategy="id",
                selector_value="resource-links",
                output_key="directory_links",
            ),
            WorkflowStep(
                name="Trigger Async Status Check",
                action_type=config.ACTION_CLICK_ELEMENT,
                selector_strategy="id",
                selector_value="load-async-btn",
            ),
            WorkflowStep(
                name="Wait for Async Result Banner",
                action_type=getattr(config, "ACTION_WAIT", "wait"),
                selector_strategy="id",
                selector_value="async-result",
                options={"wait_condition": "visible"},
            ),
            WorkflowStep(
                name="Extract Async Status Message",
                action_type=config.ACTION_EXTRACT_TEXT,
                selector_strategy="id",
                selector_value="async-result",
                output_key="async_status",
                options={"field_name": "async_status"},
            ),
            WorkflowStep(
                name="Extract Registered Client Table",
                action_type=getattr(config, "ACTION_EXTRACT_TABLE", "extract_table"),
                selector_strategy="id",
                selector_value="records-table",
                output_key="client_records",
            ),
        ],
    )


def _build_web_page_audit() -> Workflow:
    """General-purpose starter workflow for inspecting a web page's title heading and links."""
    return Workflow(
        name="General Web Page: Heading & Links Audit",
        description=(
            "Navigates to a target URL, extracts the primary `<h1>` heading text, "
            "and collects all unique hyperlinks on the page."
        ),
        target_url="https://example.com",
        steps=[
            WorkflowStep(
                name="Navigate to Target URL",
                action_type=config.ACTION_OPEN_URL,
                input_value="https://example.com",
            ),
            WorkflowStep(
                name="Extract Primary Heading",
                action_type=config.ACTION_EXTRACT_TEXT,
                selector_strategy="css",
                selector_value="h1",
                output_key="page_heading",
                options={"field_name": "page_heading"},
            ),
            WorkflowStep(
                name="Extract All Page Links",
                action_type=config.ACTION_EXTRACT_LINKS,
                output_key="page_links",
            ),
        ],
    )


PRESET_REGISTRY: dict[str, WorkflowPreset] = {
    "demo_single_intake": WorkflowPreset(
        preset_id="demo_single_intake",
        name="Demo Portal: Client Intake & Verification",
        category="Form Automation",
        description="Single-record registration with conditional banner skip and approval gate.",
        requires_csv=False,
        factory=_build_demo_single_intake,
    ),
    "demo_csv_batch_intake": WorkflowPreset(
        preset_id="demo_csv_batch_intake",
        name="Demo Portal: CSV Batch Client Onboarding",
        category="CSV Batch Processing",
        description="Onboards multiple clients from a CSV file and exports registration receipts.",
        requires_csv=True,
        factory=_build_demo_csv_batch_intake,
        sample_csv_headers=["full_name", "email", "department", "notes"],
        sample_csv_rows=[
            {
                "full_name": "Margaret Hamilton",
                "email": "margaret@apollo.org",
                "department": "Engineering",
                "notes": "Flight software director",
            },
            {
                "full_name": "Dorothy Vaughan",
                "email": "dorothy@langley.gov",
                "department": "Operations",
                "notes": "FORTRAN computing lead",
            },
            {
                "full_name": "Mary Jackson",
                "email": "mary@aerospace.org",
                "department": "Research",
                "notes": "Wind tunnel aerodynamics",
            },
        ],
    ),
    "demo_report_download": WorkflowPreset(
        preset_id="demo_report_download",
        name="Demo Portal: Automated CSV Report Download",
        category="File Downloads",
        description="Triggers a browser CSV download, waits for completion, and renames the file.",
        requires_csv=False,
        factory=_build_demo_report_download,
    ),
    "demo_directory_scraper": WorkflowPreset(
        preset_id="demo_directory_scraper",
        name="Demo Portal: Links, Async Wait & Table Extraction",
        category="Data Extraction",
        description="Scrapes directory links, waits on async content, and parses the client table.",
        requires_csv=False,
        factory=_build_demo_directory_scraper,
    ),
    "web_page_audit": WorkflowPreset(
        preset_id="web_page_audit",
        name="General Web Page: Heading & Links Audit",
        category="Data Extraction",
        description="Extracts the primary heading and all unique hyperlinks from any web page.",
        requires_csv=False,
        factory=_build_web_page_audit,
    ),
}


def list_presets() -> list[dict[str, Any]]:
    """Return UI-friendly metadata dictionaries for all registered workflow presets."""
    items: list[dict[str, Any]] = []
    for preset in PRESET_REGISTRY.values():
        wf = preset.build_workflow()
        items.append(
            {
                "preset_id": preset.preset_id,
                "name": preset.name,
                "category": preset.category,
                "description": preset.description,
                "requires_csv": preset.requires_csv,
                "step_count": len(wf.steps),
                "sample_csv_headers": list(preset.sample_csv_headers),
                "sample_csv_rows": [dict(r) for r in preset.sample_csv_rows],
            }
        )
    return items


def get_preset_workflow(preset_id: str) -> Workflow:
    """Return a fresh `Workflow` instance for `preset_id` or raise ValueError if unknown."""
    key = (preset_id or "").strip().lower()
    preset = PRESET_REGISTRY.get(key)
    if preset is None:
        available = ", ".join(PRESET_REGISTRY.keys())
        raise ValueError(f"Unknown workflow preset '{preset_id}'. Available presets: {available}.")
    return preset.build_workflow()


def get_preset_sample_csv(preset_id: str) -> tuple[list[str], list[dict[str, str]]]:
    """Return `(headers, sample_rows)` for a preset (empty lists if not CSV-driven)."""
    key = (preset_id or "").strip().lower()
    preset = PRESET_REGISTRY.get(key)
    if preset is None:
        available = ", ".join(PRESET_REGISTRY.keys())
        raise ValueError(f"Unknown workflow preset '{preset_id}'. Available presets: {available}.")
    return list(preset.sample_csv_headers), [dict(r) for r in preset.sample_csv_rows]