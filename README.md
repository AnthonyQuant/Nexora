# Nexora — Deterministic Browser Automation & CSV Workflow Studio

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Selenium](https://img.shields.io/badge/Selenium-4.25+-43B02A?style=for-the-badge&logo=selenium&logoColor=white)
![Tkinter](https://img.shields.io/badge/UI-Tkinter%20Dark%20Slate-21262D?style=for-the-badge)
![Pytest](https://img.shields.io/badge/Tests-18%20Passed-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![Architecture](https://img.shields.io/badge/Architecture-Modular%20OOP-FF6F00?style=for-the-badge)

**Nexora** is a modular Python desktop studio and command-line automation framework built on **Selenium WebDriver** and **Tkinter**. Designed for reliability, auditability, and ease of use, Nexora allows you to visually build, test, and execute deterministic browser workflows, run multi-row CSV batch processing, enforce step execution guards, intercept high-risk actions with human-in-the-loop approval gates, and export structured telemetry logs and CSV datasets.

---

## Key Highlights & Core Capabilities

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              NEXORA STUDIO ENGINE                               │
├───────────────────────────────┬─────────────────────────────────────────────────┤
│ ⚡ Deterministic Selenium      │ Multi-strategy locator resolution (CSS, XPath,   │
│    Orchestration              │ ID, Name) with explicit wait timeouts & retries.│
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 📊 Multi-Row CSV Batch        │ Dynamically inject dataset headers into steps   │
│    Processing                 │ using dynamic dynamic tokens: {{column_name}}.  │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 🛡️ Smart Conditional Guards   │ Execute, skip, or abort steps based on page     │
│    & Human Approval Gates     │ state (e.g., skip_if_missing, requires_approval)│
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 🖥️ Dual Execution Modes       │ Full dark-slate Tkinter GUI for interactive use │
│    (GUI Studio & Headless CLI)│ or headless CLI scripts for scheduled pipelines.│
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 📥 Data Extraction & Downloads│ Extract tables, text, and link sets, with       │
│    Engine                     │ polling detection for file downloads.           │
├───────────────────────────────┼─────────────────────────────────────────────────┤
│ 📈 Analytics & Complete Logs  │ Auditable per-step JSON execution records, failure│
│    Auditing                   │ screenshots, and historical CSV export data.    │
└───────────────────────────────┴─────────────────────────────────────────────────┘
```

---

## Architecture Overview

```text
Nexora/
├── main.py                     # Unified Desktop GUI & CLI entry point
├── config.py                   # Centralized paths, action constants, timeouts & defaults
├── requirements.txt            # Python dependencies (Selenium, Pytest)
├── .gitignore                  # Git tracking rules for logs, exports, and profiles
├── models/                     # Pure data models & serialization schemas
│   ├── workflow_step.py        # Step schema, selectors, CSV bindings & guard rules
│   ├── workflow.py             # Multi-step workflow container & JSON persistence
│   └── execution_record.py     # Step telemetry & aggregated run execution records
├── core/                       # Orchestration & WebDriver lifecycle
│   ├── browser_manager.py      # Chrome / Edge driver setup, timeouts & screenshots
│   ├── selector_manager.py     # Multi-strategy locator resolution & syntax validation
│   ├── action_executor.py      # Single-step dispatcher, guards & approval gates
│   └── workflow_engine.py      # Batch runner, cooperative cancellation & log persistence
├── actions/                    # 11 Modular Selenium action handlers
│   ├── base_action.py          # Retry loop, placeholder interpolation ({{var}}) & timing
│   ├── waiting.py              # Explicit WebDriverWait conditions & timeout clamping
│   ├── navigation.py           # open_url, navigate_back, navigate_forward, scroll
│   ├── interaction.py          # click_element, enter_text, select_option
│   ├── extraction.py           # extract_text, extract_links, extract_table
│   └── downloads.py            # download_file, wait_for_download & file verification
├── storage/                    # Persistence & data pipelines
│   ├── profile_manager.py      # JSON workflow profiles & template seeding
│   ├── csv_manager.py          # Encoding-resilient CSV reader & result exporter
│   ├── log_manager.py          # JSON run history & step-level audit logs
│   └── analytics_manager.py    # Metric aggregations, KPI calculations & trend reports
├── workflows/                  # Pre-built reusable workflow templates & profiles
│   ├── templates.py            # 5 Ready-to-run workflow presets
│   ├── sample_workflows.json   # Seed profiles file for default workflows
│   └── profiles/               # User-saved workflow profile JSON files
├── interface/                  # Dark-slate Tkinter desktop studio
│   ├── theme.py                # Palette, typography & ttk styling engine
│   ├── components.py           # Reusable KPI cards, DataTable, ConsoleLogView & badges
│   ├── execution_monitor.py    # Live batch runner, progress tracking & log stream
│   ├── workflow_builder.py     # Visual step sequence editor & validator
│   ├── history_viewer.py       # Historical run inspector & CSV export previewer
│   └── dashboard.py            # Main tabbed application shell
├── tests/                      # Automated Pytest suite (18 unit/integration tests)
│   ├── test_workflow_models.py
│   ├── test_storage_and_analytics.py
│   └── test_workflow_engine.py
└── demo_site/                  # Offline deterministic target portal for testing
    ├── index.html              # Core demo application page
    └── sample_report.pdf       # Verification file download artifact
```

---

## Quick Start & Installation

### 1. Prerequisites
* **Python 3.10+** installed on your system.
* **Google Chrome** or **Microsoft Edge** browser installed.

### 2. Environment Setup
Clone or extract the repository and navigate into the `Nexora/` directory:

```bash
cd Nexora
```

Create and activate a virtual environment:

```bash
# Windows (PowerShell / Git Bash)
python -m venv .venv
source .venv/Scripts/activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Launching Nexora

* **Launch Desktop Studio (GUI):**
  ```bash
  python main.py
  ```

* **Run a Preset Workflow via CLI (Headless Mode):**
  ```bash
  python main.py --preset demo_directory_scraper --headless --auto-export
  ```

---

## Desktop Studio Walkthrough

Nexora features a dark-slate desktop interface divided into three operational tabs:

### 1. Execution Monitor Tab
* **Preset & Profile Selector:** Quickly switch between built-in workflow presets and user-saved JSON profiles.
* **CSV Batch Integration:** Attach external CSV dataset files or click **Generate Sample CSV** to instantly instantiate template data (`data/sample_clients.csv`).
* **Live KPI Telemetry:** Monitor batch progress, total actions succeeded, failed/skipped counts, and extracted row counts in real time.
* **Visual Action Feed & Console Log:** Review per-step status badges (`SUCCESS`, `SKIPPED`, `FAILED`, `REJECTED`) alongside terminal logs.
* **Cooperative Control:** Pause or interrupt batch execution at any point via the **Stop Execution** control.

### 2. Workflow Builder Tab
* **Step Sequence Editor:** Create, reorder, update, and delete workflow steps visually.
* **Selector & Action Configuration:** Configure selector strategies (`ID`, `Name`, `CSS`, `XPath`), input values, CSV column bindings, explicit timeouts, and retry bounds.
* **Guard Rules & Approval Gates:** Apply conditional guards (e.g., `skip_if_missing` for optional cookie banners) and mark sensitive operations with `requires_approval=True`.
* **Validation & Profile Storage:** Validate workflow sequences for selector syntax or missing variables before saving to `workflows/profiles/` or sending directly to the active runner.

### 3. Run History & Exports Tab
* **Execution Inspector:** Filter past execution records by workflow ID, run status (`completed`, `partial`, `failed`, `stopped`), or date range.
* **Per-Step Telemetry Audit:** View precise start/end timestamps, duration in milliseconds, error messages, and retry attempts for every action.
* **CSV Result Preview:** Preview extracted dataset tables directly in the app, with quick access to export files in `data/exports/` and failure screenshots in `data/screenshots/`.

---

## Command Line Interface (CLI) Reference

Nexora features a command-line runner for headlessly executing workflows in background jobs or scheduled task pipelines.

```bash
usage: nexora [-h] [--list-presets] [--preset PRESET] [--workflow WORKFLOW]
              [--csv CSV] [--browser {chrome,edge}] [--headless]
              [--timeout TIMEOUT] [--auto-export] [--export-path EXPORT_PATH]
              [--auto-approve] [--stop-on-error]
```

### Common Command Examples

* **List All Presets and Saved Profiles:**
  ```bash
  python main.py --list-presets
  ```

* **Execute Offline Demo Scraper (Headless with Auto Export):**
  ```bash
  python main.py --preset demo_directory_scraper --headless --auto-export
  ```

* **Run CSV Batch Onboarding against a Custom CSV File:**
  ```bash
  python main.py --preset demo_csv_onboarding --csv data/sample_clients.csv --headless --auto-export
  ```

* **Execute a Saved Profile File with Auto Approval for Gated Steps:**
  ```bash
  python main.py --workflow "workflows/profiles/wf_custom_intake.json" --auto-approve --headless
  ```

---

## Supported Actions & Guard Conditions

### Selenium Browser Actions

| Action Identifier | Display Name | Requires Selector | Description |
| :--- | :--- | :---: | :--- |
| `open_url` | Open URL | ❌ | Navigates the browser to the specified web address or local `file://` URI. |
| `click_element` | Click Element | ✅ | Clicks a target element resolved via ID, Name, CSS, or XPath locator. |
| `enter_text` | Enter Text | ✅ | Types text into input fields; supports `{{column}}` dynamic tokens. |
| `select_option` | Select Option | ✅ | Selects options in HTML dropdowns by visible text, value, or index. |
| `scroll` | Scroll Page | ❌ / Optional | Scrolls to the page bottom, top, by pixel offset, or to a specific element. |
| `wait` | Wait for Condition | ✅ / Optional | Pauses until an element is visible, clickable, present, or text appears. |
| `extract_text` | Extract Text / Table | ✅ | Scrapes textual content from target elements or converts HTML tables to structured data. |
| `extract_links` | Extract Links | ✅ | Extracts all anchor `href` URLs within a specified container. |
| `download_file` | Download & Verify File | ✅ | Clicks a download trigger and polls the destination folder until complete. |
| `navigate_back` | Navigate Back | ❌ | Issues a browser back navigation command. |
| `navigate_forward` | Navigate Forward | ❌ | Issues a browser forward navigation command. |

### Selector Strategies

* **Element ID (`id`):** `submit-btn`
* **Element Name (`name`):** `username`
* **CSS Selector (`css`):** `button.btn-primary[type='submit']`
* **XPath Selector (`xpath`):** `//table[@id='records-table']//tr[td]`

### Step Guard Conditions

| Guard Rule Constant | Action Behavior |
| :--- | :--- |
| `always` | Always executes the step regardless of page state (Default). |
| `if_element_exists` | Executes the step only if the `condition_target` element is present in the DOM. |
| `skip_if_missing` | Safely skips execution if the `condition_target` element is absent (useful for optional cookie banners). |
| `stop_if_missing` | Immediately halts the entire workflow if the `condition_target` element is missing. |
| `if_text_present` | Executes only if the specified text content exists on the current page. |

---

## Pre-Built Presets & Offline Demo Portal

Nexora includes an offline web portal (`demo_site/index.html`) and 5 ready-to-run workflow presets:

1. **`demo_directory_scraper` (Demo Portal: Links, Async Wait & Table Extraction):** Scrapes resource links, triggers async content loading, waits for verification, and extracts structured client directory tables.
2. **`demo_form_entry` (Demo Portal: Dynamic Form Input & Select):** Fills out web forms using dropdown choices, checkbox toggles, and multi-line notes.
3. **`demo_csv_onboarding` (Demo Portal: CSV Batch Client Onboarding):** Iterates over `data/sample_clients.csv` row-by-row to register multiple clients automatically.
4. **`demo_conditional_guards` (Demo Portal: Scraper with Conditional Guards):** Demonstrates conditional guards by attempting to dismiss optional notification banners cleanly.
5. **`demo_file_download` (Demo Portal: Download & Verify Verification Report):** Triggers a file download in the browser, polls `data/downloads/`, and verifies file completion.

---

## Test Suite & Verification

Nexora includes an automated **Pytest** suite covering model serialization, JSON storage management, CSV export pipelines, analytics metrics, selector parsing, placeholder interpolation, and workflow execution.

To run the complete test suite:

```bash
pytest -v
```

### Test Suite Output Overview

```text
tests/test_workflow_models.py ........                                  [ 27%]
tests/test_storage_and_analytics.py ......                              [ 61%]
tests/test_workflow_engine.py .......                                   [100%]

============================== 18 passed in 1.45s ==============================
```

---

## Directory Structure & Workspace Artifacts

When running workflows, Nexora automatically manages runtime workspace artifacts:

* `workflows/profiles/*.json` — Saved custom workflow definitions.
* `data/exports/*.csv` — Extracted tables and execution result datasets.
* `data/logs/*.json` — Auditable per-run execution logs and step breakdown records.
* `data/screenshots/*.png` — Automatic failure screenshots captured upon step errors.
* `data/downloads/*` — Downloaded files managed during browser automation steps.