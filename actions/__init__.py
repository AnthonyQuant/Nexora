"""Public exports and action-type registry for all Nexora browser action handlers."""

from __future__ import annotations

from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver

import config
from actions.base_action import ActionOutcome, BaseAction, RECOVERABLE_EXCEPTIONS
from actions.downloads import DownloadFileAction, WaitForDownloadAction
from actions.extraction import ExtractLinksAction, ExtractTableAction, ExtractTextAction
from actions.interaction import ClickElementAction, EnterTextAction, SelectOptionAction
from actions.navigation import (
    NavigateBackAction,
    NavigateForwardAction,
    OpenUrlAction,
    ScrollAction,
)
from actions.waiting import WaitHandler, clamp_timeout
from models.workflow_step import WorkflowStep


class WaitAction(BaseAction):
    """Waits for an explicit DOM or navigation condition before continuing execution."""

    action_type: str = getattr(config, "ACTION_WAIT", "wait")

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        message = WaitHandler.wait_for_step(
            driver=driver,
            step=step,
            resolved_selector=resolved["selector_value"],
            resolved_input=resolved["input_value"],
        )
        return ActionOutcome(success=True, message=message)


_REGISTERED_CLASSES: tuple[type[BaseAction], ...] = (
    OpenUrlAction,
    NavigateBackAction,
    NavigateForwardAction,
    ScrollAction,
    ClickElementAction,
    EnterTextAction,
    SelectOptionAction,
    ExtractTextAction,
    ExtractLinksAction,
    ExtractTableAction,
    DownloadFileAction,
    WaitForDownloadAction,
    WaitAction,
)

ACTION_CLASSES: dict[str, type[BaseAction]] = {
    cls.action_type: cls for cls in _REGISTERED_CLASSES if cls.action_type
}


def get_action_handler(action_type: str) -> BaseAction:
    """Return an instantiated `BaseAction` handler matching `action_type`."""
    normalized = (action_type or "").strip().lower()
    handler_cls = ACTION_CLASSES.get(normalized)
    if handler_cls is None:
        supported = ", ".join(ACTION_CLASSES.keys())
        raise ValueError(
            f"Unsupported action type '{action_type}'. Registered actions: {supported}."
        )
    return handler_cls()


def get_registered_action_types() -> list[str]:
    """Return all registered browser action type identifiers in definition order."""
    return list(ACTION_CLASSES.keys())


__all__ = [
    "ActionOutcome",
    "BaseAction",
    "RECOVERABLE_EXCEPTIONS",
    "WaitHandler",
    "WaitAction",
    "clamp_timeout",
    "OpenUrlAction",
    "NavigateBackAction",
    "NavigateForwardAction",
    "ScrollAction",
    "ClickElementAction",
    "EnterTextAction",
    "SelectOptionAction",
    "ExtractTextAction",
    "ExtractLinksAction",
    "ExtractTableAction",
    "DownloadFileAction",
    "WaitForDownloadAction",
    "ACTION_CLASSES",
    "get_action_handler",
    "get_registered_action_types",
]