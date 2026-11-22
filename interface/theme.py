"""Centralized dark-slate color palette, typography, and ttk styling for Nexora."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS: dict[str, str] = {
    "bg_primary": "#0f172a",
    "bg_surface": "#1e293b",
    "bg_surface_alt": "#273549",
    "bg_input": "#0b1220",
    "border": "#334155",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "accent": "#38bdf8",
    "accent_hover": "#0284c7",
    "accent_text": "#082f49",
    "success": "#22c55e",
    "success_hover": "#16a34a",
    "success_bg": "#14532d",
    "warning": "#f59e0b",
    "warning_bg": "#451a03",
    "danger": "#ef4444",
    "danger_hover": "#dc2626",
    "danger_bg": "#450a0a",
    "row_even": "#1e293b",
    "row_odd": "#172033",
    "row_selected": "#0369a1",
}

FONTS: dict[str, tuple[str, ...]] = {
    "title": ("Segoe UI", 15, "bold"),
    "subtitle": ("Segoe UI", 9),
    "heading": ("Segoe UI", 11, "bold"),
    "subheading": ("Segoe UI", 10, "bold"),
    "body": ("Segoe UI", 10),
    "body_bold": ("Segoe UI", 10, "bold"),
    "small": ("Segoe UI", 9),
    "small_bold": ("Segoe UI", 9, "bold"),
    "kpi_value": ("Segoe UI", 18, "bold"),
    "mono": ("Consolas", 9),
}


def apply_nexora_theme(root: tk.Misc) -> ttk.Style:
    """Configure ttk widget styles to match Nexora's dark-slate desktop theme."""
    style = ttk.Style(root)
    available_themes = style.theme_names()
    if "clam" in available_themes:
        style.theme_use("clam")

    if isinstance(root, (tk.Tk, tk.Toplevel)):
        root.configure(bg=COLORS["bg_primary"])

    style.configure(
        ".",
        background=COLORS["bg_primary"],
        foreground=COLORS["text_primary"],
        fieldbackground=COLORS["bg_input"],
        bordercolor=COLORS["border"],
        darkcolor=COLORS["bg_surface"],
        lightcolor=COLORS["bg_surface_alt"],
        troughcolor=COLORS["bg_input"],
        font=FONTS["body"],
    )

    # Frames & Labels
    style.configure("TFrame", background=COLORS["bg_primary"])
    style.configure("Surface.TFrame", background=COLORS["bg_surface"])
    style.configure(
        "TLabel",
        background=COLORS["bg_primary"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.configure(
        "Surface.TLabel",
        background=COLORS["bg_surface"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.configure(
        "Muted.TLabel",
        background=COLORS["bg_surface"],
        foreground=COLORS["text_secondary"],
        font=FONTS["small"],
    )
    style.configure(
        "Heading.TLabel",
        background=COLORS["bg_surface"],
        foreground=COLORS["accent"],
        font=FONTS["heading"],
    )

    # Inputs & Comboboxes
    style.configure(
        "TEntry",
        fieldbackground=COLORS["bg_input"],
        foreground=COLORS["text_primary"],
        insertcolor=COLORS["text_primary"],
        bordercolor=COLORS["border"],
        padding=5,
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", COLORS["accent"])],
    )

    style.configure(
        "TCombobox",
        fieldbackground=COLORS["bg_input"],
        background=COLORS["bg_surface_alt"],
        foreground=COLORS["text_primary"],
        arrowcolor=COLORS["text_primary"],
        bordercolor=COLORS["border"],
        padding=5,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", COLORS["bg_input"])],
        foreground=[("readonly", COLORS["text_primary"])],
        bordercolor=[("focus", COLORS["accent"])],
    )

    style.configure(
        "TCheckbutton",
        background=COLORS["bg_surface"],
        foreground=COLORS["text_primary"],
        font=FONTS["body"],
    )
    style.map(
        "TCheckbutton",
        background=[("active", COLORS["bg_surface"])],
    )

    # Notebook Tabs
    style.configure(
        "TNotebook",
        background=COLORS["bg_primary"],
        borderwidth=0,
        tabmargins=[0, 0, 0, 0],
    )
    style.configure(
        "TNotebook.Tab",
        background=COLORS["bg_surface"],
        foreground=COLORS["text_secondary"],
        padding=[16, 8],
        font=FONTS["subheading"],
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[
            ("selected", COLORS["bg_surface_alt"]),
            ("active", COLORS["bg_surface_alt"]),
        ],
        foreground=[
            ("selected", COLORS["accent"]),
            ("active", COLORS["text_primary"]),
        ],
    )

    # Treeview Tables
    style.configure(
        "Treeview",
        background=COLORS["row_even"],
        fieldbackground=COLORS["row_even"],
        foreground=COLORS["text_primary"],
        bordercolor=COLORS["border"],
        rowheight=28,
        font=FONTS["small"],
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["bg_surface_alt"],
        foreground=COLORS["accent"],
        bordercolor=COLORS["border"],
        font=FONTS["small_bold"],
        padding=(8, 6),
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["row_selected"])],
        foreground=[("selected", "#ffffff")],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", COLORS["border"])],
    )

    # Progressbar & Scrollbars
    style.configure(
        "Horizontal.TProgressbar",
        background=COLORS["accent"],
        troughcolor=COLORS["bg_input"],
        bordercolor=COLORS["border"],
        thickness=10,
    )
    style.configure(
        "Vertical.TScrollbar",
        background=COLORS["bg_surface_alt"],
        troughcolor=COLORS["bg_input"],
        bordercolor=COLORS["border"],
        arrowcolor=COLORS["text_secondary"],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=COLORS["bg_surface_alt"],
        troughcolor=COLORS["bg_input"],
        bordercolor=COLORS["border"],
        arrowcolor=COLORS["text_secondary"],
    )

    return style