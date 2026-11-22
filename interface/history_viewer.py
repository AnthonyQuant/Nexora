"""Execution run history browser, step-level audit inspector, and CSV export viewer."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import config
from interface.components import ActionButton, CardFrame, DataTable, KpiCard, StatusBadge
from interface.theme import COLORS, FONTS
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager, WorkflowRunRecord


def _open_path_in_os(target: Path) -> None:
    """Open a file or directory using the host operating system's default handler."""
    resolved = target.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    if sys.platform.startswith("win"):
        os.startfile(str(resolved))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(resolved)], check=False)
    else:
        subprocess.run(["xdg-open", str(resolved)], check=False)


class HistoryViewerView(tk.Frame):
    """Interactive viewer for historical workflow runs, step diagnostics, and exported CSVs."""

    def __init__(
        self,
        master: tk.Misc,
        log_manager: LogManager | None = None,
        csv_manager: CSVManager | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=COLORS["bg_primary"], **kwargs)
        self.log_manager: LogManager = log_manager or LogManager()
        self.csv_manager: CSVManager = csv_manager or CSVManager()

        self._all_runs: list[WorkflowRunRecord] = []
        self._filtered_runs: list[WorkflowRunRecord] = []
        self._selected_run: WorkflowRunRecord | None = None
        self._export_files_map: dict[str, Path] = {}

        # Filter & status variables
        self.search_var = tk.StringVar(value="")
        self.status_filter_var = tk.StringVar(value="All")
        self.export_choice_var = tk.StringVar(value="")
        self.run_detail_var = tk.StringVar(
            value="Select a workflow run on the left to inspect step logs and outputs."
        )

        self._build_ui()
        self.refresh_history()

    def _build_ui(self) -> None:
        """Assemble KPI summary strip, filter toolbar, runs list, step audit table, and CSV preview."""
        # 1. KPI Summary Strip
        kpi_strip = tk.Frame(self, bg=COLORS["bg_primary"])
        kpi_strip.pack(fill=tk.X, padx=12, pady=(12, 8))
        for idx in range(4):
            kpi_strip.grid_columnconfigure(idx, weight=1)

        self.kpi_total_runs = KpiCard(
            kpi_strip,
            label="Total Runs Logged",
            value="0",
            subtext="Recorded executions",
            accent_color=COLORS["accent"],
        )
        self.kpi_total_runs.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.kpi_success_rate = KpiCard(
            kpi_strip,
            label="Run Completion Rate",
            value="0.0%",
            subtext="0 completed runs",
            accent_color=COLORS["success"],
        )
        self.kpi_success_rate.grid(row=0, column=1, sticky="ew", padx=6)

        self.kpi_rows_processed = KpiCard(
            kpi_strip,
            label="Batch Rows Processed",
            value="0",
            subtext="0 succeeded • 0 failed",
            accent_color=COLORS["warning"],
        )
        self.kpi_rows_processed.grid(row=0, column=2, sticky="ew", padx=6)

        self.kpi_exports_count = KpiCard(
            kpi_strip,
            label="CSV Export Files",
            value="0",
            subtext="Saved in exports directory",
            accent_color=COLORS["accent"],
        )
        self.kpi_exports_count.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        # 2. Filter & History Management Toolbar
        toolbar = tk.Frame(
            self,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        toolbar.pack(fill=tk.X, padx=12, pady=(0, 8))

        tk.Label(
            toolbar,
            text="Search Workflow:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).pack(side=tk.LEFT, padx=(0, 6))

        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=26)
        search_entry.pack(side=tk.LEFT, padx=(0, 12))
        search_entry.bind("<KeyRelease>", lambda _e: self._apply_filters())

        tk.Label(
            toolbar,
            text="Status:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).pack(side=tk.LEFT, padx=(0, 6))

        status_combo = ttk.Combobox(
            toolbar,
            textvariable=self.status_filter_var,
            values=["All", "completed", "partial", "failed", "stopped"],
            state="readonly",
            width=13,
        )
        status_combo.pack(side=tk.LEFT, padx=(0, 12))
        status_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_filters())

        ActionButton(
            toolbar,
            text="Refresh",
            command=self.refresh_history,
            variant="primary",
            padx=12,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            toolbar,
            text="Open Exports Folder",
            command=self._on_open_exports_folder,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT)

        ActionButton(
            toolbar,
            text="Clear All History",
            command=self._on_clear_history,
            variant="danger",
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        ActionButton(
            toolbar,
            text="Delete Run",
            command=self._on_delete_selected_run,
            variant="danger",
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT)

        # 3. Main Split Workspace: Left (Runs List) | Right (Step Audit + CSV Preview)
        workspace = tk.Frame(self, bg=COLORS["bg_primary"])
        workspace.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        workspace.grid_columnconfigure(0, weight=5)
        workspace.grid_columnconfigure(1, weight=6)
        workspace.grid_rowconfigure(0, weight=1)

        # Left Card: Historical Runs Table
        runs_card = CardFrame(
            workspace,
            title="Execution Run History",
            subtitle="Click any run record to inspect step-by-step telemetry and outputs",
            padx=12,
            pady=10,
        )
        runs_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.runs_table = DataTable(
            runs_card,
            columns=["Run ID", "Workflow", "Status", "Started", "Duration", "Rows", "Extracted"],
            height=16,
        )
        self.runs_table.set_columns(
            ["Run ID", "Workflow", "Status", "Started", "Duration", "Rows", "Extracted"],
            widths={
                "Run ID": 95,
                "Workflow": 180,
                "Status": 85,
                "Started": 130,
                "Duration": 72,
                "Rows": 70,
                "Extracted": 70,
            },
        )
        self.runs_table.pack(fill=tk.BOTH, expand=True)
        self.runs_table.tree.bind("<<TreeviewSelect>>", self._on_run_selected)

        # Right Column: Stacked Step Details (Top) + CSV Export Preview (Bottom)
        right_col = tk.Frame(workspace, bg=COLORS["bg_primary"])
        right_col.grid(row=0, column=1, sticky="nsew")
        right_col.grid_rowconfigure(0, weight=1)
        right_col.grid_rowconfigure(1, weight=1)
        right_col.grid_columnconfigure(0, weight=1)

        # Top Right: Step-by-Step Audit Log
        step_audit_card = CardFrame(
            right_col,
            title="Step-by-Step Audit Log",
            subtitle="Detailed execution breakdown for the selected workflow run",
            padx=12,
            pady=10,
        )
        step_audit_card.grid(row=0, column=0, sticky="nsew", pady=(0, 8))

        detail_header = tk.Frame(step_audit_card, bg=COLORS["bg_surface"])
        detail_header.pack(fill=tk.X, pady=(0, 6))

        self.selected_status_badge = StatusBadge(detail_header, status="ready", text="NO RUN")
        self.selected_status_badge.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            detail_header,
            textvariable=self.run_detail_var,
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small"],
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.open_run_csv_btn = ActionButton(
            detail_header,
            text="Open Run CSV",
            command=self._on_open_selected_run_export,
            variant="secondary",
            padx=10,
            pady=3,
            state=tk.DISABLED,
        )
        self.open_run_csv_btn.pack(side=tk.RIGHT)

        self.step_logs_table = DataTable(
            step_audit_card,
            columns=["#", "Action", "Description", "Status", "Time", "Output / Error"],
            height=8,
        )
        self.step_logs_table.set_columns(
            ["#", "Action", "Description", "Status", "Time", "Output / Error"],
            widths={
                "#": 38,
                "Action": 105,
                "Description": 150,
                "Status": 75,
                "Time": 65,
                "Output / Error": 240,
            },
        )
        self.step_logs_table.pack(fill=tk.BOTH, expand=True)

        # Bottom Right: CSV Export Previewer
        export_card = CardFrame(
            right_col,
            title="CSV Export Data Preview",
            subtitle="Inspect structured records exported from completed automation runs",
            padx=12,
            pady=10,
        )
        export_card.grid(row=1, column=0, sticky="nsew")

        export_bar = tk.Frame(export_card, bg=COLORS["bg_surface"])
        export_bar.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            export_bar,
            text="Export File:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.export_combo = ttk.Combobox(
            export_bar,
            textvariable=self.export_choice_var,
            state="readonly",
            width=36,
        )
        self.export_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.export_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_selected_export_preview())

        ActionButton(
            export_bar,
            text="Open File",
            command=self._on_open_chosen_export_file,
            variant="secondary",
            padx=10,
            pady=3,
        ).pack(side=tk.RIGHT)

        self.csv_preview_table = DataTable(
            export_card,
            columns=["Info"],
            height=7,
        )
        self.csv_preview_table.set_columns(["Info"], widths={"Info": 420})
        self.csv_preview_table.set_rows([{"Info": "No CSV export selected."}])
        self.csv_preview_table.pack(fill=tk.BOTH, expand=True)

    def refresh_history(self) -> None:
        """Reload run logs and exported CSV files from disk and refresh all widgets."""
        if hasattr(self.log_manager, "list_runs"):
            self._all_runs = self.log_manager.list_runs()
        else:
            self._all_runs = []

        self._update_kpis()
        self._apply_filters()
        self._refresh_exports_dropdown()

    def _update_kpis(self) -> None:
        """Compute aggregate metrics across all logged runs and CSV exports."""
        total = len(self._all_runs)
        completed = sum(1 for r in self._all_runs if (r.status or "").lower() == "completed")
        total_rows = sum(int(getattr(r, "rows_processed", 0)) for r in self._all_runs)
        ok_rows = sum(int(getattr(r, "rows_succeeded", 0)) for r in self._all_runs)
        err_rows = sum(int(getattr(r, "rows_failed", 0)) for r in self._all_runs)

        rate = (completed / total * 100.0) if total > 0 else 0.0
        exports = self.csv_manager.list_exports() if hasattr(self.csv_manager, "list_exports") else []

        self.kpi_total_runs.set_value(str(total), f"{total} run log(s) stored")
        self.kpi_success_rate.set_value(f"{rate:.1f}%", f"{completed} of {total} completed")
        self.kpi_rows_processed.set_value(
            str(total_rows),
            f"{ok_rows} succeeded • {err_rows} failed",
        )
        self.kpi_exports_count.set_value(str(len(exports)), "CSV files in exports/")

    def _apply_filters(self) -> None:
        """Filter `_all_runs` by search query and status and populate `runs_table`."""
        query = self.search_var.get().strip().lower()
        status_filter = self.status_filter_var.get().strip().lower()

        filtered: list[WorkflowRunRecord] = []
        for run in self._all_runs:
            run_status = (run.status or "").strip().lower()
            if status_filter and status_filter != "all" and run_status != status_filter:
                continue
            if query and query not in run.workflow_name.lower() and query not in run.run_id.lower():
                continue
            filtered.append(run)

        self._filtered_runs = filtered
        rows_for_table: list[dict[str, str]] = []
        for run in filtered:
            started_display = (run.started_at or "").replace("T", " ")[:19]
            dur_sec = (run.duration_ms or 0) / 1000.0
            rows_for_table.append(
                {
                    "Run ID": run.run_id[:12],
                    "Workflow": run.workflow_name,
                    "Status": (run.status or "").upper(),
                    "Started": started_display,
                    "Duration": f"{dur_sec:.2f}s",
                    "Rows": f"{run.rows_succeeded}/{run.rows_processed}",
                    "Extracted": str(run.extracted_count),
                }
            )

        self.runs_table.set_rows(rows_for_table)
        self._selected_run = None
        self.step_logs_table.clear()
        self.selected_status_badge.set_status("ready", text="NO RUN")
        self.run_detail_var.set("Select a workflow run on the left to inspect step logs and outputs.")
        self.open_run_csv_btn.configure(state=tk.DISABLED)

        # Auto-select the first row if available
        children = self.runs_table.tree.get_children()
        if children:
            self.runs_table.tree.selection_set(children[0])
            self._display_run_details(filtered[0])

    def _display_run_details(self, run: WorkflowRunRecord) -> None:
        """Render step-level logs and export linkage for `run`."""
        self._selected_run = run
        status_key = (run.status or "completed").lower()
        self.selected_status_badge.set_status(status_key, text=status_key.upper())

        summary_parts = [f"Run {run.run_id[:12]} • {len(run.step_logs)} step(s)"]
        if run.error_summary:
            summary_parts.append(f"Error: {run.error_summary}")
        self.run_detail_var.set(" | ".join(summary_parts))

        step_rows: list[dict[str, str]] = []
        for s_log in run.step_logs:
            detail_text = s_log.error_message if s_log.error_message else s_log.output_value
            step_rows.append(
                {
                    "#": str(s_log.step_index),
                    "Action": s_log.action_type,
                    "Description": s_log.description,
                    "Status": (s_log.status or "").upper(),
                    "Time": f"{s_log.duration_ms}ms",
                    "Output / Error": detail_text or "-",
                }
            )
        self.step_logs_table.set_rows(step_rows)

        export_str = (run.export_path or "").strip()
        if export_str and Path(export_str).exists():
            self.open_run_csv_btn.configure(state=tk.NORMAL)
            export_name = Path(export_str).name
            if export_name in self._export_files_map:
                self.export_choice_var.set(export_name)
                self._load_selected_export_preview()
        else:
            self.open_run_csv_btn.configure(state=tk.DISABLED)

    def _on_run_selected(self, _event: tk.Event[Any]) -> None:
        idx = self.runs_table.get_selected_index()
        if idx is None or not (0 <= idx < len(self._filtered_runs)):
            return
        self._display_run_details(self._filtered_runs[idx])

    def _refresh_exports_dropdown(self) -> None:
        """Populate the CSV exports selector from `CSVManager.list_exports()`."""
        self._export_files_map.clear()
        exports: list[Path] = []
        if hasattr(self.csv_manager, "list_exports"):
            exports = self.csv_manager.list_exports()

        for path in exports:
            self._export_files_map[path.name] = path

        names = list(self._export_files_map.keys())
        self.export_combo.configure(values=names)
        if names:
            if self.export_choice_var.get() not in self._export_files_map:
                self.export_choice_var.set(names[0])
            self._load_selected_export_preview()
        else:
            self.export_choice_var.set("")
            self.csv_preview_table.set_columns(["Info"], widths={"Info": 420})
            self.csv_preview_table.set_rows([{"Info": "No exported CSV files found yet."}])

    def _load_selected_export_preview(self) -> None:
        """Load up to 100 rows from the chosen CSV export into `csv_preview_table`."""
        chosen_name = self.export_choice_var.get().strip()
        csv_path = self._export_files_map.get(chosen_name)
        if csv_path is None or not csv_path.exists():
            return

        try:
            headers, rows = self.csv_manager.load_csv(csv_path)
        except Exception as exc:
            self.csv_preview_table.set_columns(["Error"], widths={"Error": 420})
            self.csv_preview_table.set_rows([{"Error": f"Failed to read CSV: {exc}"}])
            return

        if not headers:
            self.csv_preview_table.set_columns(["Info"], widths={"Info": 420})
            self.csv_preview_table.set_rows([{"Info": "CSV file is empty."}])
            return

        widths = {col: 150 for col in headers}
        self.csv_preview_table.set_columns(headers, widths=widths)
        self.csv_preview_table.set_rows(rows[:100])

    def _on_open_selected_run_export(self) -> None:
        if self._selected_run is None or not self._selected_run.export_path:
            return
        try:
            _open_path_in_os(Path(self._selected_run.export_path))
        except Exception as exc:
            messagebox.showerror("Open Export Error", str(exc), parent=self)

    def _on_open_chosen_export_file(self) -> None:
        chosen_name = self.export_choice_var.get().strip()
        csv_path = self._export_files_map.get(chosen_name)
        if csv_path is None:
            return
        try:
            _open_path_in_os(csv_path)
        except Exception as exc:
            messagebox.showerror("Open File Error", str(exc), parent=self)

    def _on_open_exports_folder(self) -> None:
        exports_dir = getattr(self.csv_manager, "exports_dir", config.EXPORTS_DIR)
        exports_dir.mkdir(parents=True, exist_ok=True)
        try:
            _open_path_in_os(exports_dir)
        except Exception as exc:
            messagebox.showerror("Open Folder Error", str(exc), parent=self)

    def _on_delete_selected_run(self) -> None:
        if self._selected_run is None:
            messagebox.showinfo("No Run Selected", "Select a run record to delete.", parent=self)
            return
        run_id = self._selected_run.run_id
        if not messagebox.askyesno(
            "Delete Run Record",
            f"Delete execution log '{run_id[:12]}' ({self._selected_run.workflow_name})?",
            parent=self,
        ):
            return
        if hasattr(self.log_manager, "delete_run"):
            self.log_manager.delete_run(run_id)
        self.refresh_history()

    def _on_clear_history(self) -> None:
        if not self._all_runs:
            return
        if not messagebox.askyesno(
            "Clear All Execution History",
            f"Permanently delete all {len(self._all_runs)} stored run log(s)?",
            parent=self,
        ):
            return
        if hasattr(self.log_manager, "clear_logs"):
            self.log_manager.clear_logs()
        elif hasattr(self.log_manager, "clear_runs"):
            self.log_manager.clear_runs()
        else:
            for run in list(self._all_runs):
                if hasattr(self.log_manager, "delete_run"):
                    self.log_manager.delete_run(run.run_id)
        self.refresh_history()


HistoryView = HistoryViewerView