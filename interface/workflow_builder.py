"""Visual workflow builder, preset loader, profile manager UI, and step editor view."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import config
from actions import get_registered_action_types
from core.selector_manager import SelectorManager
from interface.components import ActionButton, CardFrame, DataTable, ScrollableFrame, StatusBadge
from interface.theme import COLORS, FONTS
from models.workflow import Workflow
from models.workflow_step import WorkflowStep
from storage.profile_manager import ProfileManager
from workflows import get_preset_workflow, list_presets

WorkflowSavedCallback = Callable[[Workflow], None]

_CONDITION_CHOICES: tuple[str, ...] = (
    getattr(config, "CONDITION_ALWAYS", "always"),
    getattr(config, "CONDITION_IF_ELEMENT_EXISTS", "if_element_exists"),
    getattr(config, "CONDITION_SKIP_IF_MISSING", "skip_if_missing"),
    getattr(config, "CONDITION_STOP_IF_MISSING", "stop_if_missing"),
)

_MODE_OPTION_CHOICES: tuple[str, ...] = (
    "",
    "visible",
    "present",
    "clickable",
    "invisible",
    "text_present",
    "url_contains",
    "page_ready",
    "bottom",
    "top",
    "by_pixels",
    "to_element",
    "visible_text",
    "value",
    "index",
)


class WorkflowBuilderView(tk.Frame):
    """Interactive no-code/low-code builder for creating, editing, validating, and saving workflows."""

    def __init__(
        self,
        master: tk.Misc,
        profile_manager: ProfileManager | None = None,
        on_workflow_saved: WorkflowSavedCallback | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(master, bg=COLORS["bg_primary"], **kwargs)
        self.profile_manager: ProfileManager = profile_manager or ProfileManager()
        self.on_workflow_saved: WorkflowSavedCallback | None = on_workflow_saved

        self.current_workflow: Workflow = Workflow(name="Untitled Workflow")
        self._selected_step_index: int | None = None
        self._preset_map: dict[str, str] = {}
        self._saved_workflow_map: dict[str, str] = {}

        # Workflow metadata variables
        self.wf_name_var = tk.StringVar(value=self.current_workflow.name)
        self.wf_url_var = tk.StringVar(value="")
        self.wf_desc_var = tk.StringVar(value="")
        self.wf_browser_var = tk.StringVar(value=config.DEFAULT_BROWSER)

        # Toolbar selector variables
        self.preset_choice_var = tk.StringVar(value="")
        self.saved_choice_var = tk.StringVar(value="")

        # Step editor variables
        self.step_name_var = tk.StringVar(value="")
        self.step_action_var = tk.StringVar(value=config.ACTION_OPEN_URL)
        self.step_strategy_var = tk.StringVar(value="css")
        self.step_selector_var = tk.StringVar(value="")
        self.step_input_var = tk.StringVar(value="")
        self.step_csv_col_var = tk.StringVar(value="")
        self.step_output_key_var = tk.StringVar(value="")
        self.step_condition_var = tk.StringVar(value=_CONDITION_CHOICES[0])
        self.step_cond_target_var = tk.StringVar(value="")
        self.step_mode_option_var = tk.StringVar(value="")
        self.step_timeout_var = tk.StringVar(value=str(int(config.DEFAULT_TIMEOUT)))
        self.step_retries_var = tk.StringVar(value=str(config.DEFAULT_MAX_RETRIES))
        self.step_approval_var = tk.BooleanVar(value=False)
        self.step_continue_err_var = tk.BooleanVar(value=False)
        self.step_extract_all_var = tk.BooleanVar(value=False)
        self.step_js_click_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._refresh_presets_dropdown()
        self._refresh_saved_dropdown()
        self._refresh_steps_table()

    def _build_ui(self) -> None:
        """Assemble the top toolbar, workflow header card, step table, and step editor."""
        # 1. Top Toolbar: Presets, Saved Profiles & Actions
        toolbar = tk.Frame(
            self,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        toolbar.pack(fill=tk.X, padx=12, pady=(12, 8))

        tk.Label(
            toolbar,
            text="Preset:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.preset_combo = ttk.Combobox(
            toolbar,
            textvariable=self.preset_choice_var,
            state="readonly",
            width=32,
        )
        self.preset_combo.pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            toolbar,
            text="Load Preset",
            command=self._on_load_preset,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 14))

        tk.Label(
            toolbar,
            text="Saved:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.saved_combo = ttk.Combobox(
            toolbar,
            textvariable=self.saved_choice_var,
            state="readonly",
            width=26,
        )
        self.saved_combo.pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            toolbar,
            text="Load",
            command=self._on_load_saved,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 4))

        ActionButton(
            toolbar,
            text="Delete",
            command=self._on_delete_saved,
            variant="danger",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 12))

        ActionButton(
            toolbar,
            text="Save Workflow",
            command=self.save_current_workflow,
            variant="success",
            padx=12,
            pady=4,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        ActionButton(
            toolbar,
            text="Validate",
            command=self._on_validate_workflow,
            variant="primary",
            padx=12,
            pady=4,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        ActionButton(
            toolbar,
            text="New Blank",
            command=self._on_new_blank,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT)

        # 2. Workflow Metadata Card
        meta_card = CardFrame(
            self,
            title="Workflow Configuration",
            subtitle="Define workflow identity, default target URL, and preferred browser driver",
            padx=12,
            pady=10,
        )
        meta_card.pack(fill=tk.X, padx=12, pady=(0, 8))

        meta_grid = tk.Frame(meta_card, bg=COLORS["bg_surface"])
        meta_grid.pack(fill=tk.X)
        meta_grid.grid_columnconfigure(1, weight=2)
        meta_grid.grid_columnconfigure(3, weight=2)
        meta_grid.grid_columnconfigure(5, weight=1)

        tk.Label(
            meta_grid,
            text="Workflow Name:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(meta_grid, textvariable=self.wf_name_var).grid(
            row=0, column=1, sticky="ew", padx=(0, 14), pady=4
        )

        tk.Label(
            meta_grid,
            text="Default Target URL:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).grid(row=0, column=2, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(meta_grid, textvariable=self.wf_url_var).grid(
            row=0, column=3, sticky="ew", padx=(0, 14), pady=4
        )

        tk.Label(
            meta_grid,
            text="Browser:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).grid(row=0, column=4, sticky="w", padx=(0, 6), pady=4)
        ttk.Combobox(
            meta_grid,
            textvariable=self.wf_browser_var,
            values=list(config.SUPPORTED_BROWSERS),
            state="readonly",
            width=12,
        ).grid(row=0, column=5, sticky="ew", pady=4)

        tk.Label(
            meta_grid,
            text="Description:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(meta_grid, textvariable=self.wf_desc_var).grid(
            row=1, column=1, columnspan=5, sticky="ew", pady=4
        )

        # 3. Main Split Workspace: Left (Steps Sequence) | Right (Step Editor)
        workspace = tk.Frame(self, bg=COLORS["bg_primary"])
        workspace.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        workspace.grid_columnconfigure(0, weight=3)
        workspace.grid_columnconfigure(1, weight=2)
        workspace.grid_rowconfigure(0, weight=1)

        # Left Panel: Steps Table & Ordering Controls
        steps_card = CardFrame(
            workspace,
            title="Action Sequence",
            subtitle="Select any step to inspect or edit its parameters on the right",
            padx=12,
            pady=10,
        )
        steps_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.steps_table = DataTable(
            steps_card,
            columns=["#", "Step Name", "Action", "Selector", "Input / CSV", "Guards"],
            height=13,
        )
        self.steps_table.set_columns(
            ["#", "Step Name", "Action", "Selector", "Input / CSV", "Guards"],
            widths={
                "#": 40,
                "Step Name": 175,
                "Action": 125,
                "Selector": 155,
                "Input / CSV": 145,
                "Guards": 115,
            },
        )
        self.steps_table.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.steps_table.tree.bind("<<TreeviewSelect>>", self._on_step_selected)

        step_btn_bar = tk.Frame(steps_card, bg=COLORS["bg_surface"])
        step_btn_bar.pack(fill=tk.X)

        ActionButton(
            step_btn_bar,
            text="Move Up",
            command=lambda: self._move_selected_step(-1),
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            step_btn_bar,
            text="Move Down",
            command=lambda: self._move_selected_step(1),
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            step_btn_bar,
            text="Duplicate",
            command=self._duplicate_selected_step,
            variant="secondary",
            padx=10,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            step_btn_bar,
            text="Remove Step",
            command=self._remove_selected_step,
            variant="danger",
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT)

        self.validation_badge = StatusBadge(step_btn_bar, status="ready", text="0 STEPS")
        self.validation_badge.pack(side=tk.RIGHT, padx=(0, 10))

        # Right Panel: Scrollable Step Inspector Form
        editor_card = CardFrame(
            workspace,
            title="Step Configuration",
            subtitle="Configure action type, selector strategy, CSV bindings, and safety rules",
            padx=12,
            pady=10,
        )
        editor_card.grid(row=0, column=1, sticky="nsew")

        scroll = ScrollableFrame(editor_card, bg=COLORS["bg_surface"])
        scroll.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        form = scroll.content
        form.grid_columnconfigure(1, weight=1)

        row_idx = 0

        def _add_field(label_text: str, widget: tk.Widget) -> None:
            nonlocal row_idx
            tk.Label(
                form,
                text=label_text,
                bg=COLORS["bg_surface"],
                fg=COLORS["text_secondary"],
                font=FONTS["small_bold"],
                anchor="w",
            ).grid(row=row_idx, column=0, sticky="w", padx=(0, 8), pady=4)
            widget.grid(row=row_idx, column=1, sticky="ew", pady=4)
            row_idx += 1

        _add_field("Step Label:", ttk.Entry(form, textvariable=self.step_name_var))

        self.action_combo = ttk.Combobox(
            form,
            textvariable=self.step_action_var,
            values=get_registered_action_types(),
            state="readonly",
        )
        _add_field("Action Type:", self.action_combo)

        self.strategy_combo = ttk.Combobox(
            form,
            textvariable=self.step_strategy_var,
            values=list(config.SELECTOR_STRATEGIES),
            state="readonly",
        )
        _add_field("Selector Strategy:", self.strategy_combo)

        _add_field("Selector Value:", ttk.Entry(form, textvariable=self.step_selector_var))
        _add_field("Input / Target Val:", ttk.Entry(form, textvariable=self.step_input_var))
        _add_field("CSV Column:", ttk.Entry(form, textvariable=self.step_csv_col_var))
        _add_field("Output Variable:", ttk.Entry(form, textvariable=self.step_output_key_var))

        self.mode_combo = ttk.Combobox(
            form,
            textvariable=self.step_mode_option_var,
            values=list(_MODE_OPTION_CHOICES),
        )
        _add_field("Action Mode:", self.mode_combo)

        self.cond_combo = ttk.Combobox(
            form,
            textvariable=self.step_condition_var,
            values=list(_CONDITION_CHOICES),
            state="readonly",
        )
        _add_field("Execution Guard:", self.cond_combo)

        _add_field("Guard Selector:", ttk.Entry(form, textvariable=self.step_cond_target_var))

        limits_row = tk.Frame(form, bg=COLORS["bg_surface"])
        ttk.Entry(limits_row, textvariable=self.step_timeout_var, width=8).pack(side=tk.LEFT)
        tk.Label(
            limits_row,
            text="s   Max Retries:",
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
        ).pack(side=tk.LEFT, padx=(6, 6))
        ttk.Entry(limits_row, textvariable=self.step_retries_var, width=6).pack(side=tk.LEFT)
        _add_field("Timeout (sec):", limits_row)

        flags_frame = tk.Frame(form, bg=COLORS["bg_surface"])
        flags_frame.grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Checkbutton(
            flags_frame,
            text="Require human approval before running this step",
            variable=self.step_approval_var,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            flags_frame,
            text="Continue workflow if this step fails",
            variable=self.step_continue_err_var,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            flags_frame,
            text="Extract all matching elements (extract_text)",
            variable=self.step_extract_all_var,
        ).pack(anchor="w", pady=2)
        ttk.Checkbutton(
            flags_frame,
            text="Force JavaScript click (click_element)",
            variable=self.step_js_click_var,
        ).pack(anchor="w", pady=2)

        editor_actions = tk.Frame(editor_card, bg=COLORS["bg_surface"])
        editor_actions.pack(fill=tk.X)

        ActionButton(
            editor_actions,
            text="+ Add As New Step",
            command=self._add_step_from_form,
            variant="primary",
            padx=12,
            pady=5,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            editor_actions,
            text="Update Selected",
            command=self._update_selected_step,
            variant="success",
            padx=12,
            pady=5,
        ).pack(side=tk.LEFT, padx=(0, 6))

        ActionButton(
            editor_actions,
            text="Reset Fields",
            command=self._reset_step_form,
            variant="secondary",
            padx=10,
            pady=5,
        ).pack(side=tk.RIGHT)

    def _refresh_presets_dropdown(self) -> None:
        """Populate the built-in workflow presets combobox."""
        presets = list_presets()
        self._preset_map = {item["name"]: item["preset_id"] for item in presets}
        names = list(self._preset_map.keys())
        self.preset_combo.configure(values=names)
        if names and not self.preset_choice_var.get():
            self.preset_choice_var.set(names[0])

    def _refresh_saved_dropdown(self) -> None:
        """Reload saved workflow profiles from `ProfileManager`."""
        self._saved_workflow_map.clear()
        workflows: list[Workflow] = []
        if hasattr(self.profile_manager, "list_profiles"):
            workflows = self.profile_manager.list_profiles()
        elif hasattr(self.profile_manager, "list_workflows"):
            workflows = self.profile_manager.list_workflows()

        for wf in workflows:
            label = f"{wf.name} ({len(wf.steps)} steps)"
            self._saved_workflow_map[label] = wf.workflow_id

        labels = list(self._saved_workflow_map.keys())
        self.saved_combo.configure(values=labels)
        if labels:
            if self.saved_choice_var.get() not in self._saved_workflow_map:
                self.saved_choice_var.set(labels[0])
        else:
            self.saved_choice_var.set("")

    def load_workflow(self, workflow: Workflow) -> None:
        """Load a `Workflow` object into the builder metadata and step sequence table."""
        self.current_workflow = workflow
        self._selected_step_index = None
        self.wf_name_var.set(workflow.name)
        self.wf_url_var.set(workflow.target_url)
        self.wf_desc_var.set(workflow.description)
        self.wf_browser_var.set(getattr(workflow, "browser", "") or config.DEFAULT_BROWSER)
        self._refresh_steps_table()
        self._reset_step_form()

    def _sync_metadata_to_workflow(self) -> None:
        """Copy metadata UI fields onto `self.current_workflow`."""
        self.current_workflow.name = self.wf_name_var.get().strip() or "Untitled Workflow"
        self.current_workflow.target_url = self.wf_url_var.get().strip()
        self.current_workflow.description = self.wf_desc_var.get().strip()
        if hasattr(self.current_workflow, "browser"):
            self.current_workflow.browser = self.wf_browser_var.get().strip() or config.DEFAULT_BROWSER

    def _refresh_steps_table(self) -> None:
        """Render `self.current_workflow.steps` into the steps `DataTable`."""
        rows: list[dict[str, str]] = []
        for idx, step in enumerate(self.current_workflow.steps, start=1):
            selector_desc = (
                f"[{step.selector_strategy}] {step.selector_value}"
                if step.selector_value.strip()
                else "-"
            )
            if step.csv_column.strip():
                input_desc = f"{{CSV: {step.csv_column.strip()}}}"
            elif step.input_value.strip():
                input_desc = step.input_value.strip()
            else:
                input_desc = "-"

            guards: list[str] = []
            if step.condition and step.condition != getattr(config, "CONDITION_ALWAYS", "always"):
                guards.append(step.condition)
            if step.requires_approval:
                guards.append("approval")
            if bool(step.options.get("continue_on_error", False)):
                guards.append("continue_err")

            rows.append(
                {
                    "#": str(idx),
                    "Step Name": step.display_name,
                    "Action": step.action_type,
                    "Selector": selector_desc,
                    "Input / CSV": input_desc,
                    "Guards": ", ".join(guards) if guards else "none",
                }
            )

        self.steps_table.set_rows(rows)
        count = len(self.current_workflow.steps)
        self.validation_badge.set_status(
            "completed" if count > 0 else "ready",
            text=f"{count} STEP{'S' if count != 1 else ''}",
        )

    def _build_step_from_form(self, existing_step: WorkflowStep | None = None) -> WorkflowStep:
        """Construct and validate a `WorkflowStep` from the right-hand editor fields."""
        action_type = self.step_action_var.get().strip()
        strategy = self.step_strategy_var.get().strip() or "css"
        selector_val = self.step_selector_var.get().strip()
        input_val = self.step_input_var.get()
        csv_col = self.step_csv_col_var.get().strip()
        output_key = self.step_output_key_var.get().strip()
        condition = self.step_condition_var.get().strip() or getattr(
            config, "CONDITION_ALWAYS", "always"
        )
        cond_target = self.step_cond_target_var.get().strip()

        if selector_val:
            ok, msg = SelectorManager.validate_selector_syntax(strategy, selector_val)
            if not ok:
                raise ValueError(msg)

        try:
            timeout_val = float(self.step_timeout_var.get().strip() or config.DEFAULT_TIMEOUT)
        except ValueError as exc:
            raise ValueError("Timeout must be a valid number of seconds.") from exc
        timeout_val = max(config.MIN_TIMEOUT, min(timeout_val, config.MAX_TIMEOUT))

        try:
            retries_val = int(self.step_retries_var.get().strip() or config.DEFAULT_MAX_RETRIES)
        except ValueError as exc:
            raise ValueError("Max Retries must be a whole number.") from exc
        retries_val = max(config.MIN_RETRIES, min(retries_val, config.MAX_RETRIES))

        options: dict[str, Any] = dict(existing_step.options) if existing_step else {}
        mode_val = self.step_mode_option_var.get().strip()
        if mode_val:
            if action_type == getattr(config, "ACTION_WAIT", "wait"):
                options["wait_condition"] = mode_val
            elif action_type == config.ACTION_SCROLL:
                options["scroll_mode"] = mode_val
            elif action_type == config.ACTION_SELECT_OPTION:
                options["select_mode"] = mode_val
        else:
            options.pop("wait_condition", None)
            options.pop("scroll_mode", None)
            options.pop("select_mode", None)

        if self.step_continue_err_var.get():
            options["continue_on_error"] = True
        else:
            options.pop("continue_on_error", None)

        if self.step_extract_all_var.get():
            options["extract_all"] = True
        else:
            options.pop("extract_all", None)

        if self.step_js_click_var.get():
            options["js_click"] = True
        else:
            options.pop("js_click", None)

        step = WorkflowStep(
            name=self.step_name_var.get().strip(),
            action_type=action_type,
            selector_strategy=strategy,
            selector_value=selector_val,
            input_value=input_val,
            csv_column=csv_col,
            output_key=output_key,
            condition=condition,
            condition_target=cond_target,
            requires_approval=bool(self.step_approval_var.get()),
            timeout=timeout_val,
            max_retries=retries_val,
            options=options,
        )
        if existing_step is not None:
            step.step_id = existing_step.step_id
        return step

    def _populate_form_from_step(self, step: WorkflowStep) -> None:
        """Load a `WorkflowStep`'s attributes into the editor controls."""
        self.step_name_var.set(step.name)
        self.step_action_var.set(step.action_type)
        self.step_strategy_var.set(step.selector_strategy)
        self.step_selector_var.set(step.selector_value)
        self.step_input_var.set(step.input_value)
        self.step_csv_col_var.set(step.csv_column)
        self.step_output_key_var.set(step.output_key)
        self.step_condition_var.set(step.condition or _CONDITION_CHOICES[0])
        self.step_cond_target_var.set(step.condition_target)
        self.step_timeout_var.set(str(step.timeout))
        self.step_retries_var.set(str(step.max_retries))
        self.step_approval_var.set(bool(step.requires_approval))
        self.step_continue_err_var.set(bool(step.options.get("continue_on_error", False)))
        self.step_extract_all_var.set(bool(step.options.get("extract_all", False)))
        self.step_js_click_var.set(bool(step.options.get("js_click", False)))

        mode_val = (
            step.options.get("wait_condition")
            or step.options.get("scroll_mode")
            or step.options.get("select_mode")
            or ""
        )
        self.step_mode_option_var.set(str(mode_val))

    def _reset_step_form(self) -> None:
        """Clear step editor inputs back to clean defaults."""
        self._selected_step_index = None
        self.step_name_var.set("")
        self.step_action_var.set(config.ACTION_OPEN_URL)
        self.step_strategy_var.set("css")
        self.step_selector_var.set("")
        self.step_input_var.set("")
        self.step_csv_col_var.set("")
        self.step_output_key_var.set("")
        self.step_condition_var.set(_CONDITION_CHOICES[0])
        self.step_cond_target_var.set("")
        self.step_mode_option_var.set("")
        self.step_timeout_var.set(str(int(config.DEFAULT_TIMEOUT)))
        self.step_retries_var.set(str(config.DEFAULT_MAX_RETRIES))
        self.step_approval_var.set(False)
        self.step_continue_err_var.set(False)
        self.step_extract_all_var.set(False)
        self.step_js_click_var.set(False)

    def _on_step_selected(self, _event: tk.Event[Any]) -> None:
        idx = self.steps_table.get_selected_index()
        if idx is None or idx < 0 or idx >= len(self.current_workflow.steps):
            return
        self._selected_step_index = idx
        self._populate_form_from_step(self.current_workflow.steps[idx])

    def _add_step_from_form(self) -> None:
        try:
            new_step = self._build_step_from_form()
        except ValueError as exc:
            messagebox.showerror("Invalid Step Configuration", str(exc), parent=self)
            return

        self.current_workflow.steps.append(new_step)
        self._refresh_steps_table()
        self._selected_step_index = len(self.current_workflow.steps) - 1

    def _update_selected_step(self) -> None:
        if self._selected_step_index is None or not (
            0 <= self._selected_step_index < len(self.current_workflow.steps)
        ):
            messagebox.showinfo(
                "No Step Selected",
                "Select an existing step from the sequence table first, or click '+ Add As New Step'.",
                parent=self,
            )
            return

        existing = self.current_workflow.steps[self._selected_step_index]
        try:
            updated = self._build_step_from_form(existing_step=existing)
        except ValueError as exc:
            messagebox.showerror("Invalid Step Configuration", str(exc), parent=self)
            return

        self.current_workflow.steps[self._selected_step_index] = updated
        self._refresh_steps_table()

    def _move_selected_step(self, delta: int) -> None:
        idx = self.steps_table.get_selected_index()
        if idx is None:
            return
        new_idx = idx + delta
        steps = self.current_workflow.steps
        if not (0 <= new_idx < len(steps)):
            return
        steps[idx], steps[new_idx] = steps[new_idx], steps[idx]
        self._selected_step_index = new_idx
        self._refresh_steps_table()
        children = self.steps_table.tree.get_children()
        if 0 <= new_idx < len(children):
            self.steps_table.tree.selection_set(children[new_idx])

    def _duplicate_selected_step(self) -> None:
        idx = self.steps_table.get_selected_index()
        if idx is None or not (0 <= idx < len(self.current_workflow.steps)):
            return
        cloned = self.current_workflow.steps[idx].clone()
        cloned.name = f"{cloned.display_name} (Copy)"
        self.current_workflow.steps.insert(idx + 1, cloned)
        self._refresh_steps_table()

    def _remove_selected_step(self) -> None:
        idx = self.steps_table.get_selected_index()
        if idx is None or not (0 <= idx < len(self.current_workflow.steps)):
            return
        self.current_workflow.steps.pop(idx)
        self._selected_step_index = None
        self._refresh_steps_table()

    def _on_new_blank(self) -> None:
        self.load_workflow(Workflow(name="Untitled Workflow"))

    def _on_load_preset(self) -> None:
        chosen_name = self.preset_choice_var.get().strip()
        preset_id = self._preset_map.get(chosen_name)
        if not preset_id:
            return
        wf = get_preset_workflow(preset_id)
        self.load_workflow(wf)

    def _on_load_saved(self) -> None:
        chosen_label = self.saved_choice_var.get().strip()
        wf_id = self._saved_workflow_map.get(chosen_label)
        if not wf_id:
            return

        loaded: Workflow | None = None
        if hasattr(self.profile_manager, "get_workflow"):
            loaded = self.profile_manager.get_workflow(wf_id)
        elif hasattr(self.profile_manager, "load_workflow"):
            loaded = self.profile_manager.load_workflow(wf_id)

        if loaded is not None:
            self.load_workflow(loaded)

    def _on_delete_saved(self) -> None:
        chosen_label = self.saved_choice_var.get().strip()
        wf_id = self._saved_workflow_map.get(chosen_label)
        if not wf_id:
            return
        if not messagebox.askyesno(
            "Delete Saved Workflow",
            f"Delete saved workflow profile '{chosen_label}'?",
            parent=self,
        ):
            return
        if hasattr(self.profile_manager, "delete_workflow"):
            self.profile_manager.delete_workflow(wf_id)
        self._refresh_saved_dropdown()

    def _on_validate_workflow(self) -> None:
        self._sync_metadata_to_workflow()
        if not self.current_workflow.steps:
            self.validation_badge.set_status("warning", text="NO STEPS")
            messagebox.showwarning(
                "Validation Warning",
                "Add at least one action step before running or saving.",
                parent=self,
            )
            return

        issues = SelectorManager.validate_workflow_selectors(self.current_workflow)
        if issues:
            self.validation_badge.set_status("error", text=f"{len(issues)} ISSUE(S)")
            formatted = "\n".join(
                f"• Step {item['step_index']} ({item['step_name']}): {item['message']}"
                for item in issues
            )
            messagebox.showerror("Selector Validation Issues", formatted, parent=self)
            return

        self.validation_badge.set_status("completed", text="VALIDATED")
        messagebox.showinfo(
            "Workflow Validated",
            f"All {len(self.current_workflow.steps)} step(s) passed pre-flight syntax checks.",
            parent=self,
        )

    def save_current_workflow(self) -> Workflow | None:
        """Persist `self.current_workflow` via `ProfileManager` and notify listeners."""
        self._sync_metadata_to_workflow()
        if not self.current_workflow.steps:
            messagebox.showwarning(
                "Cannot Save Empty Workflow",
                "Add at least one action step before saving.",
                parent=self,
            )
            return None

        if hasattr(self.profile_manager, "save_workflow"):
            self.current_workflow.is_template = False
            self.profile_manager.save_workflow(self.current_workflow)

        self._refresh_saved_dropdown()
        self.validation_badge.set_status("completed", text="SAVED")

        if callable(self.on_workflow_saved):
            self.on_workflow_saved(self.current_workflow)

        return self.current_workflow