"""Data model and parameter validation for an individual Nexora workflow step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import config


def _generate_step_id() -> str:
    """Return a short unique identifier for a workflow step."""
    return f"step_{uuid4().hex[:8]}"


@dataclass
class WorkflowStep:
    """Represents a single configurable browser action within a workflow."""

    step_id: str = field(default_factory=_generate_step_id)
    name: str = ""
    action_type: str = config.ACTION_OPEN_URL
    selector_strategy: str = "css"
    selector_value: str = ""
    input_value: str = ""
    condition: str = config.CONDITION_ALWAYS
    condition_target: str = ""
    timeout: float = config.DEFAULT_TIMEOUT
    max_retries: int = config.DEFAULT_MAX_RETRIES
    requires_approval: bool = False
    csv_column: str = ""
    output_key: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Return custom step title or fallback human-readable action label."""
        cleaned = self.name.strip()
        if cleaned:
            return cleaned
        return config.ACTION_LABELS.get(self.action_type, self.action_type)

    def summary(self) -> str:
        """Return a concise single-line summary for dry-run previews and UI lists."""
        label = self.display_name
        detail = ""

        if self.action_type == config.ACTION_OPEN_URL:
            detail = self.input_value.strip()
        elif self.action_type == config.ACTION_ENTER_TEXT:
            source = f"{{{{{self.csv_column.strip()}}}}}" if self.csv_column.strip() else repr(self.input_value)
            detail = f"{source} -> [{self.selector_strategy}: {self.selector_value.strip()}]"
        elif self.action_type in (
            config.ACTION_CLICK_ELEMENT,
            config.ACTION_SELECT_OPTION,
            config.ACTION_EXTRACT_TEXT,
            config.ACTION_DOWNLOAD_FILE,
        ):
            detail = f"[{self.selector_strategy}: {self.selector_value.strip()}]"
            if self.action_type == config.ACTION_SELECT_OPTION and self.input_value.strip():
                detail = f"{repr(self.input_value.strip())} in {detail}"
        elif self.action_type == config.ACTION_WAIT:
            wait_mode = str(self.options.get("wait_condition", config.DEFAULT_WAIT_CONDITION))
            target = (
                self.input_value.strip()
                if wait_mode in ("text_present", "url_contains")
                else f"[{self.selector_strategy}: {self.selector_value.strip()}]"
            )
            detail = f"{wait_mode}: {target}"
        elif self.action_type == config.ACTION_SCROLL:
            scroll_mode = str(self.options.get("scroll_mode", config.DEFAULT_SCROLL_MODE))
            detail = scroll_mode
            if scroll_mode == "to_element":
                detail = f"to [{self.selector_strategy}: {self.selector_value.strip()}]"
            elif scroll_mode == "by_pixels" and self.input_value.strip():
                detail = f"by {self.input_value.strip()}px"
        elif self.action_type == config.ACTION_EXTRACT_LINKS and self.selector_value.strip():
            detail = f"within [{self.selector_strategy}: {self.selector_value.strip()}]"

        parts = [label]
        if detail:
            parts.append(f"({detail})")
        if self.condition != config.CONDITION_ALWAYS:
            parts.append(f"[if: {self.condition}]")
        if self.requires_approval:
            parts.append("[APPROVAL REQUIRED]")
        return " ".join(parts)

    def validate(self) -> list[str]:
        """Validate step configuration and return a list of human-readable error strings."""
        errors: list[str] = []

        if self.action_type not in config.SUPPORTED_ACTIONS:
            errors.append(f"Unsupported action type: '{self.action_type}'.")
            return errors

        selector_val = self.selector_value.strip()
        input_val = self.input_value.strip()
        csv_col = self.csv_column.strip()
        cond_target = self.condition_target.strip()

        # Selector requirement checks
        requires_selector = self.action_type in config.ACTIONS_REQUIRING_SELECTOR
        if self.action_type == config.ACTION_WAIT:
            wait_mode = str(self.options.get("wait_condition", config.DEFAULT_WAIT_CONDITION))
            if wait_mode not in config.WAIT_CONDITIONS:
                errors.append(f"Invalid wait condition: '{wait_mode}'.")
            elif wait_mode in ("present", "visible", "clickable", "invisible"):
                requires_selector = True
            elif not input_val:
                errors.append(f"Wait condition '{wait_mode}' requires a target text or URL value.")

        if self.action_type == config.ACTION_SCROLL:
            scroll_mode = str(self.options.get("scroll_mode", config.DEFAULT_SCROLL_MODE))
            if scroll_mode not in config.SCROLL_MODES:
                errors.append(f"Invalid scroll mode: '{scroll_mode}'.")
            elif scroll_mode == "to_element":
                requires_selector = True
            elif scroll_mode == "by_pixels" and input_val and "{{" not in input_val:
                try:
                    int(input_val)
                except ValueError:
                    errors.append("Scroll 'by_pixels' value must be an integer (e.g., 500 or -300).")

        if requires_selector or selector_val:
            if self.selector_strategy not in config.SELECTOR_STRATEGIES:
                errors.append(f"Unsupported selector strategy: '{self.selector_strategy}'.")
        if requires_selector and not selector_val:
            errors.append(
                f"Action '{config.ACTION_LABELS.get(self.action_type, self.action_type)}' requires a selector value."
            )

        # Value & URL checks
        if self.action_type in config.ACTIONS_REQUIRING_VALUE and not input_val:
            errors.append(
                f"Action '{config.ACTION_LABELS.get(self.action_type, self.action_type)}' requires an input value."
            )

        if self.action_type == config.ACTION_OPEN_URL and input_val and "{{" not in input_val:
            lowered = input_val.lower()
            if not (lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("file://")):
                errors.append("Open URL target must start with 'http://', 'https://', or 'file://'.")

        if self.action_type == config.ACTION_ENTER_TEXT and not input_val and not csv_col:
            errors.append("Enter Text requires either static input text or a mapped CSV column.")

        if self.action_type == config.ACTION_SELECT_OPTION:
            select_mode = str(self.options.get("select_mode", config.DEFAULT_SELECT_MODE))
            if select_mode not in config.SELECT_MODES:
                errors.append(f"Invalid select mode: '{select_mode}'.")
            elif select_mode == "index" and input_val and "{{" not in input_val:
                try:
                    idx = int(input_val)
                    if idx < 0:
                        errors.append("Select option index must be 0 or greater.")
                except ValueError:
                    errors.append("Select option index must be a non-negative integer.")

        # Conditional execution checks
        if self.condition not in config.STEP_CONDITIONS:
            errors.append(f"Unsupported step condition: '{self.condition}'.")
        elif self.condition == config.CONDITION_IF_TEXT_PRESENT and not cond_target:
            errors.append("Condition 'if_text_present' requires target text in 'condition_target'.")
        elif self.condition in (
            config.CONDITION_IF_ELEMENT_EXISTS,
            config.CONDITION_SKIP_IF_MISSING,
            config.CONDITION_STOP_IF_MISSING,
        ):
            if not cond_target and not selector_val:
                errors.append(
                    f"Condition '{self.condition}' requires a selector in 'condition_target' or 'selector_value'."
                )

        # Timeout & retry bounds
        try:
            timeout_val = float(self.timeout)
            if not (config.MIN_TIMEOUT <= timeout_val <= config.MAX_TIMEOUT):
                errors.append(
                    f"Timeout must be between {config.MIN_TIMEOUT}s and {config.MAX_TIMEOUT}s."
                )
        except (TypeError, ValueError):
            errors.append("Timeout must be a valid number.")

        try:
            retries_val = int(self.max_retries)
            if not (config.MIN_RETRIES <= retries_val <= config.MAX_RETRIES):
                errors.append(
                    f"Max retries must be between {config.MIN_RETRIES} and {config.MAX_RETRIES}."
                )
        except (TypeError, ValueError):
            errors.append("Max retries must be an integer.")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize step attributes into a JSON-compatible dictionary."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "action_type": self.action_type,
            "selector_strategy": self.selector_strategy,
            "selector_value": self.selector_value,
            "input_value": self.input_value,
            "condition": self.condition,
            "condition_target": self.condition_target,
            "timeout": float(self.timeout),
            "max_retries": int(self.max_retries),
            "requires_approval": bool(self.requires_approval),
            "csv_column": self.csv_column,
            "output_key": self.output_key,
            "options": dict(self.options),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        """Deserialize a WorkflowStep from a dictionary with safe type coercion."""
        raw_options = data.get("options")
        options = dict(raw_options) if isinstance(raw_options, dict) else {}

        try:
            timeout = float(data.get("timeout", config.DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            timeout = config.DEFAULT_TIMEOUT

        try:
            max_retries = int(data.get("max_retries", config.DEFAULT_MAX_RETRIES))
        except (TypeError, ValueError):
            max_retries = config.DEFAULT_MAX_RETRIES

        return cls(
            step_id=str(data.get("step_id") or _generate_step_id()),
            name=str(data.get("name", "")),
            action_type=str(data.get("action_type", config.ACTION_OPEN_URL)),
            selector_strategy=str(data.get("selector_strategy", "css")),
            selector_value=str(data.get("selector_value", "")),
            input_value=str(data.get("input_value", "")),
            condition=str(data.get("condition", config.CONDITION_ALWAYS)),
            condition_target=str(data.get("condition_target", "")),
            timeout=timeout,
            max_retries=max_retries,
            requires_approval=bool(data.get("requires_approval", False)),
            csv_column=str(data.get("csv_column", "")),
            output_key=str(data.get("output_key", "")),
            options=options,
        )

    def clone(self) -> WorkflowStep:
        """Create an independent copy of this step with a new step_id."""
        payload = self.to_dict()
        payload["step_id"] = _generate_step_id()
        return WorkflowStep.from_dict(payload)