from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#F4F7FB"
SIDEBAR = "#F8FAFD"
HEADER = "#FFFFFF"
CARD = "#FFFFFF"
BORDER = "#DCE5F0"
TEXT = "#162033"
MUTED = "#718096"
PRIMARY = "#1677FF"
PRIMARY_ACTIVE = "#0F6AE6"
PRIMARY_SOFT = "#EAF3FF"
SUCCESS = "#20A66A"
SUCCESS_SOFT = "#EAF8F1"
WARNING = "#D98A00"
WARNING_SOFT = "#FFF6E3"
DANGER = "#E45757"
DANGER_ACTIVE = "#CC4545"
DANGER_SOFT = "#FFF0F0"

FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 18, "bold")
FONT_SECTION = ("Microsoft YaHei UI", 12, "bold")
FONT_NAV = ("Microsoft YaHei UI", 10)


class AutoHideScrollbar(ttk.Scrollbar):
    """Scrollbar that disappears while the whole content is visible."""

    def set(self, first: str, last: str) -> None:
        try:
            fully_visible = float(first) <= 0.0 and float(last) >= 1.0
        except (TypeError, ValueError):
            fully_visible = False
        if fully_visible:
            self.grid_remove()
        else:
            self.grid()
        super().set(first, last)


def apply_theme(root: tk.Tk) -> ttk.Style:
    root.configure(background=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=FONT, background=BG, foreground=TEXT)
    style.configure("App.TFrame", background=BG)
    style.configure("Header.TFrame", background=HEADER)
    style.configure("Card.TFrame", background=CARD)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT)
    style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=FONT_SMALL)
    style.configure("PageTitle.TLabel", background=HEADER, foreground=TEXT, font=FONT_TITLE)
    style.configure("PageSubtitle.TLabel", background=HEADER, foreground=MUTED, font=FONT_SMALL)
    style.configure("Section.TLabel", background=CARD, foreground=TEXT, font=FONT_SECTION)
    style.configure("Status.TLabel", background=HEADER, foreground=MUTED, font=FONT_SMALL)

    style.configure(
        "TEntry",
        fieldbackground=CARD,
        foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        insertcolor=TEXT,
        padding=(8, 6),
    )
    style.map("TEntry", bordercolor=[("focus", PRIMARY)])

    style.configure(
        "Card.TCheckbutton",
        background=CARD,
        foreground=TEXT,
        padding=(0, 2),
    )
    style.map(
        "Card.TCheckbutton",
        background=[("active", CARD), ("selected", CARD)],
        foreground=[("disabled", "#AAB4C3")],
    )
    style.configure(
        "Card.TRadiobutton",
        background=CARD,
        foreground=TEXT,
        padding=(0, 2),
    )
    style.map(
        "Card.TRadiobutton",
        background=[("active", CARD), ("selected", CARD)],
        foreground=[("disabled", "#AAB4C3")],
    )

    style.configure(
        "Primary.TButton",
        background=PRIMARY,
        foreground="#FFFFFF",
        borderwidth=0,
        focusthickness=0,
        padding=(14, 7),
        font=("Microsoft YaHei UI", 9, "bold"),
    )
    style.map(
        "Primary.TButton",
        background=[("disabled", "#A8C9F8"), ("active", PRIMARY_ACTIVE), ("pressed", PRIMARY_ACTIVE)],
        foreground=[("disabled", "#F2F6FC"), ("active", "#FFFFFF")],
    )

    style.configure(
        "Secondary.TButton",
        background="#FFFFFF",
        foreground=TEXT,
        borderwidth=1,
        relief="solid",
        padding=(13, 6),
        font=FONT_SMALL,
    )
    style.map(
        "Secondary.TButton",
        background=[("disabled", "#F2F4F7"), ("active", "#F3F7FD"), ("pressed", "#EAF2FD")],
        foreground=[("disabled", "#AAB4C3")],
    )

    style.configure(
        "Danger.TButton",
        background=DANGER,
        foreground="#FFFFFF",
        borderwidth=0,
        focusthickness=0,
        padding=(14, 7),
        font=("Microsoft YaHei UI", 9, "bold"),
    )
    style.map(
        "Danger.TButton",
        background=[("disabled", "#F0B3B3"), ("active", DANGER_ACTIVE), ("pressed", DANGER_ACTIVE)],
        foreground=[("disabled", "#FFF7F7")],
    )

    style.configure(
        "Ghost.TButton",
        background=CARD,
        foreground=MUTED,
        borderwidth=0,
        padding=(10, 6),
        font=FONT_SMALL,
    )
    style.map(
        "Ghost.TButton",
        background=[("active", "#F3F6FA"), ("pressed", "#EDF2F8")],
        foreground=[("active", TEXT), ("disabled", "#B8C0CB")],
    )

    style.configure(
        "Modern.Treeview",
        background=CARD,
        fieldbackground=CARD,
        foreground=TEXT,
        borderwidth=0,
        relief="flat",
        rowheight=31,
        font=FONT_SMALL,
    )
    style.map(
        "Modern.Treeview",
        background=[("selected", PRIMARY_SOFT)],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "Modern.Treeview.Heading",
        background="#F7F9FC",
        foreground="#526175",
        relief="flat",
        borderwidth=0,
        padding=(8, 8),
        font=("Microsoft YaHei UI", 9, "bold"),
    )
    style.map(
        "Modern.Treeview.Heading",
        background=[("active", "#EEF3F9")],
        foreground=[("active", TEXT)],
    )

    # Slim, arrow-less scrollbars that fit the flat card/table visual language.
    try:
        style.layout(
            "Modern.Vertical.TScrollbar",
            [
                (
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})
                        ],
                    },
                )
            ],
        )
        style.layout(
            "Modern.Horizontal.TScrollbar",
            [
                (
                    "Horizontal.Scrollbar.trough",
                    {
                        "sticky": "ew",
                        "children": [
                            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})
                        ],
                    },
                )
            ],
        )
    except tk.TclError:
        pass
    for scrollbar_style in ("Modern.Vertical.TScrollbar", "Modern.Horizontal.TScrollbar"):
        style.configure(
            scrollbar_style,
            background="#C9D3DF",
            troughcolor=CARD,
            bordercolor=CARD,
            lightcolor="#C9D3DF",
            darkcolor="#C9D3DF",
            arrowcolor=MUTED,
            relief="flat",
            borderwidth=0,
            gripcount=0,
            width=8,
        )
        style.map(
            scrollbar_style,
            background=[("active", "#AEBBCB"), ("pressed", "#96A6B9")],
        )

    return style
