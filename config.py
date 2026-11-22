"""Centralized configuration, filesystem paths, and domain constants for Nexora."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

# Application Metadata
APP_NAME: str = "Nexora"
APP_TAGLINE: str = "Configurable Browser Workflow Automation Studio"
APP_VERSION: str = "1.0.0"

# Root and Subdirectory Paths (anchored to Nexora/)
BASE_DIR: Path = Path(__file__).resolve().parent

WORKFLOWS_DIR: Path = BASE_DIR / "workflows"
PROFILES_DIR: Path = WORKFLOWS_DIR / "profiles"
SAMPLE_WORKFLOWS_PATH: Path = WORKFLOWS_DIR / "sample_workflows.json"

DATA_DIR: Path = BASE_DIR / "data"
EXPORTS_DIR: Path = DATA_DIR / "exports"
DOWNLOADS_DIR: Path = DATA_DIR / "downloads"
SCREENSHOTS_DIR: Path = DATA_DIR / "screenshots"
DB_PATH: Path = DATA_DIR / "nexora.db"
HISTORY_CSV_PATH: Path = DATA_DIR / "execution_history.csv"
SAMPLE_CSV_PATH: Path = DATA_DIR / "sample_contacts.csv"

DEMO_SITE_DIR: Path = BASE_DIR / "demo_site"

MANAGED_DIRECTORIES: tuple[Path, ...] = (
    WORKFLOWS_DIR,
    PROFILES_DIR,
    DATA_DIR,
    EXPORTS_DIR,
    DOWNLOADS_DIR,
    SCREENSHOTS_DIR,
    DEMO_SITE_DIR,
)

# Browser Settings
SUPPORTED_BROWSERS: tuple[str, ...] = ("chrome", "edge")
DEFAULT_BROWSER: str = "chrome"
DEFAULT_HEADLESS: bool = False

# Element Selector Strategies
SELECTOR_STRATEGIES: tuple[str, ...] = ("id", "name", "css", "xpath")
SELECTOR_STRATEGY_LABELS: dict[str, str] = {
    "id": "Element ID",
    "name": "Element Name",
    "css": "CSS Selector",
    "xpath": "XPath Selector",
}

# Supported Browser Actions
ACTION_OPEN_URL: str = "open_url"
ACTION_CLICK_ELEMENT: str = "click_element"
ACTION_ENTER_TEXT: str = "enter_text"
ACTION_SELECT_OPTION: str = "select_option"
ACTION_SCROLL: str = "scroll"
ACTION_WAIT: str = "wait"
ACTION_EXTRACT_TEXT: str = "extract_text"
ACTION_EXTRACT_LINKS: str = "extract_links"
ACTION_DOWNLOAD_FILE: str = "download_file"
ACTION_NAVIGATE_BACK: str = "navigate_back"
ACTION_NAVIGATE_FORWARD: str = "navigate_forward"

SUPPORTED_ACTIONS: tuple[str, ...] = (
    ACTION_OPEN_URL,
    ACTION_CLICK_ELEMENT,
    ACTION_ENTER_TEXT,
    ACTION_SELECT_OPTION,
    ACTION_SCROLL,
    ACTION_WAIT,
    ACTION_EXTRACT_TEXT,
    ACTION_EXTRACT_LINKS,
    ACTION_DOWNLOAD_FILE,
    ACTION_NAVIGATE_BACK,
    ACTION_NAVIGATE_FORWARD,
)

ACTION_LABELS: dict[str, str] = {
    ACTION_OPEN_URL: "Open URL",
    ACTION_CLICK_ELEMENT: "Click Element",
    ACTION_ENTER_TEXT: "Enter Text",
    ACTION_SELECT_OPTION: "Select Option",
    ACTION_SCROLL: "Scroll Page",
    ACTION_WAIT: "Wait for Condition",
    ACTION_EXTRACT_TEXT: "Extract Text / Table",
    ACTION_EXTRACT_LINKS: "Extract Links",
    ACTION_DOWNLOAD_FILE: "Download & Verify File",
    ACTION_NAVIGATE_BACK: "Navigate Back",
    ACTION_NAVIGATE_FORWARD: "Navigate Forward",
}

ACTIONS_REQUIRING_SELECTOR: frozenset[str] = frozenset(
    {
        ACTION_CLICK_ELEMENT,
        ACTION_ENTER_TEXT,
        ACTION_SELECT_OPTION,
        ACTION_EXTRACT_TEXT,
        ACTION_DOWNLOAD_FILE,
    }
)

ACTIONS_REQUIRING_VALUE: frozenset[str] = frozenset(
    {
        ACTION_OPEN_URL,
        ACTION_SELECT_OPTION,
    }
)

HIGH_RISK_ACTIONS: frozenset[str] = frozenset(
    {
        ACTION_CLICK_ELEMENT,
        ACTION_DOWNLOAD_FILE,
    }
)

# Condition-Based Wait Modes
WAIT_CONDITIONS: tuple[str, ...] = (
    "present",
    "visible",
    "clickable",
    "invisible",
    "text_present",
    "url_contains",
)
DEFAULT_WAIT_CONDITION: str = "visible"

# Scroll & Select Modes
SCROLL_MODES: tuple[str, ...] = ("bottom", "top", "by_pixels", "to_element")
DEFAULT_SCROLL_MODE: str = "bottom"

SELECT_MODES: tuple[str, ...] = ("visible_text", "value", "index")
DEFAULT_SELECT_MODE: str = "visible_text"

# Step Conditional Execution Rules
CONDITION_ALWAYS: str = "always"
CONDITION_IF_ELEMENT_EXISTS: str = "if_element_exists"
CONDITION_SKIP_IF_MISSING: str = "skip_if_missing"
CONDITION_STOP_IF_MISSING: str = "stop_if_missing"
CONDITION_IF_TEXT_PRESENT: str = "if_text_present"

STEP_CONDITIONS: tuple[str, ...] = (
    CONDITION_ALWAYS,
    CONDITION_IF_ELEMENT_EXISTS,
    CONDITION_SKIP_IF_MISSING,
    CONDITION_STOP_IF_MISSING,
    CONDITION_IF_TEXT_PRESENT,
)

STEP_CONDITION_LABELS: dict[str, str] = {
    CONDITION_ALWAYS: "Always Execute",
    CONDITION_IF_ELEMENT_EXISTS: "Execute Only If Element Exists",
    CONDITION_SKIP_IF_MISSING: "Skip Step If Element Missing",
    CONDITION_STOP_IF_MISSING: "Stop Workflow If Element Missing",
    CONDITION_IF_TEXT_PRESENT: "Execute Only If Text Is Present",
}

# Timeouts, Retries & Download Polling Bounds
DEFAULT_TIMEOUT: float = 10.0
MIN_TIMEOUT: float = 1.0
MAX_TIMEOUT: float = 120.0

DEFAULT_MAX_RETRIES: int = 1
MIN_RETRIES: int = 0
MAX_RETRIES: int = 5
RETRY_BACKOFF_SECONDS: float = 0.75

DOWNLOAD_POLL_INTERVAL: float = 0.5
TEMP_DOWNLOAD_EXTENSIONS: tuple[str, ...] = (".crdownload", ".tmp", ".part")

# Execution & Step Status Constants
RUN_STATUS_SUCCESS: str = "Success"
RUN_STATUS_PARTIAL: str = "Partial"
RUN_STATUS_FAILED: str = "Failed"
RUN_STATUS_STOPPED: str = "Stopped"

STEP_STATUS_SUCCESS: str = "Success"
STEP_STATUS_FAILED: str = "Failed"
STEP_STATUS_SKIPPED: str = "Skipped"
STEP_STATUS_REJECTED: str = "Rejected"

# CSV Execution History Schema
EXECUTION_HISTORY_HEADERS: tuple[str, ...] = (
    "execution_id",
    "workflow_name",
    "start_time",
    "end_time",
    "total_actions",
    "successful_actions",
    "failed_actions",
    "status",
)


def ensure_directories(extra_dirs: Iterable[Path] | None = None) -> None:
    """Create all managed Nexora runtime directories if they do not exist."""
    targets = list(MANAGED_DIRECTORIES)
    if extra_dirs:
        targets.extend(extra_dirs)
    for directory in targets:
        directory.mkdir(parents=True, exist_ok=True)


def get_demo_url(page_filename: str = "index.html") -> str:
    """Return a cross-platform file:// URI pointing to a page in Nexora/demo_site/."""
    target_path = (DEMO_SITE_DIR / page_filename).resolve()
    return target_path.as_uri()