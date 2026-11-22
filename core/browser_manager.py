"""Selenium WebDriver lifecycle, download configuration, and failure screenshot manager."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.remote.webdriver import WebDriver

import config

_SAFE_FILENAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")


def _slugify(label: str, fallback: str = "capture") -> str:
    """Convert an arbitrary label into a filesystem-safe filename prefix."""
    cleaned = _SAFE_FILENAME_PATTERN.sub("_", label.strip().lower()).strip("_")
    return cleaned[:48] or fallback


class BrowserManager:
    """Creates, configures, monitors, and safely closes Selenium browser sessions."""

    def __init__(
        self,
        browser_name: str = config.DEFAULT_BROWSER,
        headless: bool = config.DEFAULT_HEADLESS,
        timeout: float = config.DEFAULT_TIMEOUT,
        downloads_dir: Path | str | None = None,
        screenshots_dir: Path | str | None = None,
    ) -> None:
        self.browser_name: str = (browser_name or config.DEFAULT_BROWSER).strip().lower()
        self.headless: bool = bool(headless)
        self.timeout: float = float(timeout)
        self.downloads_dir: Path = (
            Path(downloads_dir).resolve() if downloads_dir else config.DOWNLOADS_DIR.resolve()
        )
        self.screenshots_dir: Path = (
            Path(screenshots_dir).resolve() if screenshots_dir else config.SCREENSHOTS_DIR.resolve()
        )
        self.driver: WebDriver | None = None

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_active(self) -> bool:
        """Return True if a WebDriver session is currently open and responsive."""
        if self.driver is None:
            return False
        try:
            _ = self.driver.window_handles
            return True
        except WebDriverException:
            return False

    def _build_download_prefs(self) -> dict[str, Any]:
        """Return Chromium download preferences pointing directly to `downloads_dir`."""
        return {
            "download.default_directory": str(self.downloads_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True,
        }

    def _apply_common_chromium_flags(self, options: ChromeOptions | EdgeOptions) -> None:
        """Apply shared stability, viewport, and download options to Chrome or Edge."""
        options.add_experimental_option("prefs", self._build_download_prefs())
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")

        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1366,768")
        else:
            options.add_argument("--start-maximized")

    def _create_chrome_driver(self) -> WebDriver:
        """Instantiate a configured Chrome WebDriver session."""
        options = ChromeOptions()
        self._apply_common_chromium_flags(options)
        return webdriver.Chrome(options=options)

    def _create_edge_driver(self) -> WebDriver:
        """Instantiate a configured Microsoft Edge WebDriver session."""
        options = EdgeOptions()
        self._apply_common_chromium_flags(options)
        return webdriver.Edge(options=options)

    def start_session(
        self,
        browser_name: str | None = None,
        headless: bool | None = None,
        timeout: float | None = None,
    ) -> WebDriver:
        """Start a fresh Selenium WebDriver session, closing any prior session first."""
        if browser_name is not None:
            self.browser_name = browser_name.strip().lower()
        if headless is not None:
            self.headless = bool(headless)
        if timeout is not None:
            self.timeout = float(timeout)

        if self.browser_name not in config.SUPPORTED_BROWSERS:
            supported = ", ".join(config.SUPPORTED_BROWSERS)
            raise ValueError(
                f"Unsupported browser '{self.browser_name}'. Supported browsers: {supported}."
            )

        if self.driver is not None:
            self.close_session()

        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        if self.browser_name == "chrome":
            driver = self._create_chrome_driver()
        else:
            driver = self._create_edge_driver()

        # Use explicit condition-based waits rather than implicit waits
        driver.implicitly_wait(0)
        page_timeout = max(self.timeout, 15.0)
        driver.set_page_load_timeout(page_timeout)
        driver.set_script_timeout(page_timeout)

        self.driver = driver
        return driver

    def get_driver(self) -> WebDriver:
        """Return the active WebDriver or raise RuntimeError if no session is running."""
        if self.driver is None:
            raise RuntimeError("No active browser session. Call `start_session()` first.")
        return self.driver

    def capture_screenshot(self, label: str = "step_failure") -> str:
        """Save a PNG screenshot of the current browser viewport and return its file path."""
        if self.driver is None:
            return ""

        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _slugify(label, fallback="step_failure")
        filename = f"{slug}_{stamp}_{uuid4().hex[:6]}.png"
        target_path = self.screenshots_dir / filename

        try:
            saved = self.driver.save_screenshot(str(target_path))
            return str(target_path) if saved and target_path.exists() else ""
        except WebDriverException:
            return ""

    def close_session(self) -> None:
        """Safely quit the active WebDriver and release resources even after errors."""
        driver = self.driver
        self.driver = None
        if driver is None:
            return
        try:
            driver.quit()
        except Exception:
            pass

    def __enter__(self) -> WebDriver:
        """Start a browser session upon entering a `with` context block."""
        return self.start_session()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Guarantee browser termination when exiting a `with` context block."""
        self.close_session()