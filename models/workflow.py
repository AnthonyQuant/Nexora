"""Workflow profile data model supporting ordered steps, CSV mappings, and JSON persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any
from uuid import uuid4

import config
from models.workflow_step import WorkflowStep

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_workflow_id() -> str:
    """Return a short unique identifier for a workflow profile."""
    return f"wf_{uuid4().hex[:8]}"


def _default_browser_options() -> dict[str, Any]:
    """Return default browser session settings for a workflow."""
    return {
        "browser": config.DEFAULT_BROWSER,
        "headless": config.DEFAULT_HEADLESS,
        "timeout": config.DEFAULT_TIMEOUT,
    }


@dataclass
class Workflow:
    """Represents a reusable, JSON-serializable browser automation workflow."""

    workflow_id: str = field(default_factory=_generate_workflow_id)
    name: str = "Untitled Workflow"
    description: str = ""
    category: str = "General"
    target_url: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    csv_mappings: dict[str, str] = field(default_factory=dict)
    browser_options: dict[str, Any] = field(default_factory=_default_browser_options)
    is_template: bool = False
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    @property
    def step_count(self) -> int:
        """Return the number of configured steps in this workflow."""
        return len(self.steps)

    def touch(self) -> None:
        """Update the modification timestamp to the current UTC time."""
        self.updated_at = _utc_now_iso()

    def add_step(self, step: WorkflowStep, index: int | None = None) -> None:
        """Append a step or insert it at a specific 0-based index."""
        if index is None or index >= len(self.steps):
            self.steps.append(step)
        else:
            safe_index = max(0, index)
            self.steps.insert(safe_index, step)
        self.touch()

    def update_step(self, index: int, step: WorkflowStep) -> None:
        """Replace an existing step at the given 0-based index."""
        if not (0 <= index < len(self.steps)):
            raise IndexError(f"Step index {index} out of range for workflow '{self.name}'.")
        self.steps[index] = step
        self.touch()

    def remove_step(self, index: int) -> WorkflowStep:
        """Remove and return the step at the given 0-based index."""
        if not (0 <= index < len(self.steps)):
            raise IndexError(f"Step index {index} out of range for workflow '{self.name}'.")
        removed = self.steps.pop(index)
        self.touch()
        return removed

    def move_step(self, from_index: int, to_index: int) -> bool:
        """Move a step from `from_index` to `to_index`. Returns True if moved."""
        if not (0 <= from_index < len(self.steps)) or not (0 <= to_index < len(self.steps)):
            return False
        if from_index == to_index:
            return False
        step = self.steps.pop(from_index)
        self.steps.insert(to_index, step)
        self.touch()
        return True

    def move_step_up(self, index: int) -> bool:
        """Move the step at `index` one position earlier in the sequence."""
        return self.move_step(index, index - 1)

    def move_step_down(self, index: int) -> bool:
        """Move the step at `index` one position later in the sequence."""
        return self.move_step(index, index + 1)

    def get_step(self, index: int) -> WorkflowStep | None:
        """Safely retrieve a step by 0-based index, or None if out of bounds."""
        if 0 <= index < len(self.steps):
            return self.steps[index]
        return None

    def steps_requiring_approval(self) -> list[tuple[int, WorkflowStep]]:
        """Return (1-based step number, WorkflowStep) pairs flagged for manual approval."""
        return [
            (idx, step)
            for idx, step in enumerate(self.steps, start=1)
            if step.requires_approval
        ]

    def get_required_csv_columns(self) -> list[str]:
        """Return an ordered, deduplicated list of CSV columns referenced by this workflow."""
        ordered_columns: list[str] = []
        seen: set[str] = set()

        def _register(col_name: str) -> None:
            cleaned = col_name.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                ordered_columns.append(cleaned)

        for col in self.csv_mappings.keys():
            _register(col)

        for match in _PLACEHOLDER_PATTERN.findall(self.target_url):
            _register(match)

        for step in self.steps:
            if step.csv_column:
                _register(step.csv_column)
            for text_field in (step.input_value, step.selector_value, step.condition_target):
                for match in _PLACEHOLDER_PATTERN.findall(text_field):
                    _register(match)

        return ordered_columns

    def validate(self) -> list[str]:
        """Validate workflow metadata, browser options, and every step configuration."""
        errors: list[str] = []

        if not self.name or not self.name.strip():
            errors.append("Workflow name cannot be empty.")

        url_val = self.target_url.strip()
        if url_val and "{{" not in url_val:
            lowered = url_val.lower()
            if not (lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("file://")):
                errors.append("Default target URL must start with 'http://', 'https://', or 'file://'.")

        browser_name = str(self.browser_options.get("browser", config.DEFAULT_BROWSER)).lower()
        if browser_name not in config.SUPPORTED_BROWSERS:
            errors.append(
                f"Unsupported browser '{browser_name}'. Choose from: {', '.join(config.SUPPORTED_BROWSERS)}."
            )

        if not self.steps:
            errors.append("Workflow must contain at least one action step.")
        else:
            for idx, step in enumerate(self.steps, start=1):
                step_errors = step.validate()
                for err in step_errors:
                    errors.append(f"Step {idx} ({step.display_name}): {err}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize the workflow and its ordered steps into a JSON-compatible dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "target_url": self.target_url,
            "steps": [step.to_dict() for step in self.steps],
            "csv_mappings": dict(self.csv_mappings),
            "browser_options": dict(self.browser_options),
            "is_template": bool(self.is_template),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        """Deserialize a Workflow from a dictionary with safe defaults."""
        raw_steps = data.get("steps")
        steps: list[WorkflowStep] = []
        if isinstance(raw_steps, list):
            for item in raw_steps:
                if isinstance(item, WorkflowStep):
                    steps.append(item)
                elif isinstance(item, dict):
                    steps.append(WorkflowStep.from_dict(item))

        raw_mappings = data.get("csv_mappings")
        csv_mappings = (
            {str(k): str(v) for k, v in raw_mappings.items()}
            if isinstance(raw_mappings, dict)
            else {}
        )

        merged_options = _default_browser_options()
        raw_options = data.get("browser_options")
        if isinstance(raw_options, dict):
            merged_options.update(raw_options)

        now_iso = _utc_now_iso()
        return cls(
            workflow_id=str(data.get("workflow_id") or _generate_workflow_id()),
            name=str(data.get("name") or "Untitled Workflow"),
            description=str(data.get("description", "")),
            category=str(data.get("category") or "General"),
            target_url=str(data.get("target_url", "")),
            steps=steps,
            csv_mappings=csv_mappings,
            browser_options=merged_options,
            is_template=bool(data.get("is_template", False)),
            created_at=str(data.get("created_at") or now_iso),
            updated_at=str(data.get("updated_at") or now_iso),
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialize the workflow to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, raw_json: str) -> Workflow:
        """Parse a JSON string into a Workflow instance."""
        payload = json.loads(raw_json)
        if not isinstance(payload, dict):
            raise ValueError("Workflow JSON root must be an object.")
        return cls.from_dict(payload)

    def clone(self, new_name: str | None = None, as_template: bool = False) -> Workflow:
        """Create an independent copy of this workflow with fresh IDs and timestamps."""
        now_iso = _utc_now_iso()
        cloned_steps = [step.clone() for step in self.steps]
        return Workflow(
            workflow_id=_generate_workflow_id(),
            name=(new_name.strip() if new_name and new_name.strip() else f"{self.name} (Copy)"),
            description=self.description,
            category=self.category,
            target_url=self.target_url,
            steps=cloned_steps,
            csv_mappings=dict(self.csv_mappings),
            browser_options=dict(self.browser_options),
            is_template=as_template,
            created_at=now_iso,
            updated_at=now_iso,
        )