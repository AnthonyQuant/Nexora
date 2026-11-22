"""Main desktop application shell integrating Workflow Builder, Execution Monitor, and History."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any
import webbrowser

import config
from core.browser_manager import BrowserManager
from core.workflow_engine import WorkflowEngine
from interface.components import ActionButton, StatusBadge
from interface.execution_monitor import ExecutionMonitorView
from interface.history_viewer import HistoryViewerView
from interface.theme import COLORS, FONTS, apply_nexora_theme
from interface.workflow_builder import WorkflowBuilderView
from models.execution_record import ExecutionRecord
from models.workflow import Workflow
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager
from storage.profile_manager import ProfileManager
from workflows import DEMO_PORTAL_URL


def _open_directory(path: Path) -> None:
    """Open a local directory in the host operating system's file explorer."""
    resolved = path.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(resolved))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(resolved)], check=False)
    else:
        subprocess.run(["xdg-open", str(resolved)], check=False)


class NexoraDashboardApp:
    """Top-level Tkinter window orchestrating all Nexora views and shared services."""

    def __init__(
        self,
        root: tk.Tk | None = None,
        browser_manager: BrowserManager | None = None,
        profile_manager: ProfileManager | None = None,
        csv_manager: CSVManager | None = None,
        log_manager: LogManager | None = None,
        workflow_engine: WorkflowEngine | None = None,
    ) -> None:
        self.root: tk.Tk = root if root is not None else tk.Tk()
        apply_nexora_theme(self.root)

        app_title = getattr(config, "APP_NAME", "Nexora")
        self.root.title(f"{app_title} — Browser Automation & CSV Workflow Studio")
        self.root.geometry("1340x850")
        self.root.minsize(1100, 720)

        # Shared backend services
        self.browser_manager: BrowserManager = browser_manager or BrowserManager()
        self.profile_manager: ProfileManager = profile_manager or ProfileManager()
        self.csv_manager: CSVManager = csv_manager or CSVManager()
        self.log_manager: LogManager = log_manager or LogManager()
        self.workflow_engine: WorkflowEngine = workflow_engine or WorkflowEngine(
            browser_manager=self.browser_manager,
            log_manager=self.log_manager,
            csv_manager=self.csv_manager,
        )

        # Seed default starter profiles on first launch if profiles/ is empty
        try:
            self.profile_manager.seed_default_profiles(overwrite=False)
        except Exception:
            pass

        self.status_message_var = tk.StringVar(
            value="Ready • Select a workflow preset or build a custom automation sequence"
        )

        self._build_layout()
        self._bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window)

    def _build_layout(self) -> None:
        """Construct the top header bar, tabbed workspace notebook, and footer status bar."""
        # 1. Top Application Header
        header = tk.Frame(
            self.root,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=16,
            pady=10,
        )
        header.pack(fill=tk.X)

        brand_col = tk.Frame(header, bg=COLORS["bg_surface"])
        brand_col.pack(side=tk.LEFT)

        title_row = tk.Frame(brand_col, bg=COLORS["bg_surface"])
        title_row.pack(anchor="w")

        tk.Label(
            title_row,
            text="NEXORA",
            bg=COLORS["bg_surface"],
            fg=COLORS["accent"],
            font=FONTS["title"],
        ).pack(side=tk.LEFT, padx=(0, 10))

        version_str = getattr(config, "APP_VERSION", "v1.0.0")
        tk.Label(
            title_row,
            text=version_str,
            bg=COLORS["bg_surface_alt"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
            padx=8,
            pady=2,
        ).pack(side=tk.LEFT)

        tk.Label(
            brand_col,
            text="Deterministic Selenium Workflow Engine • CSV Batch Orchestration • Audit & Export Studio",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["subtitle"],
        ).pack(anchor="w", pady=(2, 0))

        # Right-side quick actions
        controls_col = tk.Frame(header, bg=COLORS["bg_surface"])
        controls_col.pack(side=tk.RIGHT)

        self.global_badge = StatusBadge(controls_col, status="ready", text="ENGINE READY")
        self.global_badge.pack(side=tk.RIGHT, padx=(10, 0))

        ActionButton(
            controls_col,
            text="Data Folder",
            command=self._on_open_data_folder,
            variant="secondary",
            padx=10,
            pady=5,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        ActionButton(
            controls_col,
            text="Open Demo Portal",
            command=self._on_open_demo_portal,
            variant="secondary",
            padx=10,
            pady=5,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        ActionButton(
            controls_col,
            text="Send Builder Workflow → Runner",
            command=self._on_send_builder_to_runner,
            variant="primary",
            padx=12,
            pady=5,
        ).pack(side=tk.RIGHT)

        # 2. Central Tabbed Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        self.execution_view = ExecutionMonitorView(
            self.notebook,
            workflow_engine=self.workflow_engine,
            profile_manager=self.profile_manager,
            csv_manager=self.csv_manager,
            on_run_completed=self._handle_run_completed,
        )
        self.builder_view = WorkflowBuilderView(
            self.notebook,
            profile_manager=self.profile_manager,
            on_workflow_saved=self._handle_workflow_saved,
        )
        self.history_view = HistoryViewerView(
            self.notebook,
            log_manager=self.log_manager,
            csv_manager=self.csv_manager,
        )

        self.notebook.add(self.execution_view, text="  Execution Monitor  ")
        self.notebook.add(self.builder_view, text="  Workflow Builder  ")
        self.notebook.add(self.history_view, text="  Run History & Exports  ")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # 3. Bottom Status Bar
        footer = tk.Frame(
            self.root,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=5,
        )
        footer.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Label(
            footer,
            textvariable=self.status_message_var,
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Label(
            footer,
            text="Shortcuts: Ctrl+S Save Workflow  |  F5 Refresh Views",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_muted"],
            font=FONTS["small"],
            anchor="e",
        ).pack(side=tk.RIGHT)

    def _bind_shortcuts(self) -> None:
        """Bind convenient global keyboard shortcuts."""
        self.root.bind("<Control-s>", self._on_shortcut_save)
        self.root.bind("<F5>", self._on_shortcut_refresh)

    def _on_shortcut_save(self, _event: tk.Event[Any]) -> None:
        if self.notebook.index(self.notebook.select()) == 1:
            self.builder_view.save_current_workflow()

    def _on_shortcut_refresh(self, _event: tk.Event[Any]) -> None:
        self.execution_view.refresh_workflows()
        self.history_view.refresh_history()
        self.set_status("Refreshed workflow profiles, run logs, and CSV exports.")

    def _on_tab_changed(self, _event: tk.Event[Any]) -> None:
        selected_idx = self.notebook.index(self.notebook.select())
        if selected_idx == 0:
            self.execution_view.refresh_workflows()
        elif selected_idx == 2:
            self.history_view.refresh_history()

    def _handle_workflow_saved(self, workflow: Workflow) -> None:
        """Sync newly saved workflows into the Execution Monitor dropdown."""
        self.execution_view.refresh_workflows()
        self.execution_view.load_workflow(workflow)
        self.set_status(
            f"Saved workflow '{workflow.name}' ({len(workflow.steps)} steps) and synced to Runner."
        )

    def _handle_run_completed(self, record: ExecutionRecord) -> None:
        """Refresh Run History & Exports automatically after any workflow finishes."""
        self.history_view.refresh_history()
        status_label = (record.status or "completed").upper()
        self.global_badge.set_status(record.status, text=status_label)
        self.set_status(
            f"Run '{record.workflow_name}' finished with status {status_label} "
            f"in {record.duration_seconds:.2f}s."
        )

    def _on_send_builder_to_runner(self) -> None:
        """Load the active Workflow Builder definition into Execution Monitor and switch tabs."""
        self.builder_view._sync_metadata_to_workflow()
        wf = self.builder_view.current_workflow
        if not wf.steps:
            messagebox.showwarning(
                "No Steps in Builder",
                "Add at least one action step in the Workflow Builder before sending to Runner.",
                parent=self.root,
            )
            return

        self.execution_view.load_workflow(wf)
        self.notebook.select(self.execution_view)
        self.set_status(
            f"Loaded '{wf.name}' ({len(wf.steps)} steps) from Builder into Execution Monitor."
        )

    def _on_open_demo_portal(self) -> None:
        """Launch the bundled offline demo HTML portal in the user's default browser."""
        demo_html = Path(getattr(config, "DEMO_SITE_DIR", Path("demo_site"))) / "index.html"
        if not demo_html.exists():
            messagebox.showerror(
                "Demo Portal Missing",
                f"Could not find local demo file at:\n{demo_html.resolve()}",
                parent=self.root,
            )
            return
        webbrowser.open(DEMO_PORTAL_URL)
        self.set_status("Opened offline Nexora Demo Portal in your default web browser.")

    def _on_open_data_folder(self) -> None:
        """Open Nexora's `data/` directory containing profiles, logs, exports, and downloads."""
        try:
            _open_directory(config.DATA_DIR)
        except Exception as exc:
            messagebox.showerror("Open Folder Error", str(exc), parent=self.root)

    def set_status(self, message: str) -> None:
        """Update the bottom status bar text."""
        self.status_message_var.set(message)

    def _on_close_window(self) -> None:
        """Gracefully halt any active workflow and close open Selenium sessions before exit."""
        if self.workflow_engine.is_running:
            if not messagebox.askyesno(
                "Workflow Still Running",
                "A workflow execution is currently active. Stop it and close Nexora?",
                parent=self.root,
            ):
                return
            self.workflow_engine.stop()

        try:
            self.browser_manager.close_session()
        except Exception:
            pass

        self.root.destroy()

    def run(self) -> None:
        """Start the Tkinter desktop event loop."""
        self.root.mainloop()


DashboardWindow = NexoraDashboardApp
NexoraApp = NexoraDashboardApp