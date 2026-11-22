"""Browser file download trigger, completion polling, and file organization actions."""

from __future__ import annotations

from pathlib import Path
import re
import threading
import time
from typing import Any

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.remote.webdriver import WebDriver

import config
from actions.base_action import ActionOutcome, BaseAction
from actions.waiting import WaitHandler, clamp_timeout
from core.selector_manager import SelectorManager
from models.workflow_step import WorkflowStep

_TEMP_DOWNLOAD_SUFFIXES: tuple[str, ...] = (".crdownload", ".part", ".tmp", ".download")
_UNSAFE_NAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_POLL_INTERVAL: float = 0.25


def _snapshot_directory(directory: Path) -> dict[Path, tuple[float, int]]:
    """Record `{resolved_path: (mtime, size_bytes)}` for non-hidden files in `directory`."""
    snapshot: dict[Path, tuple[float, int]] = {}
    if not directory.exists():
        return snapshot

    for entry in directory.iterdir():
        if entry.name.startswith(".") or not entry.is_file():
            continue
        try:
            stat = entry.stat()
            snapshot[entry.resolve()] = (stat.st_mtime, stat.st_size)
        except OSError:
            continue
    return snapshot


def _sanitize_target_filename(raw_name: str, fallback_suffix: str) -> str:
    """Clean a requested output filename and preserve the original file extension if omitted."""
    base_name = Path(raw_name.strip()).name
    cleaned = _UNSAFE_NAME_PATTERN.sub("_", base_name).strip(" .")
    if not cleaned:
        return ""
    if not Path(cleaned).suffix and fallback_suffix:
        cleaned = f"{cleaned}{fallback_suffix}"
    return cleaned


def _sleep_interruptible(seconds: float, stop_event: Any = None) -> bool:
    """Sleep for `seconds` while honoring an optional `threading.Event`. Returns False if stopped."""
    if seconds <= 0:
        return True
    if isinstance(stop_event, threading.Event):
        return not stop_event.wait(timeout=seconds)
    time.sleep(seconds)
    return True


