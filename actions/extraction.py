"""Text, attribute, hyperlink, and HTML table extraction actions powered by Selenium and BeautifulSoup."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

import config
from actions.base_action import ActionOutcome, BaseAction
from actions.waiting import WaitHandler
from core.selector_manager import SelectorManager
from models.workflow_step import WorkflowStep


def _normalize_text(raw: str, collapse_whitespace: bool = True) -> str:
    """Clean extracted text by stripping edges and optionally collapsing internal whitespace."""
    cleaned = (raw or "").strip()
    if collapse_whitespace:
        return " ".join(cleaned.split())
    return cleaned


def _extract_from_element(
    element: WebElement,
    attribute: str = "",
    collapse_whitespace: bool = True,
) -> str:
    """Extract an attribute value or visible/inner text from a Selenium WebElement."""
    attr_name = attribute.strip()
    if attr_name and attr_name.lower() != "text":
        val = element.get_attribute(attr_name)
        return _normalize_text(val or "", collapse_whitespace=collapse_whitespace)

    visible = _normalize_text(element.text or "", collapse_whitespace=collapse_whitespace)
    if visible:
        return visible

    # Fallback to innerHTML/textContent via BeautifulSoup for hidden or off-screen nodes
    try:
        outer_html = element.get_attribute("outerHTML") or ""
        if outer_html:
            soup = BeautifulSoup(outer_html, "html.parser")
            return _normalize_text(soup.get_text(" "), collapse_whitespace=collapse_whitespace)
    except WebDriverException:
        pass
    return ""


class ExtractTextAction(BaseAction):
    """Extracts text or an HTML attribute from one or all elements matching a selector."""

    action_type: str = config.ACTION_EXTRACT_TEXT

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        selector_val = resolved["selector_value"].strip()
        if not selector_val:
            raise ValueError("Extract Text action requires a non-empty selector value.")

        WaitHandler.wait_for_present(
            driver=driver,
            strategy=step.selector_strategy,
            value=selector_val,
            timeout=step.timeout,
        )

        matches = SelectorManager.find_elements(driver, step.selector_strategy, selector_val)
        if not matches:
            raise ValueError(f"No elements found for [{step.selector_strategy}: {selector_val}].")

        attribute = str(step.options.get("attribute", "")).strip()
        extract_all = bool(step.options.get("extract_all", False))
        collapse_ws = bool(step.options.get("strip_whitespace", True))
        field_name = (
            str(step.options.get("field_name", "")).strip()
            or step.output_key.strip()
            or step.name.strip()
            or "extracted_text"
        )

        warning = ""
        if not extract_all and len(matches) > 1:
            warning = (
                f"Selector [{step.selector_strategy}: {selector_val}] matched {len(matches)} elements; "
                "extracted the first match (enable 'extract_all' to capture all)."
            )

        target_elements = matches if extract_all else [matches[0]]
        extracted_values = [
            _extract_from_element(el, attribute=attribute, collapse_whitespace=collapse_ws)
            for el in target_elements
        ]

        output_key = step.output_key.strip()
        if output_key:
            variables = context.setdefault("variables", {})
            if isinstance(variables, dict):
                variables[output_key] = extracted_values if extract_all else extracted_values[0]

        if extract_all:
            payload: Any = [{field_name: val} for val in extracted_values]
            preview = f"{len(extracted_values)} item(s)"
        else:
            single_val = extracted_values[0]
            payload = {field_name: single_val}
            preview = repr(single_val if len(single_val) <= 60 else f"{single_val[:57]}...")

        source_label = f"attribute '{attribute}'" if attribute and attribute.lower() != "text" else "text"
        return ActionOutcome(
            success=True,
            message=f"Extracted {source_label} ({preview}) from [{step.selector_strategy}: {selector_val}].",
            extracted_data=payload,
            warning=warning,
        )


class ExtractLinksAction(BaseAction):
    """Extracts hyperlinks (`<a href>`) from the current page or within a scoped container."""

    action_type: str = config.ACTION_EXTRACT_LINKS

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        selector_val = resolved["selector_value"].strip()
        warning = ""

        if selector_val:
            container = WaitHandler.wait_for_present(
                driver=driver,
                strategy=step.selector_strategy,
                value=selector_val,
                timeout=step.timeout,
            )
            matches = SelectorManager.find_elements(driver, step.selector_strategy, selector_val)
            if len(matches) > 1:
                warning = (
                    f"Container selector [{step.selector_strategy}: {selector_val}] matched "
                    f"{len(matches)} elements; extracting links from the first container."
                )
            html_source = container.get_attribute("outerHTML") or ""
            scope_desc = f"within [{step.selector_strategy}: {selector_val}]"
        else:
            html_source = driver.page_source or ""
            scope_desc = "on current page"

        try:
            base_url = driver.current_url or ""
        except WebDriverException:
            base_url = ""

        resolve_relative = bool(step.options.get("resolve_relative", True))
        unique_only = bool(step.options.get("unique_only", True))
        ignore_fragments = bool(step.options.get("ignore_fragments", True))
        text_filter = str(
            step.options.get("contains_text", step.options.get("filter_text", ""))
        ).strip().lower()
        href_filter = str(step.options.get("href_contains", "")).strip().lower()

        soup = BeautifulSoup(html_source, "html.parser")
        extracted_links: list[dict[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()

        for anchor in soup.find_all("a", href=True):
            raw_href = str(anchor.get("href") or "").strip()
            if not raw_href:
                continue
            if ignore_fragments and (
                raw_href.startswith("#") or raw_href.lower().startswith("javascript:")
            ):
                continue

            resolved_href = (
                urljoin(base_url, raw_href)
                if (resolve_relative and base_url)
                else raw_href
            )
            link_text = _normalize_text(anchor.get_text(" "), collapse_whitespace=True)
            title_attr = _normalize_text(str(anchor.get("title") or ""), collapse_whitespace=True)

            if text_filter and text_filter not in link_text.lower() and text_filter not in resolved_href.lower():
                continue
            if href_filter and href_filter not in resolved_href.lower():
                continue

            pair_key = (link_text, resolved_href)
            if unique_only and pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            extracted_links.append(
                {
                    "text": link_text,
                    "href": resolved_href,
                    "title": title_attr,
                }
            )

        output_key = step.output_key.strip()
        if output_key:
            variables = context.setdefault("variables", {})
            if isinstance(variables, dict):
                variables[output_key] = extracted_links

        return ActionOutcome(
            success=True,
            message=f"Extracted {len(extracted_links)} link(s) {scope_desc}.",
            extracted_data=extracted_links,
            warning=warning,
        )


class ExtractTableAction(BaseAction):
    """Parses an HTML `<table>` into a list of row dictionaries keyed by column headers."""

    action_type: str = getattr(config, "ACTION_EXTRACT_TABLE", "extract_table")

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        selector_val = resolved["selector_value"].strip() or "table"
        strategy = step.selector_strategy if resolved["selector_value"].strip() else "css"

        table_el = WaitHandler.wait_for_present(
            driver=driver,
            strategy=strategy,
            value=selector_val,
            timeout=step.timeout,
        )
        outer_html = table_el.get_attribute("outerHTML") or ""
        soup = BeautifulSoup(outer_html, "html.parser")
        table = soup.find("table") or soup

        rows = table.find_all("tr")
        if not rows:
            return ActionOutcome(
                success=True,
                message=f"Table [{strategy}: {selector_val}] contained 0 rows.",
                extracted_data=[],
            )

        header_cells = rows[0].find_all(["th", "td"])
        headers = [
            _normalize_text(cell.get_text(" "), collapse_whitespace=True) or f"column_{idx}"
            for idx, cell in enumerate(header_cells, start=1)
        ]

        records: list[dict[str, str]] = []
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row_dict: dict[str, str] = {}
            for idx, header in enumerate(headers):
                val = (
                    _normalize_text(cells[idx].get_text(" "), collapse_whitespace=True)
                    if idx < len(cells)
                    else ""
                )
                row_dict[header] = val
            if any(row_dict.values()):
                records.append(row_dict)

        output_key = step.output_key.strip()
        if output_key:
            variables = context.setdefault("variables", {})
            if isinstance(variables, dict):
                variables[output_key] = records

        return ActionOutcome(
            success=True,
            message=f"Extracted {len(records)} table row(s) from [{strategy}: {selector_val}].",
            extracted_data=records,
        )