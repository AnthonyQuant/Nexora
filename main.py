"""Unified desktop GUI and CLI entry point for the Nexora Browser Automation Framework."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT: Path = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config
from core.browser_manager import BrowserManager
from core.workflow_engine import WorkflowEngine
from models.workflow import Workflow
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager
from storage.profile_manager import ProfileManager
from workflows import get_preset_workflow, list_presets


def _ensure_workspace_directories() -> None:
    """Create all managed Nexora runtime directories if they do not yet exist."""
    config.ensure_directories()


def _resolve_cli_workflow(
    profile_manager: ProfileManager,
    preset_id: str | None = None,
    workflow_ref: str | None = None,
) -> Workflow:
    """Resolve a target `Workflow` from a preset ID, JSON file path, or saved profile."""
    if preset_id:
        return get_preset_workflow(preset_id)

    if workflow_ref:
        candidate_path = Path(workflow_ref)
        if candidate_path.exists() and candidate_path.is_file():
            return profile_manager.load_workflow_file(candidate_path)

        by_id = profile_manager.get_workflow(workflow_ref)
        if by_id is not None:
            return by_id

        by_name = profile_manager.get_workflow_by_name(workflow_ref)
        if by_name is not None:
            return by_name

        raise FileNotFoundError(
            f"Could not find workflow profile or JSON file matching '{workflow_ref}'."
        )

    raise ValueError("Specify either --preset or --workflow when running in CLI mode.")


def _print_available_workflows(profile_manager: ProfileManager) -> None:
    """Print all built-in presets and saved user profiles to stdout."""
    print("\n=== Built-in Workflow Presets ===")
    for item in list_presets():
        csv_tag = " [CSV Batch]" if item["requires_csv"] else ""
        print(f"  • {item['preset_id']:<24} | {item['name']} ({item['step_count']} steps){csv_tag}")

    saved = profile_manager.list_profiles()
    print("\n=== Saved Workflow Profiles ===")
    if not saved:
        print("  (No saved profiles yet)")
    else:
        for wf in saved:
            print(f"  • {wf.workflow_id:<24} | {wf.name} ({len(wf.steps)} steps)")
    print()


def _run_cli(args: argparse.Namespace) -> int:
    """Execute a workflow headlessly or interactively from the command line."""
    profile_manager = ProfileManager()
    profile_manager.seed_default_profiles(overwrite=False)

    if args.list_presets:
        _print_available_workflows(profile_manager)
        return 0

    workflow = _resolve_cli_workflow(
        profile_manager=profile_manager,
        preset_id=args.preset,
        workflow_ref=args.workflow,
    )

    browser_manager = BrowserManager(
        browser_name=args.browser or config.DEFAULT_BROWSER,
        headless=bool(args.headless),
        timeout=float(args.timeout or config.DEFAULT_TIMEOUT),
    )
    csv_manager = CSVManager()
    log_manager = LogManager()
    engine = WorkflowEngine(
        browser_manager=browser_manager,
        log_manager=log_manager,
        csv_manager=csv_manager,
    )

    def _cli_approval(step: Any, row_idx: int, _ctx: dict[str, Any]) -> bool:
        if args.auto_approve:
            return True
        answer = input(
            f"[APPROVAL REQUIRED] Row {row_idx} -> '{step.display_name}' ({step.action_type}). "
            "Approve? [y/N]: "
        )
        return answer.strip().lower() in ("y", "yes")

    record = engine.run_workflow(
        workflow=workflow,
        csv_path=args.csv,
        browser_name=args.browser,
        headless=bool(args.headless),
        timeout=args.timeout,
        auto_export=bool(args.auto_export),
        export_path=args.export_path,
        stop_batch_on_row_error=bool(args.stop_on_error),
        approval_callback=_cli_approval,
        auto_approve=bool(args.auto_approve),
        on_log=lambda level, msg: print(f"[{level}] {msg}"),
    )

    print("\n--- Execution Summary ---")
    print(f"Workflow : {record.workflow_name} ({record.execution_id})")
    print(f"Status   : {record.status.upper()}")
    print(f"Duration : {record.duration_seconds:.2f}s")
    print(f"Rows     : {record.batch_rows_processed}")
    print(
        f"Actions  : {record.successful_actions}/{record.total_actions} succeeded "
        f"({record.failed_actions} failed, {record.skipped_actions} skipped)"
    )
    if record.notes:
        print(f"Notes    : {record.notes}")

    return 0 if record.status == config.RUN_STATUS_SUCCESS else 1


def _launch_gui() -> int:
    """Start the Nexora Tkinter desktop studio."""
    from interface.dashboard import NexoraDashboardApp

    app = NexoraDashboardApp()
    app.run()
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser for Nexora."""
    parser = argparse.ArgumentParser(
        prog="nexora",
        description="Nexora — Deterministic Selenium Workflow & CSV Batch Automation Studio",
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List all built-in workflow presets and saved user profiles, then exit.",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        help="Run a built-in workflow preset by ID (e.g., demo_directory_scraper).",
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default=None,
        help="Run a saved workflow by ID/name or a path to a workflow .json file.",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Path to an input CSV file for row-by-row batch automation.",
    )
    parser.add_argument(
        "--browser",
        type=str,
        choices=list(config.SUPPORTED_BROWSERS),
        default=None,
        help="Browser driver to use (chrome, edge).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode without a visible window.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Override default explicit wait timeout in seconds.",
    )
    parser.add_argument(
        "--auto-export",
        action="store_true",
        help="Automatically export extracted records to a timestamped CSV file.",
    )
    parser.add_argument(
        "--export-path",
        type=str,
        default=None,
        help="Explicit destination path for exported CSV results.",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve steps marked with requires_approval=True in CLI mode.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort remaining CSV batch rows immediately if any row encounters an error.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and dispatch either CLI execution or the Tkinter GUI."""
    _ensure_workspace_directories()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_presets or args.preset or args.workflow:
        return _run_cli(args)

    return _launch_gui()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[WARNING] Nexora interrupted by user.")
        raise SystemExit(130)