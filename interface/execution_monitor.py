"""Live workflow execution monitor, CSV batch runner, approval prompts, and log console."""

from __future__ import annotations

from collections.abc import Callable
import csv
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

import config
from core.workflow_engine import WorkflowEngine
from interface.components import (
    ActionButton,
    CardFrame,
    ConsoleLogView,
    DataTable,
    KpiCard,
    StatusBadge,
)
from interface.theme import COLORS, FONTS
from models.execution_record import ExecutionRecord, StepExecutionResult
from models.workflow import Workflow
from models.workflow_step import WorkflowStep
from storage.csv_manager import CSVManager
from storage.profile_manager import ProfileManager
from workflows import get_preset_sample_csv, get_preset_workflow, list_presets

RunCompletedCallback = Callable[[ExecutionRecord], None]


class ExecutionDashboardView(tk.Frame):
    """Interactive control center for launching, monitoring, and stopping workflow runs."""

    def __init__(
        self,
        master: tk.Misc,
        workflow_engine: WorkflowEngine | None = None,
        profile_manager: ProfileManager | None = None,
        csv_manager: CSVManager | None = None,
        on_run_completed: RunCompletedCallback | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=COLORS["bg_primary"], **kwargs)
        self.workflow_engine: WorkflowEngine = workflow_engine or WorkflowEngine()
        self.profile_manager: ProfileManager = profile_manager or ProfileManager()
        self.csv_manager: CSVManager = csv_manager or CSVManager()
        self.on_run_completed: RunCompletedCallback | None = on_run_completed

        self._workflow_catalog: dict[str, tuple[str, str]] = {}
        self._active_workflow: Workflow | None = None
        self._active_preset_id: str | None = None
        self._csv_path: Path | None = None
        self._csv_headers: list[str] = []
        self._csv_row_count: int = 0
        self._last_record: ExecutionRecord | None = None
        self._worker_thread: threading.Thread | None = None
        self._ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()

        # Run counters updated on UI thread
        self._passed_steps: int = 0
        self._failed_steps: int = 0
        self._skipped_steps: int = 0
        self._extracted_items: int = 0
        self._step_rows_buffer: list[dict[str, str]] = []

        # Control variables
        self.selected_wf_var = tk.StringVar(value="")
        self.browser_var = tk.StringVar(value=config.DEFAULT_BROWSER)
        self.headless_var = tk.BooleanVar(value=False)
        self.auto_export_var = tk.BooleanVar(value=True)
        self.stop_on_row_err_var = tk.BooleanVar(value=False)
        self.csv_status_var = tk.StringVar(value="No CSV dataset attached (single-pass mode)")
        self.progress_caption_var = tk.StringVar(value="Ready to execute")

        self._build_ui()
        self.refresh_workflows()
        self._drain_ui_queue()

    def _enqueue_ui(self, callback: Callable[[], None]) -> None:
        """Safely queue a UI update callable from any background worker thread."""
        self._ui_queue.put(callback)

    def _drain_ui_queue(self) -> None:
        """Process queued worker-thread UI updates exclusively on the Tk main thread."""
        while True:
            try:
                callback = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except tk.TclError:
                return

        try:
            if self.winfo_exists():
                self.after(25, self._drain_ui_queue)
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        """Assemble the execution control bar, KPI cards, live step table, and console."""
        # 1. Execution Configuration & Batch Input Card
        control_card = CardFrame(
            self,
            title="Execution Control Center",
            subtitle="Select a saved workflow or built-in preset, optionally attach a CSV batch file, and run",
            padx=12,
            pady=10,
        )
        control_card.pack(fill=tk.X, padx=12, pady=(12, 8))

        top_row = tk.Frame(control_card, bg=COLORS["bg_surface"])
        top_row.pack(fill=tk.X, pady=(0, 8))
        top_row.grid_columnconfigure(1, weight=3)

        tk.Label(
            top_row,
            text="Target Workflow:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.workflow_combo = ttk.Combobox(
            top_row,
            textvariable=self.selected_wf_var,
            state="readonly",
            width=44,
        )
        self.workflow_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.workflow_combo.bind("<<ComboboxSelected>>", self._on_workflow_selected)

        ActionButton(
            top_row,
            text="Refresh",
            command=self.refresh_workflows,
            variant="secondary",
            padx=10,
            pady=4,
        ).grid(row=0, column=2, padx=(0, 14))

        tk.Label(
            top_row,
            text="Browser:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).grid(row=0, column=3, sticky="w", padx=(0, 6))

        self.browser_combo = ttk.Combobox(
            top_row,
            textvariable=self.browser_var,
            values=list(config.SUPPORTED_BROWSERS),
            state="readonly",
            width=11,
        )
        self.browser_combo.grid(row=0, column=4, padx=(0, 12))

        self.status_badge = StatusBadge(top_row, status="idle", text="IDLE")
        self.status_badge.grid(row=0, column=5, sticky="e")

        # Second row: CSV Batch Controls & Execution Flags
        csv_row = tk.Frame(control_card, bg=COLORS["bg_surface"])
        csv_row.pack(fill=tk.X, pady=(0, 8))

        ActionButton(
            csv_row,
            text="Attach CSV Batch...",
            command=self._on_browse_csv,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.sample_csv_btn = ActionButton(
            csv_row,
            text="Generate Sample CSV",
            command=self._on_generate_sample_csv,
            variant="secondary",
            padx=10,
            pady=4,
        )
        self.sample_csv_btn.pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            csv_row,
            text="Clear CSV",
            command=self._on_clear_csv,
            variant="secondary",
            padx=8,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 12))

        tk.Label(
            csv_row,
            textvariable=self.csv_status_var,
            bg=COLORS["bg_surface"],
            fg=COLORS["accent"],
            font=FONTS["small"],
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Third row: Checkboxes & Run/Stop Action Buttons
        action_row = tk.Frame(control_card, bg=COLORS["bg_surface"])
        action_row.pack(fill=tk.X)

        ttk.Checkbutton(
            action_row,
            text="Headless Browser",
            variable=self.headless_var,
        ).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Checkbutton(
            action_row,
            text="Auto-Export Extracted CSV",
            variable=self.auto_export_var,
        ).pack(side=tk.LEFT, padx=(0, 14))

        ttk.Checkbutton(
            action_row,
            text="Halt Batch on Row Error",
            variable=self.stop_on_row_err_var,
        ).pack(side=tk.LEFT)

        self.stop_btn = ActionButton(
            action_row,
            text="Stop Execution",
            command=self._on_stop_clicked,
            variant="danger",
            padx=14,
            pady=5,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self.run_btn = ActionButton(
            action_row,
            text="Run Workflow",
            command=self._on_run_clicked,
            variant="success",
            padx=18,
            pady=5,
        )
        self.run_btn.pack(side=tk.RIGHT)

        # 2. KPI Metrics Strip & Progress Bar
        kpi_strip = tk.Frame(self, bg=COLORS["bg_primary"])
        kpi_strip.pack(fill=tk.X, padx=12, pady=(0, 8))
        for col_idx in range(4):
            kpi_strip.grid_columnconfigure(col_idx, weight=1)

        self.kpi_progress = KpiCard(
            kpi_strip,
            label="Batch & Step Progress",
            value="0 / 0",
            subtext="Awaiting run",
            accent_color=COLORS["accent"],
        )
        self.kpi_progress.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.kpi_succeeded = KpiCard(
            kpi_strip,
            label="Steps Succeeded",
            value="0",
            subtext="Completed cleanly",
            accent_color=COLORS["success"],
        )
        self.kpi_succeeded.grid(row=0, column=1, sticky="ew", padx=6)

        self.kpi_issues = KpiCard(
            kpi_strip,
            label="Failed / Skipped",
            value="0 / 0",
            subtext="Errors / Guard skips",
            accent_color=COLORS["warning"],
        )
        self.kpi_issues.grid(row=0, column=2, sticky="ew", padx=6)

        self.kpi_extracted = KpiCard(
            kpi_strip,
            label="Extracted Records",
            value="0",
            subtext="Captured data rows",
            accent_color=COLORS["accent"],
        )
        self.kpi_extracted.grid(row=0, column=3, sticky="ew", padx=(6, 0))

        progress_frame = tk.Frame(
            self,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=12,
            pady=6,
        )
        progress_frame.pack(fill=tk.X, padx=12, pady=(0, 8))

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100,
            value=0,
        )
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))

        tk.Label(
            progress_frame,
            textvariable=self.progress_caption_var,
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
            width=32,
            anchor="e",
        ).pack(side=tk.RIGHT)

        # 3. Bottom Split: Live Step Telemetry Table | Monospaced Execution Console
        bottom_split = tk.Frame(self, bg=COLORS["bg_primary"])
        bottom_split.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        bottom_split.grid_columnconfigure(0, weight=3)
        bottom_split.grid_columnconfigure(1, weight=2)
        bottom_split.grid_rowconfigure(0, weight=1)

        steps_card = CardFrame(
            bottom_split,
            title="Live Step Execution Feed",
            subtitle="Per-step status, retry count, timing, and diagnostic outcomes",
            padx=12,
            pady=10,
        )
        steps_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.results_table = DataTable(
            steps_card,
            columns=["Row", "Step", "Action", "Status", "Tries", "Time", "Outcome"],
            height=12,
        )
        self.results_table.set_columns(
            ["Row", "Step", "Action", "Status", "Tries", "Time", "Outcome"],
            widths={
                "Row": 45,
                "Step": 150,
                "Action": 110,
                "Status": 80,
                "Tries": 48,
                "Time": 68,
                "Outcome": 240,
            },
        )
        self.results_table.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        table_footer = tk.Frame(steps_card, bg=COLORS["bg_surface"])
        table_footer.pack(fill=tk.X)

        self.export_now_btn = ActionButton(
            table_footer,
            text="Export Extracted Results CSV...",
            command=self._on_manual_export,
            variant="primary",
            padx=12,
            pady=4,
            state=tk.DISABLED,
        )
        self.export_now_btn.pack(side=tk.RIGHT)

        console_card = CardFrame(
            bottom_split,
            title="Engine Console Log",
            subtitle="Real-time execution stream and browser diagnostics",
            padx=12,
            pady=10,
        )
        console_card.grid(row=0, column=1, sticky="nsew")

        self.console_view = ConsoleLogView(console_card, height=12)
        self.console_view.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        console_footer = tk.Frame(console_card, bg=COLORS["bg_surface"])
        console_footer.pack(fill=tk.X)

        ActionButton(
            console_footer,
            text="Clear Console",
            command=self.console_view.clear,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT)

    def refresh_workflows(self) -> None:
        """Reload saved user profiles and built-in presets into the workflow selector."""
        previous_choice = self.selected_wf_var.get()
        self._workflow_catalog.clear()

        saved_profiles: list[Workflow] = []
        if hasattr(self.profile_manager, "list_profiles"):
            saved_profiles = self.profile_manager.list_profiles()

        for wf in saved_profiles:
            label = f"[Saved] {wf.name} ({len(wf.steps)} steps)"
            self._workflow_catalog[label] = ("saved", wf.workflow_id)

        for preset in list_presets():
            label = f"[Preset] {preset['name']} ({preset['step_count']} steps)"
            self._workflow_catalog[label] = ("preset", preset["preset_id"])

        labels = list(self._workflow_catalog.keys())
        self.workflow_combo.configure(values=labels)

        if labels:
            chosen = previous_choice if previous_choice in self._workflow_catalog else labels[0]
            self.selected_wf_var.set(chosen)
            self._resolve_selected_workflow()

    def load_workflow(self, workflow: Workflow, preset_id: str | None = None) -> None:
        """Directly load a `Workflow` instance into the dashboard runner."""
        self._active_workflow = workflow
        self._active_preset_id = preset_id
        wf_browser = getattr(workflow, "browser", "") or config.DEFAULT_BROWSER
        if wf_browser in config.SUPPORTED_BROWSERS:
            self.browser_var.set(wf_browser)

        for label, (kind, ref_id) in self._workflow_catalog.items():
            if kind == "saved" and ref_id == workflow.workflow_id:
                self.selected_wf_var.set(label)
                break

        self._update_sample_csv_button_state()

    def _resolve_selected_workflow(self) -> Workflow | None:
        """Instantiate or fetch the `Workflow` currently chosen in `workflow_combo`."""
        chosen_label = self.selected_wf_var.get().strip()
        entry = self._workflow_catalog.get(chosen_label)
        if entry is None:
            return self._active_workflow

        kind, ref_id = entry
        if kind == "preset":
            wf = get_preset_workflow(ref_id)
            self._active_workflow = wf
            self._active_preset_id = ref_id
        else:
            wf = self.profile_manager.get_workflow(ref_id)
            if wf is not None:
                self._active_workflow = wf
                self._active_preset_id = None

        if self._active_workflow is not None:
            wf_browser = getattr(self._active_workflow, "browser", "") or config.DEFAULT_BROWSER
            if wf_browser in config.SUPPORTED_BROWSERS:
                self.browser_var.set(wf_browser)

        self._update_sample_csv_button_state()
        return self._active_workflow

    def _update_sample_csv_button_state(self) -> None:
        """Enable 'Generate Sample CSV' when the active preset defines sample CSV data."""
        has_sample = False
        if self._active_preset_id:
            headers, rows = get_preset_sample_csv(self._active_preset_id)
            has_sample = bool(headers and rows)
        self.sample_csv_btn.configure(state=tk.NORMAL if has_sample else tk.DISABLED)

    def _on_workflow_selected(self, _event: tk.Event[Any]) -> None:
        self._resolve_selected_workflow()

    def _attach_csv_file(self, path: Path) -> None:
        """Validate and attach a CSV file for batch iteration."""
        headers, rows = self.csv_manager.load_csv(path)
        if not rows:
            raise ValueError(f"CSV file '{path.name}' contains no data rows.")
        self._csv_path = path.resolve()
        self._csv_headers = headers
        self._csv_row_count = len(rows)
        cols_preview = ", ".join(headers[:5]) + ("..." if len(headers) > 5 else "")
        self.csv_status_var.set(
            f"Attached: {path.name} ({self._csv_row_count} rows | cols: {cols_preview})"
        )
        self.console_view.append_log(
            "INFO",
            f"Loaded CSV batch '{path.name}' with {self._csv_row_count} row(s).",
        )

    def _on_browse_csv(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select CSV Batch Input File",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
        )
        if not selected:
            return
        try:
            self._attach_csv_file(Path(selected))
        except Exception as exc:
            messagebox.showerror("CSV Load Error", str(exc), parent=self)

    def _on_generate_sample_csv(self) -> None:
        """Write the active preset's sample CSV dataset to disk and attach it."""
        if not self._active_preset_id:
            return
        headers, rows = get_preset_sample_csv(self._active_preset_id)
        if not headers or not rows:
            return

        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        sample_path = config.DATA_DIR / f"{self._active_preset_id}_sample.csv"
        with sample_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        try:
            self._attach_csv_file(sample_path)
        except Exception as exc:
            messagebox.showerror("Sample CSV Error", str(exc), parent=self)

    def _on_clear_csv(self) -> None:
        self._csv_path = None
        self._csv_headers = []
        self._csv_row_count = 0
        self.csv_status_var.set("No CSV dataset attached (single-pass mode)")

    def _prompt_approval_threadsafe(
        self,
        step: WorkflowStep,
        row_index: int,
        _context: dict[str, Any],
    ) -> bool:
        """Pause the background worker thread and ask the user to approve a gated step."""
        decision_event = threading.Event()
        decision_holder: dict[str, bool] = {"approved": False}

        def _ask_on_main_thread() -> None:
            try:
                self.console_view.append_log(
                    "WARNING",
                    f"Approval required for step '{step.display_name}' (Row {row_index})...",
                )
                approved = messagebox.askyesno(
                    "Human-in-the-Loop Approval Gate",
                    (
                        f"Workflow paused at Row {row_index}:\n\n"
                        f"Step: {step.display_name}\n"
                        f"Action: {step.action_type}\n"
                        f"Target: {step.selector_value or step.input_value or 'N/A'}\n\n"
                        "Approve and continue execution?"
                    ),
                    parent=self,
                )
                decision_holder["approved"] = bool(approved)
            finally:
                decision_event.set()

        self._enqueue_ui(_ask_on_main_thread)
        decision_event.wait()
        return decision_holder["approved"]

    def _reset_run_telemetry(self, total_steps: int, total_rows: int) -> None:
        """Reset KPI cards, progress bar, and live step feed before starting a run."""
        self._passed_steps = 0
        self._failed_steps = 0
        self._skipped_steps = 0
        self._extracted_items = 0
        self._step_rows_buffer.clear()
        self._last_record = None

        self.results_table.clear()
        self.export_now_btn.configure(state=tk.DISABLED)
        self.progress_bar.configure(value=0)
        self.progress_caption_var.set(f"0 / {total_steps * total_rows} actions completed")

        self.kpi_progress.set_value(f"Row 1 / {total_rows}", f"{total_steps} steps per row")
        self.kpi_succeeded.set_value("0", "Completed cleanly")
        self.kpi_issues.set_value("0 / 0", "0 failed • 0 skipped")
        self.kpi_extracted.set_value("0", "Captured data rows")

    def _on_run_clicked(self) -> None:
        """Validate selection and launch `WorkflowEngine.run_workflow` on a background thread."""
        if self.workflow_engine.is_running or (
            self._worker_thread is not None and self._worker_thread.is_alive()
        ):
            messagebox.showinfo(
                "Execution In Progress",
                "A workflow is already running. Wait for it to finish or click 'Stop Execution'.",
                parent=self,
            )
            return

        workflow = self._resolve_selected_workflow()
        if workflow is None:
            messagebox.showwarning(
                "No Workflow Selected",
                "Choose a saved workflow or built-in preset before running.",
                parent=self,
            )
            return

        if not workflow.steps:
            messagebox.showwarning(
                "Empty Workflow",
                f"Workflow '{workflow.name}' has 0 steps. Add steps in the Workflow Builder first.",
                parent=self,
            )
            return

        total_rows = self._csv_row_count if self._csv_path is not None else 1
        total_steps = len(workflow.steps)
        total_planned_actions = max(1, total_rows * total_steps)

        self._reset_run_telemetry(total_steps=total_steps, total_rows=total_rows)
        self.status_badge.set_status("running", text="RUNNING")
        self.run_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        selected_browser = self.browser_var.get().strip() or config.DEFAULT_BROWSER
        is_headless = bool(self.headless_var.get())
        do_auto_export = bool(self.auto_export_var.get())
        halt_on_row_err = bool(self.stop_on_row_err_var.get())
        csv_file = self._csv_path

        def _handle_step_start(
            step: WorkflowStep,
            step_idx: int,
            row_idx: int,
            rows_total: int,
        ) -> None:
            def _ui_update() -> None:
                self.kpi_progress.set_value(
                    f"Row {row_idx} / {rows_total}",
                    f"Running step {step_idx}/{total_steps}: {step.display_name}",
                )

            self._enqueue_ui(_ui_update)

        def _handle_step_complete(
            result: StepExecutionResult,
            row_idx: int,
            rows_total: int,
        ) -> None:
            def _ui_update() -> None:
                if result.status == config.STEP_STATUS_SUCCESS:
                    self._passed_steps += 1
                elif result.status == config.STEP_STATUS_SKIPPED:
                    self._skipped_steps += 1
                else:
                    self._failed_steps += 1

                if result.extracted_data:
                    if isinstance(result.extracted_data, list):
                        self._extracted_items += len(result.extracted_data)
                    else:
                        self._extracted_items += 1

                completed_count = self._passed_steps + self._failed_steps + self._skipped_steps
                pct = min(100.0, (completed_count / total_planned_actions) * 100.0)
                self.progress_bar.configure(value=pct)
                self.progress_caption_var.set(
                    f"{completed_count} / {total_planned_actions} actions ({pct:.0f}%)"
                )

                self.kpi_succeeded.set_value(str(self._passed_steps))
                self.kpi_issues.set_value(
                    f"{self._failed_steps} / {self._skipped_steps}",
                    f"{self._failed_steps} failed • {self._skipped_steps} skipped",
                )
                self.kpi_extracted.set_value(str(self._extracted_items))

                self._step_rows_buffer.append(
                    {
                        "Row": f"{row_idx}/{rows_total}",
                        "Step": f"{result.step_index}. {result.step_name}",
                        "Action": result.action_type,
                        "Status": result.status.upper(),
                        "Tries": str(result.attempts),
                        "Time": f"{result.duration_ms:.0f}ms",
                        "Outcome": result.message,
                    }
                )
                self.results_table.set_rows(self._step_rows_buffer)
                children = self.results_table.tree.get_children()
                if children:
                    self.results_table.tree.see(children[-1])

            self._enqueue_ui(_ui_update)

        def _handle_log(level: str, message: str) -> None:
            self._enqueue_ui(lambda: self.console_view.append_log(level, message))

        def _worker() -> None:
            record: ExecutionRecord | None = None
            error_text: str | None = None
            try:
                record = self.workflow_engine.run_workflow(
                    workflow=workflow,
                    csv_path=csv_file,
                    browser_name=selected_browser,
                    headless=is_headless,
                    auto_export=do_auto_export,
                    stop_batch_on_row_error=halt_on_row_err,
                    approval_callback=self._prompt_approval_threadsafe,
                    on_step_start=_handle_step_start,
                    on_step_complete=_handle_step_complete,
                    on_log=_handle_log,
                )
            except Exception as exc:
                error_text = str(exc)

            def _finalize_on_ui() -> None:
                self.run_btn.configure(state=tk.NORMAL)
                self.stop_btn.configure(state=tk.DISABLED)

                if error_text is not None:
                    self.status_badge.set_status("failed", text="ERROR")
                    self.progress_caption_var.set("Aborted due to error")
                    messagebox.showerror("Workflow Execution Error", error_text, parent=self)
                    return

                if record is not None:
                    self._last_record = record
                    status_key = (record.status or "completed").lower()
                    self.status_badge.set_status(status_key, text=status_key.upper())
                    self.progress_bar.configure(value=100)
                    self.progress_caption_var.set(
                        f"Finished in {record.duration_seconds:.2f}s ({status_key.upper()})"
                    )
                    self.kpi_progress.set_value(
                        f"{record.batch_rows_processed} / {total_rows} rows",
                        f"Completed in {record.duration_seconds:.2f}s",
                    )

                    extracted = record.collect_extracted_rows()
                    self.kpi_extracted.set_value(str(len(extracted)))
                    if extracted:
                        self.export_now_btn.configure(state=tk.NORMAL)

                    if callable(self.on_run_completed):
                        self.on_run_completed(record)

            self._enqueue_ui(_finalize_on_ui)

        self._worker_thread = threading.Thread(target=_worker, name="NexoraWorker", daemon=True)
        self._worker_thread.start()

    def _on_stop_clicked(self) -> None:
        """Request cooperative cancellation of the running workflow."""
        self.workflow_engine.stop()
        self.stop_btn.configure(state=tk.DISABLED)
        self.status_badge.set_status("stopped", text="STOPPING...")
        self.console_view.append_log("WARNING", "Stop requested by user; halting after current action...")

    def _on_manual_export(self) -> None:
        """Export extracted rows from `_last_record` to a user-selected CSV path."""
        if self._last_record is None:
            return
        extracted = self._last_record.collect_extracted_rows()
        if not extracted:
            messagebox.showinfo(
                "No Extracted Data",
                "The last run did not capture any structured data to export.",
                parent=self,
            )
            return

        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Export Extracted Results to CSV",
            defaultextension=".csv",
            initialfile=f"{self._last_record.workflow_name.lower().replace(' ', '_')}_results.csv",
            filetypes=[("CSV Files", "*.csv")],
        )
        if not dest:
            return

        try:
            saved_path = self.csv_manager.export_run_results(
                workflow_name=self._last_record.workflow_name,
                records=extracted,
                destination_path=Path(dest),
            )
            self.console_view.append_log("SUCCESS", f"Exported results to '{saved_path}'.")
            messagebox.showinfo("Export Complete", f"Saved CSV results to:\n{saved_path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Export Failed", str(exc), parent=self)


ExecutionMonitorView = ExecutionDashboardView