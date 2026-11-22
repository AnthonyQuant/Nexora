"""JSON workflow profile storage, template seeding, and import/export management."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import config
from models.workflow import Workflow

_SAFE_FILENAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
_DEMO_SCHEME_PREFIX = "demo://"


def _slugify(name: str, fallback: str = "workflow") -> str:
    """Convert a workflow name into a safe filesystem slug."""
    cleaned = _SAFE_FILENAME_PATTERN.sub("_", name.strip().lower()).strip("_")
    return cleaned[:48] or fallback


def _resolve_demo_uri(raw_value: str, demo_dir: Path | None = None) -> str:
    """Resolve portable `demo://<page.html>` references to local `file://` URIs."""
    text = raw_value.strip()
    if not text.lower().startswith(_DEMO_SCHEME_PREFIX):
        return raw_value
    page_name = text[len(_DEMO_SCHEME_PREFIX) :].lstrip("/") or "index.html"
    if demo_dir is not None:
        return (demo_dir / page_name).resolve().as_uri()
    return config.get_demo_url(page_name)


class ProfileManager:
    """Manages saving, loading, duplicating, deleting, and seeding JSON workflows."""

    def __init__(
        self,
        profiles_dir: Path | None = None,
        sample_workflows_path: Path | None = None,
        demo_dir: Path | None = None,
    ) -> None:
        self.profiles_dir: Path = Path(profiles_dir) if profiles_dir else config.PROFILES_DIR
        self.sample_workflows_path: Path = (
            Path(sample_workflows_path) if sample_workflows_path else config.SAMPLE_WORKFLOWS_PATH
        )
        self.demo_dir: Path = Path(demo_dir) if demo_dir else config.DEMO_SITE_DIR
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def _hydrate_demo_paths(self, workflow: Workflow) -> Workflow:
        """Resolve any portable `demo://` URLs inside a workflow to local file URIs."""
        if workflow.target_url:
            workflow.target_url = _resolve_demo_uri(workflow.target_url, self.demo_dir)
        for step in workflow.steps:
            if step.action_type == config.ACTION_OPEN_URL and step.input_value:
                step.input_value = _resolve_demo_uri(step.input_value, self.demo_dir)
        return workflow

    def _find_existing_file_by_id(self, workflow_id: str) -> Path | None:
        """Locate an existing JSON profile file matching `workflow_id`."""
        if not self.profiles_dir.exists():
            return None
        for file_path in sorted(self.profiles_dir.glob("*.json")):
            if workflow_id in file_path.stem:
                return file_path
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("workflow_id") == workflow_id:
                    return file_path
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def _build_profile_path(self, workflow: Workflow) -> Path:
        """Construct a deterministic JSON file path for a workflow profile."""
        slug = _slugify(workflow.name, fallback=workflow.workflow_id)
        return self.profiles_dir / f"{slug}_{workflow.workflow_id}.json"

    def save_workflow(self, workflow: Workflow, update_timestamp: bool = True) -> Path:
        """Persist a Workflow as a formatted JSON file in `profiles_dir`."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        if update_timestamp:
            workflow.touch()

        existing_path = self._find_existing_file_by_id(workflow.workflow_id)
        target_path = self._build_profile_path(workflow)

        target_path.write_text(workflow.to_json(indent=2), encoding="utf-8")
        if existing_path and existing_path.resolve() != target_path.resolve() and existing_path.exists():
            existing_path.unlink(missing_ok=True)

        return target_path

    def load_workflow_file(self, file_path: Path | str) -> Workflow:
        """Read and deserialize a single workflow JSON file."""
        path = Path(file_path)
        raw_text = path.read_text(encoding="utf-8")
        workflow = Workflow.from_json(raw_text)
        return self._hydrate_demo_paths(workflow)

    def list_profiles(self) -> list[Workflow]:
        """Return all saved user workflow profiles sorted by name."""
        if not self.profiles_dir.exists():
            return []

        profiles: list[Workflow] = []
        for file_path in sorted(self.profiles_dir.glob("*.json")):
            try:
                workflow = self.load_workflow_file(file_path)
                profiles.append(workflow)
            except (OSError, ValueError, json.JSONDecodeError):
                continue

        profiles.sort(key=lambda wf: wf.name.lower())
        return profiles

    def load_templates(self) -> list[Workflow]:
        """Load predefined workflow templates from `sample_workflows.json`."""
        if not self.sample_workflows_path.exists():
            return []

        raw_text = self.sample_workflows_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return []

        try:
            payload: Any = json.loads(raw_text)
        except json.JSONDecodeError:
            return []

        if isinstance(payload, dict):
            raw_list = payload.get("workflows", [])
        elif isinstance(payload, list):
            raw_list = payload
        else:
            return []

        templates: list[Workflow] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            wf = Workflow.from_dict(item)
            wf.is_template = True
            templates.append(self._hydrate_demo_paths(wf))

        return templates

    def list_all_workflows(self, include_templates: bool = True) -> list[Workflow]:
        """Return saved user profiles, optionally followed by uncloned sample templates."""
        profiles = self.list_profiles()
        if not include_templates:
            return profiles

        existing_ids = {wf.workflow_id for wf in profiles}
        combined = list(profiles)
        for template in self.load_templates():
            if template.workflow_id not in existing_ids:
                combined.append(template)
        return combined

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Retrieve a workflow by `workflow_id` across saved profiles and templates."""
        for wf in self.list_profiles():
            if wf.workflow_id == workflow_id:
                return wf
        for tpl in self.load_templates():
            if tpl.workflow_id == workflow_id:
                return tpl
        return None

    def get_workflow_by_name(self, name: str) -> Workflow | None:
        """Retrieve the first workflow matching `name` (case-insensitive)."""
        target = name.strip().lower()
        if not target:
            return None
        for wf in self.list_all_workflows(include_templates=True):
            if wf.name.strip().lower() == target:
                return wf
        return None

    def duplicate_workflow(self, workflow_id: str, new_name: str | None = None) -> Workflow:
        """Clone an existing profile or template and save it as a user profile."""
        source = self.get_workflow(workflow_id)
        if source is None:
            raise KeyError(f"Workflow '{workflow_id}' was not found.")
        cloned = source.clone(new_name=new_name, as_template=False)
        self.save_workflow(cloned, update_timestamp=False)
        return cloned

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a saved user profile by `workflow_id`. Returns True if removed."""
        existing_path = self._find_existing_file_by_id(workflow_id)
        if existing_path and existing_path.exists():
            existing_path.unlink()
            return True
        return False

    def export_workflow(self, workflow_id: str, destination_path: Path | str) -> Path:
        """Export a workflow profile or template to an arbitrary JSON file path."""
        workflow = self.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(f"Workflow '{workflow_id}' was not found.")
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(workflow.to_json(indent=2), encoding="utf-8")
        return dest

    def import_workflow(self, source_path: Path | str, assign_new_id: bool = True) -> Workflow:
        """Import a workflow JSON file into `profiles_dir` and return the saved Workflow."""
        imported = self.load_workflow_file(source_path)
        if assign_new_id:
            imported = imported.clone(new_name=imported.name, as_template=False)
        else:
            imported.is_template = False
        self.save_workflow(imported, update_timestamp=True)
        return imported

    def seed_default_profiles(self, overwrite: bool = False) -> list[Workflow]:
        """Populate `profiles_dir` with starter profiles from `sample_workflows.json` if empty."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        existing_files = list(self.profiles_dir.glob("*.json"))
        if existing_files and not overwrite:
            return self.list_profiles()

        seeded: list[Workflow] = []
        for template in self.load_templates():
            profile = template.clone(new_name=template.name, as_template=False)
            self.save_workflow(profile, update_timestamp=False)
            seeded.append(profile)
        return seeded