class DownloadFileAction(BaseAction):
    """Clicks a download trigger (optional) and waits until the target file finishes downloading."""

    action_type: str = getattr(config, "ACTION_DOWNLOAD_FILE", "download_file")

    @staticmethod
    def _resolve_downloads_dir(context: dict[str, Any]) -> Path:
        """Resolve the active downloads directory from execution context or project config."""
        ctx_dir = context.get("downloads_dir")
        if ctx_dir:
            target = Path(ctx_dir).resolve()
        else:
            default_dir = getattr(
                config,
                "DOWNLOADS_DIR",
                Path(__file__).resolve().parent.parent / "data" / "downloads",
            )
            target = Path(default_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def _trigger_download_click(
        driver: WebDriver,
        step: WorkflowStep,
        selector_val: str,
    ) -> str:
        """Locate and click the download link or button, returning any non-blocking warning."""
        warning = ""
        try:
            matches = SelectorManager.find_elements(driver, step.selector_strategy, selector_val)
            if len(matches) > 1:
                warning = (
                    f"Selector [{step.selector_strategy}: {selector_val}] matched {len(matches)} elements; "
                    "triggering download on the first match."
                )
        except (ValueError, WebDriverException):
            pass

        element = WaitHandler.wait_for_clickable(
            driver=driver,
            strategy=step.selector_strategy,
            value=selector_val,
            timeout=step.timeout,
        )

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                element,
            )
        except WebDriverException:
            pass

        force_js = bool(step.options.get("js_click", False))
        allow_js_fallback = bool(step.options.get("js_fallback", True))

        if force_js:
            driver.execute_script("arguments[0].click();", element)
            return warning

        try:
            element.click()
            return warning
        except ElementClickInterceptedException:
            if not allow_js_fallback:
                raise
            driver.execute_script("arguments[0].click();", element)
            note = "Native click was intercepted; triggered download via JavaScript fallback."
            return f"{warning} {note}".strip() if warning else note

    @staticmethod
    def _wait_for_new_file(
        downloads_dir: Path,
        before_snapshot: dict[Path, tuple[float, int]],
        timeout: float,
        expected_ext: str = "",
        stop_event: Any = None,
    ) -> Path:
        """Poll `downloads_dir` until a non-empty, completed download file appears."""
        deadline = time.monotonic() + timeout
        normalized_ext = ""
        if expected_ext.strip():
            raw_ext = expected_ext.strip().lower()
            normalized_ext = raw_ext if raw_ext.startswith(".") else f".{raw_ext}"

        while time.monotonic() <= deadline:
            if isinstance(stop_event, threading.Event) and stop_event.is_set():
                raise RuntimeError("Download aborted because workflow execution was stopped.")

            in_progress = False
            candidates: list[tuple[float, Path]] = []

            if downloads_dir.exists():
                for entry in downloads_dir.iterdir():
                    if entry.name.startswith(".") or not entry.is_file():
                        continue
                    lower_name = entry.name.lower()
                    if lower_name.endswith(_TEMP_DOWNLOAD_SUFFIXES):
                        in_progress = True
                        continue

                    try:
                        stat = entry.stat()
                    except OSError:
                        continue

                    if stat.st_size <= 0:
                        in_progress = True
                        continue

                    resolved_entry = entry.resolve()
                    prior_meta = before_snapshot.get(resolved_entry)
                    is_new_or_updated = prior_meta is None or prior_meta != (stat.st_mtime, stat.st_size)
                    if not is_new_or_updated:
                        continue

                    if normalized_ext and entry.suffix.lower() != normalized_ext:
                        continue

                    candidates.append((stat.st_mtime, resolved_entry))

            if candidates and not in_progress:
                candidates.sort(key=lambda item: item[0], reverse=True)
                newest_file = candidates[0][1]
                try:
                    first_size = newest_file.stat().st_size
                except OSError:
                    first_size = -1

                if not _sleep_interruptible(0.15, stop_event):
                    raise RuntimeError("Download aborted because workflow execution was stopped.")

                try:
                    second_size = newest_file.stat().st_size
                except OSError:
                    second_size = -2

                if first_size > 0 and first_size == second_size:
                    return newest_file

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not _sleep_interruptible(min(_POLL_INTERVAL, remaining), stop_event):
                raise RuntimeError("Download aborted because workflow execution was stopped.")

        ext_note = f" matching '{normalized_ext}'" if normalized_ext else ""
        raise TimeoutException(
            f"Timed out after {timeout:.1f}s waiting for a completed download{ext_note} "
            f"in '{downloads_dir}'."
        )

    @staticmethod
    def _apply_optional_rename(
        downloaded_path: Path,
        rename_to: str,
        overwrite: bool = True,
    ) -> Path:
        """Rename `downloaded_path` within its directory when a target filename is configured."""
        cleaned_name = _sanitize_target_filename(rename_to, downloaded_path.suffix)
        if not cleaned_name:
            return downloaded_path

        target_path = downloaded_path.parent / cleaned_name
        if target_path.resolve() == downloaded_path.resolve():
            return downloaded_path

        if target_path.exists():
            if overwrite:
                target_path.unlink(missing_ok=True)
            else:
                stem = target_path.stem
                suffix = target_path.suffix
                counter = 1
                while target_path.exists():
                    target_path = downloaded_path.parent / f"{stem}_{counter}{suffix}"
                    counter += 1

        downloaded_path.replace(target_path)
        return target_path

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        downloads_dir = self._resolve_downloads_dir(context)
        before_snapshot = _snapshot_directory(downloads_dir)

        selector_val = resolved["selector_value"].strip()
        warning = ""
        if selector_val:
            warning = self._trigger_download_click(driver, step, selector_val)

        bounded_timeout = clamp_timeout(step.timeout)
        expected_ext = str(
            step.options.get("expected_extension", step.options.get("extension", ""))
        ).strip()
        stop_event = context.get("stop_event")

        downloaded_path = self._wait_for_new_file(
            downloads_dir=downloads_dir,
            before_snapshot=before_snapshot,
            timeout=bounded_timeout,
            expected_ext=expected_ext,
            stop_event=stop_event,
        )

        rename_target = str(step.options.get("rename_to", "")).strip() or resolved["input_value"].strip()
        overwrite = bool(step.options.get("overwrite", True))
        if rename_target:
            downloaded_path = self._apply_optional_rename(
                downloaded_path,
                rename_to=rename_target,
                overwrite=overwrite,
            )

        size_bytes = downloaded_path.stat().st_size if downloaded_path.exists() else 0
        output_key = step.output_key.strip()
        if output_key:
            variables = context.setdefault("variables", {})
            if isinstance(variables, dict):
                variables[output_key] = str(downloaded_path)

        return ActionOutcome(
            success=True,
            message=f"Downloaded '{downloaded_path.name}' ({size_bytes:,} bytes).",
            extracted_data={
                "file_name": downloaded_path.name,
                "file_path": str(downloaded_path),
                "size_bytes": size_bytes,
            },
            warning=warning,
        )


class WaitForDownloadAction(DownloadFileAction):
    """Alias action for waiting on an already-triggered download without clicking an element."""

    action_type: str = getattr(config, "ACTION_WAIT_FOR_DOWNLOAD", "wait_for_download")

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        step_copy = step.clone()
        step_copy.selector_value = ""
        resolved_copy = dict(resolved)
        resolved_copy["selector_value"] = ""
        return super().perform(driver, step_copy, resolved_copy, context)