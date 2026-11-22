"""Reusable dark-themed Tkinter UI components for Nexora views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import tkinter as tk
from tkinter import ttk
from typing import Any

from interface.theme import COLORS, FONTS


class ActionButton(tk.Button):
    """Flat, hover-responsive button supporting primary, secondary, success, and danger styles."""

    _VARIANT_PALETTE: dict[str, tuple[str, str, str]] = {
        "primary": (COLORS["accent"], COLORS["accent_hover"], COLORS["accent_text"]),
        "secondary": (COLORS["bg_surface_alt"], COLORS["border"], COLORS["text_primary"]),
        "success": (COLORS["success"], COLORS["success_hover"], "#052e16"),
        "danger": (COLORS["danger"], COLORS["danger_hover"], "#ffffff"),
    }

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Any = None,
        variant: str = "primary",
        padx: int = 14,
        pady: int = 6,
        **kwargs: Any,
    ) -> None:
        bg, hover_bg, fg = self._VARIANT_PALETTE.get(
            variant.lower(), self._VARIANT_PALETTE["primary"]
        )
        self._base_bg = bg
        self._hover_bg = hover_bg
        self._base_fg = fg

        super().__init__(
            master,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            disabledforeground=COLORS["text_muted"],
            relief=tk.FLAT,
            bd=0,
            padx=padx,
            pady=pady,
            font=FONTS["small_bold"],
            cursor="hand2",
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event: tk.Event[Any]) -> None:
        if str(self.cget("state")) != tk.DISABLED:
            self.configure(bg=self._hover_bg)

    def _on_leave(self, _event: tk.Event[Any]) -> None:
        self.configure(bg=self._base_bg)


class CardFrame(tk.Frame):
    """Bordered surface panel with an optional title and subtitle header."""

    def __init__(
        self,
        master: tk.Misc,
        title: str = "",
        subtitle: str = "",
        padx: int = 14,
        pady: int = 12,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=padx,
            pady=pady,
            **kwargs,
        )

        if title:
            header_frame = tk.Frame(self, bg=COLORS["bg_surface"])
            header_frame.pack(fill=tk.X, pady=(0, 8))

            tk.Label(
                header_frame,
                text=title,
                bg=COLORS["bg_surface"],
                fg=COLORS["accent"],
                font=FONTS["heading"],
                anchor="w",
            ).pack(fill=tk.X)

            if subtitle:
                tk.Label(
                    header_frame,
                    text=subtitle,
                    bg=COLORS["bg_surface"],
                    fg=COLORS["text_secondary"],
                    font=FONTS["small"],
                    anchor="w",
                ).pack(fill=tk.X, pady=(2, 0))

            tk.Frame(self, bg=COLORS["border"], height=1).pack(fill=tk.X, pady=(0, 10))


class KpiCard(tk.Frame):
    """Dashboard metric card displaying a KPI title, prominent value, and optional caption."""

    def __init__(
        self,
        master: tk.Misc,
        label: str,
        value: str = "0",
        subtext: str = "",
        accent_color: str = COLORS["accent"],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=14,
            pady=10,
            **kwargs,
        )
        self._accent = accent_color

        tk.Frame(self, bg=accent_color, height=3).pack(fill=tk.X, pady=(0, 8))

        self.title_label = tk.Label(
            self,
            text=label.upper(),
            bg=COLORS["bg_surface"],
            fg=COLORS["text_secondary"],
            font=FONTS["small_bold"],
            anchor="w",
        )
        self.title_label.pack(fill=tk.X)

        self.value_label = tk.Label(
            self,
            text=value,
            bg=COLORS["bg_surface"],
            fg=COLORS["text_primary"],
            font=FONTS["kpi_value"],
            anchor="w",
        )
        self.value_label.pack(fill=tk.X, pady=(2, 2))

        self.subtext_label = tk.Label(
            self,
            text=subtext,
            bg=COLORS["bg_surface"],
            fg=COLORS["text_muted"],
            font=FONTS["small"],
            anchor="w",
        )
        self.subtext_label.pack(fill=tk.X)

    def set_value(self, value: str, subtext: str | None = None) -> None:
        """Update the displayed KPI metric and optional subtitle."""
        self.value_label.configure(text=str(value))
        if subtext is not None:
            self.subtext_label.configure(text=subtext)


class StatusBadge(tk.Label):
    """Compact pill badge reflecting workflow or engine status."""

    _STATUS_STYLES: dict[str, tuple[str, str]] = {
        "ready": (COLORS["bg_surface_alt"], COLORS["text_secondary"]),
        "idle": (COLORS["bg_surface_alt"], COLORS["text_secondary"]),
        "running": ("#0c4a6e", COLORS["accent"]),
        "completed": (COLORS["success_bg"], COLORS["success"]),
        "success": (COLORS["success_bg"], COLORS["success"]),
        "partial": (COLORS["warning_bg"], COLORS["warning"]),
        "warning": (COLORS["warning_bg"], COLORS["warning"]),
        "failed": (COLORS["danger_bg"], COLORS["danger"]),
        "error": (COLORS["danger_bg"], COLORS["danger"]),
        "stopped": (COLORS["warning_bg"], COLORS["warning"]),
    }

    def __init__(self, master: tk.Misc, status: str = "ready", text: str | None = None) -> None:
        super().__init__(
            master,
            font=FONTS["small_bold"],
            padx=10,
            pady=4,
            relief=tk.FLAT,
        )
        self.set_status(status=status, text=text)

    def set_status(self, status: str, text: str | None = None) -> None:
        """Update badge text and background/foreground colors for `status`."""
        key = (status or "ready").strip().lower()
        bg, fg = self._STATUS_STYLES.get(key, self._STATUS_STYLES["ready"])
        display = text if text is not None else key.upper()
        self.configure(text=display, bg=bg, fg=fg)


class ScrollableFrame(tk.Frame):
    """Vertically scrollable container exposing `.content` for child widgets."""

    def __init__(self, master: tk.Misc, bg: str = COLORS["bg_primary"], **kwargs: Any) -> None:
        super().__init__(master, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=bg)

        self._window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_content_configure(self, _event: tk.Event[Any]) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event[Any]) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event[Any]) -> None:
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_mousewheel(self, _event: tk.Event[Any]) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event[Any]) -> None:
        self.canvas.unbind_all("<MouseWheel>")


class DataTable(tk.Frame):
    """Themed `ttk.Treeview` table with zebra striping, scrollbars, and dict-row loading."""

    def __init__(
        self,
        master: tk.Misc,
        columns: Sequence[str] | None = None,
        height: int = 8,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            bg=COLORS["bg_surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            **kwargs,
        )
        self._columns: list[str] = []

        self.tree = ttk.Treeview(self, show="headings", height=height, selectmode="browse")
        self.v_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.h_scroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.v_scroll.set, xscrollcommand=self.h_scroll.set)

        self.tree.tag_configure("even", background=COLORS["row_even"], foreground=COLORS["text_primary"])
        self.tree.tag_configure("odd", background=COLORS["row_odd"], foreground=COLORS["text_primary"])

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.v_scroll.grid(row=0, column=1, sticky="ns")
        self.h_scroll.grid(row=1, column=0, sticky="ew")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        if columns:
            self.set_columns(columns)

    def set_columns(
        self,
        columns: Sequence[str],
        widths: Mapping[str, int] | None = None,
    ) -> None:
        """Configure column headers and optional widths."""
        self.clear()
        self._columns = [str(col) for col in columns]
        self.tree.configure(columns=self._columns)
        for col in self._columns:
            self.tree.heading(col, text=col, anchor="w")
            col_width = widths.get(col, 130) if widths else 130
            self.tree.column(col, width=col_width, minwidth=70, anchor="w")

    def clear(self) -> None:
        """Remove all rows from the table."""
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

    def set_rows(self, rows: Sequence[Mapping[str, Any] | Sequence[Any]]) -> None:
        """Replace table contents with a sequence of row dicts or tuples."""
        self.clear()
        for idx, row in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            if isinstance(row, Mapping):
                values = [str(row.get(col, "")) for col in self._columns]
            else:
                values = [str(val) for val in row]
            self.tree.insert("", tk.END, values=values, tags=(tag,))

    def get_selected_index(self) -> int | None:
        """Return the 0-based index of the currently selected row, or None."""
        selection = self.tree.selection()
        if not selection:
            return None
        return self.tree.index(selection[0])

    def get_selected_values(self) -> list[str]:
        """Return the cell values of the selected row as a list of strings."""
        selection = self.tree.selection()
        if not selection:
            return []
        raw = self.tree.item(selection[0], "values")
        return [str(v) for v in raw]


class ConsoleLogView(tk.Frame):
    """Read-only monospaced execution log panel with severity color tags."""

    def __init__(self, master: tk.Misc, height: int = 10, **kwargs: Any) -> None:
        super().__init__(
            master,
            bg=COLORS["bg_input"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            **kwargs,
        )
        self.text = tk.Text(
            self,
            height=height,
            bg=COLORS["bg_input"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"],
            font=FONTS["mono"],
            wrap=tk.WORD,
            relief=tk.FLAT,
            bd=6,
            state=tk.DISABLED,
        )
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.text.yview)
        self.text.configure(yscrollcommand=self.scrollbar.set)

        self.text.tag_configure("INFO", foreground=COLORS["text_primary"])
        self.text.tag_configure("SUCCESS", foreground=COLORS["success"])
        self.text.tag_configure("WARNING", foreground=COLORS["warning"])
        self.text.tag_configure("ERROR", foreground=COLORS["danger"])
        self.text.tag_configure("TIMESTAMP", foreground=COLORS["text_muted"])

        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def append_log(self, level: str, message: str) -> None:
        """Append a timestamped log line with severity styling and auto-scroll."""
        lvl = (level or "INFO").strip().upper()
        if lvl not in ("INFO", "SUCCESS", "WARNING", "ERROR"):
            lvl = "INFO"
        stamp = datetime.now().strftime("%H:%M:%S")

        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, f"[{stamp}] ", "TIMESTAMP")
        self.text.insert(tk.END, f"[{lvl}] {message}\n", lvl)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def clear(self) -> None:
        """Clear all messages from the log console."""
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)