from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
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


def _parent_bg(widget: tk.Widget, fallback: str = CARD) -> str:
    try:
        return str(widget.cget("background"))
    except Exception:
        return fallback


def _rounded_points(width: int, height: int, radius: int) -> list[int]:
    radius = max(2, min(radius, width // 2, height // 2))
    return [
        radius, 1,
        width - radius, 1,
        width - 1, 1,
        width - 1, radius,
        width - 1, height - radius,
        width - 1, height - 1,
        width - radius, height - 1,
        radius, height - 1,
        1, height - 1,
        1, height - radius,
        1, radius,
        1, 1,
    ]


class RoundedButton(tk.Canvas):
    """Flat rounded button used across the desktop UI."""

    PALETTES = {
        "primary": (PRIMARY, PRIMARY_ACTIVE, "#A8C9F8", "#FFFFFF", PRIMARY, PRIMARY),
        "secondary": ("#FFFFFF", "#F3F7FD", "#F2F4F7", TEXT, BORDER, "#C8D6E7"),
        "danger": (DANGER, DANGER_ACTIVE, "#F0B3B3", "#FFFFFF", DANGER, DANGER),
        "ghost": (CARD, "#F3F6FA", "#F2F4F7", MUTED, CARD, CARD),
    }

    def __init__(
        self,
        master: tk.Widget,
        *,
        text: str,
        command=None,
        variant: str = "primary",
        width: int | None = None,
        height: int = 34,
        radius: int = 9,
        anchor: str = "center",
        font=FONT_SMALL,
        background: str | None = None,
        foreground: str | None = None,
        activebackground: str | None = None,
        activeforeground: str | None = None,
        bordercolor: str | None = None,
        padx: int = 14,
        state: str = "normal",
        cursor: str = "hand2",
        **kwargs,
    ):
        self._text = text
        self._command = command
        self._variant = variant if variant in self.PALETTES else "secondary"
        self._height = height
        self._radius = radius
        self._anchor = anchor
        self._font = font
        self._padx = padx
        self._state = state
        self._hover = False
        self._cursor = cursor
        palette = self.PALETTES[self._variant]
        self._fill = background or palette[0]
        self._active_fill = activebackground or palette[1]
        self._disabled_fill = palette[2]
        self._fg = foreground or palette[3]
        self._active_fg = activeforeground or self._fg
        self._border = bordercolor if bordercolor is not None else palette[4]
        self._active_border = palette[5]
        bg = _parent_bg(master)

        if width is None:
            try:
                measured = tkfont.Font(font=self._font).measure(text)
            except Exception:
                measured = max(40, len(text) * 12)
            width = measured + (self._padx * 2)

        super().__init__(
            master,
            width=max(42, int(width)),
            height=self._height,
            background=bg,
            highlightthickness=0,
            bd=0,
            relief="flat",
            cursor=self._cursor if state != "disabled" else "arrow",
            takefocus=1,
            **kwargs,
        )
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Return>", self._on_click)
        self.bind("<space>", self._on_click)
        self._redraw()

    def _redraw(self) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        disabled = self._state == "disabled"
        fill = self._disabled_fill if disabled else (self._active_fill if self._hover else self._fill)
        fg = "#F7F9FC" if disabled and self._variant in {"primary", "danger"} else (
            "#AAB4C3" if disabled else (self._active_fg if self._hover else self._fg)
        )
        border = self._border if not self._hover else self._active_border
        self.delete("all")
        self.create_polygon(
            _rounded_points(width, height, self._radius),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=border,
            width=1,
        )
        if self._anchor == "w":
            x = self._padx
            anchor = "w"
        else:
            x = width / 2
            anchor = "center"
        self.create_text(
            x,
            height / 2,
            text=self._text,
            fill=fg,
            font=self._font,
            anchor=anchor,
        )

    def _on_enter(self, _event=None) -> None:
        if self._state != "disabled":
            self._hover = True
            self._redraw()

    def _on_leave(self, _event=None) -> None:
        self._hover = False
        self._redraw()

    def _on_click(self, _event=None):
        if self._state != "disabled" and callable(self._command):
            return self._command()
        return None

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        redraw = False
        for key in (
            "text", "command", "state", "background", "foreground",
            "activebackground", "activeforeground", "font", "bordercolor",
        ):
            if key not in kwargs:
                continue
            value = kwargs.pop(key)
            if key == "text":
                self._text = str(value)
            elif key == "command":
                self._command = value
            elif key == "state":
                self._state = str(value)
                super().configure(cursor=self._cursor if self._state != "disabled" else "arrow")
            elif key == "background":
                self._fill = str(value)
            elif key == "foreground":
                self._fg = str(value)
            elif key == "activebackground":
                self._active_fill = str(value)
            elif key == "activeforeground":
                self._active_fg = str(value)
            elif key == "font":
                self._font = value
            elif key == "bordercolor":
                self._border = str(value)
            redraw = True
        if kwargs:
            super().configure(**kwargs)
        if redraw:
            self._redraw()

    config = configure


class RoundedEntry(tk.Canvas):
    """Borderless Entry hosted inside a rounded rectangle."""

    def __init__(
        self,
        master: tk.Widget,
        *,
        textvariable: tk.Variable | None = None,
        show: str = "",
        width: int | None = None,
        height: int = 34,
        radius: int = 9,
        background: str = CARD,
        foreground: str = TEXT,
        bordercolor: str = BORDER,
        focus_bordercolor: str = PRIMARY,
        font=FONT,
        **kwargs,
    ):
        self._height = height
        self._radius = radius
        self._fill = background
        self._border = bordercolor
        self._focus_border = focus_bordercolor
        self._focused = False
        bg = _parent_bg(master)
        pixel_width = 180 if width is None else max(70, int(width) * 10)
        super().__init__(
            master,
            height=height,
            width=pixel_width,
            background=bg,
            highlightthickness=0,
            bd=0,
            relief="flat",
            **kwargs,
        )
        self.entry = tk.Entry(
            self,
            textvariable=textvariable,
            show=show,
            relief="flat",
            bd=0,
            highlightthickness=0,
            background=self._fill,
            foreground=foreground,
            insertbackground=foreground,
            font=font,
        )
        self._window = self.create_window(10, height / 2, anchor="w", window=self.entry)
        self.bind("<Configure>", lambda _event: self._redraw())
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self._redraw()

    def _redraw(self) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("shape")
        self.create_polygon(
            _rounded_points(width, height, self._radius),
            smooth=True,
            splinesteps=24,
            fill=self._fill,
            outline=self._focus_border if self._focused else self._border,
            width=1,
            tags="shape",
        )
        self.tag_lower("shape")
        self.coords(self._window, 11, height / 2)
        self.itemconfigure(self._window, width=max(20, width - 22), height=max(20, height - 10))

    def _focus_in(self, _event=None) -> None:
        self._focused = True
        self._redraw()

    def _focus_out(self, _event=None) -> None:
        self._focused = False
        self._redraw()

    def get(self) -> str:
        return self.entry.get()

    def focus_set(self) -> None:
        self.entry.focus_set()

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        entry_keys = {"show", "state", "font", "foreground", "insertbackground"}
        entry_kwargs = {key: kwargs.pop(key) for key in list(kwargs) if key in entry_keys}
        if entry_kwargs:
            self.entry.configure(**entry_kwargs)
        if "background" in kwargs:
            self._fill = str(kwargs.pop("background"))
            self.entry.configure(background=self._fill)
            self._redraw()
        if "bordercolor" in kwargs:
            self._border = str(kwargs.pop("bordercolor"))
            self._redraw()
        if kwargs:
            super().configure(**kwargs)

    config = configure


class RoundedContainer(tk.Canvas):
    """Rounded shell with a normal Tk frame inside for compound controls."""

    def __init__(
        self,
        master: tk.Widget,
        *,
        height: int = 36,
        radius: int = 9,
        background: str = CARD,
        bordercolor: str = BORDER,
        active_bordercolor: str = PRIMARY,
        **kwargs,
    ):
        self._height = height
        self._radius = radius
        self._fill = background
        self._border = bordercolor
        self._active_border = active_bordercolor
        self._active = False
        super().__init__(
            master,
            height=height,
            background=_parent_bg(master),
            highlightthickness=0,
            bd=0,
            relief="flat",
            **kwargs,
        )
        self.content = tk.Frame(self, background=self._fill, bd=0)
        self._window = self.create_window(8, height / 2, anchor="w", window=self.content)
        self.bind("<Configure>", lambda _event: self._redraw())
        self._redraw()

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._redraw()

    def _redraw(self) -> None:
        width = max(2, self.winfo_width())
        height = max(2, self.winfo_height())
        self.delete("shape")
        self.create_polygon(
            _rounded_points(width, height, self._radius),
            smooth=True,
            splinesteps=24,
            fill=self._fill,
            outline=self._active_border if self._active else self._border,
            width=1,
            tags="shape",
        )
        self.tag_lower("shape")
        self.coords(self._window, 8, height / 2)
        self.itemconfigure(self._window, width=max(20, width - 16), height=max(20, height - 8))


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
