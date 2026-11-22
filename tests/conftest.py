"""Shared pytest fixtures for Nexora unit and integration test suites."""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from models.workflow import Workflow
from models.workflow_step import WorkflowStep
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager
from storage.profile_manager import ProfileManager


@pytest.fixture()
def isolated_workspace(tmp_path: Path) -> dict[str, Path]:
    """Provide isolated temporary directories mirroring Nexora's runtime storage layout."""
    paths = {
        "root": tmp_path,
        "profiles": tmp_path / "profiles",
        "exports": tmp_path / "exports",
        "logs": tmp_path / "logs",
        "screenshots": tmp_path / "screenshots",
        "downloads": tmp_path / "downloads",
    }
    for folder in paths.values():
        folder.mkdir(parents=True, exist_ok=True)
    return paths


@pytest.fixture()
def profile_manager(isolated_workspace: dict[str, Path]) -> ProfileManager:
    """Return a `ProfileManager` backed by an isolated temporary profiles directory."""
    return ProfileManager(
        profiles_dir=isolated_workspace["profiles"],
        sample_workflows_path=PROJECT_ROOT / "data" / "sample_workflows.json",
        demo_dir=PROJECT_ROOT / "demo_site",
    )


@pytest.fixture()
def csv_manager(isolated_workspace: dict[str, Path]) -> CSVManager:
    """Return a `CSVManager` writing exports to an isolated temporary folder."""
    return CSVManager(exports_dir=isolated_workspace["exports"])


@pytest.fixture()
def log_manager(isolated_workspace: dict[str, Path]) -> LogManager:
    """Return a `LogManager` saving JSON run records to an isolated temporary folder."""
    return LogManager(logs_dir=isolated_workspace["logs"])


@pytest.fixture()
def sample_workflow() -> Workflow:
    """Return a deterministic multi-step workflow suitable for unit testing."""
    return Workflow(
        name="Sample Intake Automation",
        description="Test workflow covering navigation, input, click, and extraction.",
        target_url="https://example.com/intake",
        steps=[
            WorkflowStep(
                name="Open Intake Page",
                action_type=config.ACTION_OPEN_URL,
                input_value="https://example.com/intake",
            ),
            WorkflowStep(
                name="Fill Client Name",
                action_type=config.ACTION_ENTER_TEXT,
                selector_strategy="id",
                selector_value="full-name",
                csv_column="full_name",
            ),
            WorkflowStep(
                name="Submit Form",
                action_type=config.ACTION_CLICK_ELEMENT,
                selector_strategy="id",
                selector_value="submit-btn",
            ),
            WorkflowStep(
                name="Extract Confirmation",
                action_type=config.ACTION_EXTRACT_TEXT,
                selector_strategy="id",
                selector_value="status-badge",
                output_key="confirmation_text",
            ),
        ],
    )


@pytest.fixture()
def mock_webdriver() -> MagicMock:
    """Return a lightweight mocked Selenium WebDriver instance."""
    driver = MagicMock()
    driver.title = "Nexora Test Page"
    driver.current_url = "https://example.com/intake"
    driver.execute_script.return_value = "complete"
    driver.find_elements.return_value = []
    driver.save_screenshot.return_value = True
    return driver