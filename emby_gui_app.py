from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import Any, Callable
import tkinter as tk
from tkinter import messagebox, ttk

from emby_batch import EmbyClient, EmbyError, __version__, parse_library_ids
from emby_gui import (
    APP_TITLE,
    complete_directory_path,
    load_settings,
    resource_path,
    save_settings,
    settings_path,
)

from emby_gui_theme import (
    BG,
    SIDEBAR,
    HEADER,
    CARD,
    BORDER,
    TEXT,
    MUTED,
    PRIMARY,
    PRIMARY_ACTIVE,
    PRIMARY_SOFT,
    SUCCESS,
    WARNING,
    DANGER,
    apply_theme,
)


def tree_sort_key(value: Any) -> tuple[int, Any]:
    """Return a stable, user-friendly sort key for Treeview cell values."""
    text = str(value or "").strip()
    if not text:
        return (2, "")
    try:
        return (0, int(text))
    except ValueError:
        return (1, text.casefold())
from emby_gui_actor import ActorTabMixin
from emby_gui_director import DirectorTabMixin
from emby_gui_missing import MissingActorsTabMixin
from emby_gui_people import PeopleQualityTabMixin


class EmbyBatchApp(
    ActorTabMixin,
    MissingActorsTabMixin,
    DirectorTabMixin,
    PeopleQualityTabMixin,
):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE}  v{__version__}")
        self.root.geometry("1380x840")
        self.root.minsize(1160, 700)
        self.logo_image: tk.PhotoImage | None = None
        self.apply_branding()

        self.settings = load_settings()
        self.busy = False
        self.actor_rows: list[dict[str, Any]] = []
        self.missing_rows: list[dict[str, Any]] = []
        self.director_rows: list[dict[str, Any]] = []
        self.action_buttons: list[Any] = []
        self.scope_sync_callbacks: list[Callable[[], None]] = []
        self.library_dropdown_popup: tk.Toplevel | None = None
        self.library_dropdown_root_click_bind: str | None = None

        self.url_var = tk.StringVar(value=str(self.settings["connection"].get("url") or ""))
        self.api_key_var = tk.StringVar(value=str(self.settings["connection"].get("api_key") or ""))
        self.verify_ssl_var = tk.BooleanVar(value=bool(self.settings["connection"].get("verify_ssl", True)))
        self.show_key_var = tk.BooleanVar(value=False)
        self.timeout_var = tk.StringVar(value=str(self.settings["connection"].get("timeout", 60)))

        libs = self.settings["libraries"]
        library_names = self.settings.get("library_names") or {}
        scopes = self.settings["scopes"]
        paths = self.settings["paths"]
        self.actor_lib_var = tk.StringVar(value=str(libs.get("delete_actor_images") or ""))
        self.missing_lib_var = tk.StringVar(value=str(libs.get("scan_missing_actors") or ""))
        self.people_lib_var = tk.StringVar(value=str(libs.get("people_quality") or ""))
        self.director_lib_var = tk.StringVar(value=str(libs.get("delete_directors") or ""))
        self.library_name_maps: dict[str, dict[str, str]] = {}
        for key in ("delete_actor_images", "scan_missing_actors", "people_quality", "delete_directors"):
            raw_names = library_names.get(key) if isinstance(library_names, dict) else {}
            if not isinstance(raw_names, dict):
                raw_names = {}
            self.library_name_maps[key] = {
                str(library_id): str(name)
                for library_id, name in raw_names.items()
                if str(library_id).strip() and str(name).strip()
            }
        self.actor_lib_name_var = tk.StringVar(
            value=self.library_selection_text("delete_actor_images", self.actor_lib_var.get())
        )
        self.missing_lib_name_var = tk.StringVar(
            value=self.library_selection_text("scan_missing_actors", self.missing_lib_var.get())
        )
        self.people_lib_name_var = tk.StringVar(
            value=self.library_selection_text("people_quality", self.people_lib_var.get())
        )
        self.director_lib_name_var = tk.StringVar(
            value=self.library_selection_text("delete_directors", self.director_lib_var.get())
        )
        self.actor_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("delete_actor_images")))
        self.missing_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("scan_missing_actors")))
        self.people_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("people_quality")))
        self.director_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("delete_directors")))
        self.include_video_var = tk.BooleanVar(
            value=bool(self.settings["scan_missing_actors"].get("include_video", False))
        )
        self.directory_prefix_var = tk.StringVar(value=str(paths.get("directory_prefix") or ""))
        self.status_var = tk.StringVar(value=f"设置文件：{settings_path()}")
        self.connection_status_var = tk.StringVar(value="未测试连接")
        self.sidebar_status_var = tk.StringVar(value="就绪")
        self.page_title_var = tk.StringVar(value="演员头像清理")
        self.page_subtitle_var = tk.StringVar(
            value="扫描指定媒体库中的演员头像，预览确认后再执行清理。"
        )
        self.actor_result_var = tk.StringVar(value="0 条")
        self.missing_result_var = tk.StringVar(value="0 部")
        self.director_result_var = tk.StringVar(value="0 部")
        self.nav_buttons: dict[str, tk.Button] = {}
        self.page_frames: dict[str, tk.Frame] = {}
        self.current_page = "actor"
        self.sidebar_logo: tk.PhotoImage | None = None

        self.build_ui()
        self.root.bind("<Configure>", self.on_root_configure, add="+")
        self.root.bind("<Unmap>", lambda _event: self.close_library_dropdown(), add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def apply_branding(self) -> None:
        try:
            self.logo_image = tk.PhotoImage(file=str(resource_path("assets/emby.png")))
            self.root.iconphoto(True, self.logo_image)
        except Exception:
            self.logo_image = None

    def build_ui(self) -> None:
        apply_theme(self.root)

        shell = tk.Frame(self.root, background=BG, bd=0)
        shell.pack(fill="both", expand=True)

        sidebar = tk.Frame(
            shell,
            background=SIDEBAR,
            width=218,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, background=SIDEBAR, bd=0)
        brand.pack(fill="x", padx=16, pady=(18, 18))
        if self.logo_image is not None:
            try:
                width = max(1, int(self.logo_image.width()))
                factor = max(1, (width + 31) // 32)
                self.sidebar_logo = self.logo_image.subsample(factor, factor)
            except Exception:
                self.sidebar_logo = self.logo_image
        if self.sidebar_logo is not None:
            tk.Label(
                brand,
                image=self.sidebar_logo,
                background=SIDEBAR,
                bd=0,
            ).pack(side="left", padx=(0, 10))
        brand_text = tk.Frame(brand, background=SIDEBAR, bd=0)
        brand_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            brand_text,
            text="EMBY Doctor",
            background=SIDEBAR,
            foreground=TEXT,
            font=("Microsoft YaHei UI", 14, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            brand_text,
            text="Emby 媒体库维护工具",
            background=SIDEBAR,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        tk.Label(
            sidebar,
            text="功能导航",
            background=SIDEBAR,
            foreground="#8A97A8",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(2, 6))

        self._build_nav_button(sidebar, "actor", "演员头像清理")
        self._build_nav_button(sidebar, "missing", "无演员影片扫描")
        self._build_nav_button(sidebar, "people", "重复人物与质检")
        self._build_nav_button(sidebar, "director", "导演信息清理")

        tk.Label(
            sidebar,
            text="系统状态",
            background=SIDEBAR,
            foreground="#8A97A8",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x", padx=18, pady=(22, 6))

        status_card = tk.Frame(
            sidebar,
            background="#FFFFFF",
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        status_card.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(
            status_card,
            text="●",
            background="#FFFFFF",
            foreground=SUCCESS,
            font=("Microsoft YaHei UI", 9),
        ).grid(row=0, column=0, padx=(10, 5), pady=(10, 3), sticky="w")
        tk.Label(
            status_card,
            textvariable=self.sidebar_status_var,
            background="#FFFFFF",
            foreground=TEXT,
            font=("Microsoft YaHei UI", 9, "bold"),
            anchor="w",
        ).grid(row=0, column=1, padx=(0, 10), pady=(10, 3), sticky="w")
        tk.Label(
            status_card,
            textvariable=self.connection_status_var,
            background="#FFFFFF",
            foreground=MUTED,
            font=("Microsoft YaHei UI", 8),
            anchor="w",
            justify="left",
            wraplength=170,
        ).grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        sidebar_footer = tk.Frame(sidebar, background=SIDEBAR, bd=0)
        sidebar_footer.pack(side="bottom", fill="x", padx=16, pady=14)
        tk.Label(
            sidebar_footer,
            text=f"版本 v{__version__}",
            background=SIDEBAR,
            foreground="#94A0AF",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x")

        content_area = tk.Frame(shell, background=BG, bd=0)
        content_area.pack(side="left", fill="both", expand=True)

        header = tk.Frame(
            content_area,
            background=HEADER,
            height=88,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        header_left = tk.Frame(header, background=HEADER, bd=0)
        header_left.pack(side="left", fill="both", expand=True, padx=20, pady=14)
        ttk.Label(
            header_left,
            textvariable=self.page_title_var,
            style="PageTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            header_left,
            textvariable=self.page_subtitle_var,
            style="PageSubtitle.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        header_right = tk.Frame(header, background=HEADER, bd=0)
        header_right.pack(side="right", padx=20)
        tk.Label(
            header_right,
            text=f"v{__version__}",
            background=PRIMARY_SOFT,
            foreground=PRIMARY,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=4,
        ).pack(side="right")

        status_bar = tk.Frame(
            content_area,
            background=HEADER,
            height=30,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        status_bar.pack(side="bottom", fill="x")
        ttk.Label(
            status_bar,
            textvariable=self.status_var,
            style="Status.TLabel",
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=14, pady=5)
        ttk.Label(
            status_bar,
            text=f"EMBY Doctor · {settings_path().name}",
            style="Status.TLabel",
        ).pack(side="right", padx=14, pady=5)

        body = tk.Frame(content_area, background=BG, bd=0)
        body.pack(fill="both", expand=True, padx=16, pady=14)

        self.connection_card = self._build_connection_card(body)
        self.connection_card.pack(fill="x", pady=(0, 12))

        self.page_host = tk.Frame(body, background=BG, bd=0)
        self.page_host.pack(fill="both", expand=True)
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)

        self.actor_tab = tk.Frame(self.page_host, background=BG, bd=0)
        self.missing_tab = tk.Frame(self.page_host, background=BG, bd=0)
        self.people_tab = tk.Frame(self.page_host, background=BG, bd=0)
        self.director_tab = tk.Frame(self.page_host, background=BG, bd=0)
        self.page_frames = {
            "actor": self.actor_tab,
            "missing": self.missing_tab,
            "people": self.people_tab,
            "director": self.director_tab,
        }
        for frame in self.page_frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

        self.build_actor_tab()
        self.build_missing_tab()
        self.build_people_quality_tab()
        self.build_director_tab()
        self.refresh_result_counts()
        self.show_page("actor")

    def make_card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(
            parent,
            background=CARD,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
        )

    def _build_connection_card(self, parent: tk.Widget) -> tk.Frame:
        card = self.make_card(parent)
        inner = ttk.Frame(card, style="Card.TFrame", padding=(14, 10))
        inner.pack(fill="both", expand=True)

        head = ttk.Frame(inner, style="Card.TFrame")
        head.pack(fill="x", pady=(0, 9))
        ttk.Label(head, text="Emby 连接", style="Section.TLabel").pack(side="left")
        tk.Label(
            head,
            textvariable=self.connection_status_var,
            background="#F3F7FD",
            foreground=MUTED,
            font=("Microsoft YaHei UI", 8),
            padx=9,
            pady=3,
        ).pack(side="right")

        row = ttk.Frame(inner, style="Card.TFrame")
        row.pack(fill="x")
        row.columnconfigure(0, weight=4)
        row.columnconfigure(1, weight=4)
        row.columnconfigure(2, weight=1)
        row.columnconfigure(3, weight=0)

        address = ttk.Frame(row, style="Card.TFrame")
        address.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(address, text="服务器地址", style="Muted.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Entry(address, textvariable=self.url_var).pack(fill="x")

        api = ttk.Frame(row, style="Card.TFrame")
        api.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(api, text="API Key", style="Muted.TLabel").pack(anchor="w", pady=(0, 3))
        self.api_entry = ttk.Entry(api, textvariable=self.api_key_var, show="●")
        self.api_entry.pack(fill="x")

        timeout = ttk.Frame(row, style="Card.TFrame")
        timeout.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        ttk.Label(timeout, text="超时(秒)", style="Muted.TLabel").pack(anchor="w", pady=(0, 3))
        ttk.Entry(timeout, textvariable=self.timeout_var, width=8).pack(fill="x")

        actions = ttk.Frame(row, style="Card.TFrame")
        actions.grid(row=0, column=3, sticky="se")
        b_test = ttk.Button(actions, text="测试连接", style="Primary.TButton", command=self.test_connection)
        b_test.pack(side="left", padx=(0, 6))
        b_save = ttk.Button(actions, text="保存设置", style="Secondary.TButton", command=self.save_all_settings)
        b_save.pack(side="left")
        self.action_buttons.extend([b_test, b_save])

        options = ttk.Frame(inner, style="Card.TFrame")
        options.pack(fill="x", pady=(9, 0))
        ttk.Checkbutton(
            options,
            text="显示 API Key",
            style="Card.TCheckbutton",
            variable=self.show_key_var,
            command=lambda: self.api_entry.configure(show="" if self.show_key_var.get() else "●"),
        ).pack(side="left")
        ttk.Checkbutton(
            options,
            text="校验 HTTPS 证书",
            style="Card.TCheckbutton",
            variable=self.verify_ssl_var,
        ).pack(side="left", padx=(12, 18))
        ttk.Label(options, text="目录路径前缀", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(options, textvariable=self.directory_prefix_var).pack(side="left", fill="x", expand=True)
        ttk.Label(
            options,
            text=r"例：\\192.168.1.10",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))

        return card

    def _build_nav_button(self, parent: tk.Widget, key: str, text: str) -> None:
        button = tk.Button(
            parent,
            text=text,
            command=lambda current=key: self.show_page(current),
            anchor="w",
            background=SIDEBAR,
            foreground=TEXT,
            activebackground=PRIMARY_SOFT,
            activeforeground=PRIMARY,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=16,
            pady=9,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10),
        )
        button.pack(fill="x", padx=10, pady=2)
        self.nav_buttons[key] = button

    def show_page(self, key: str) -> None:
        titles = {
            "actor": (
                "演员头像清理",
                "扫描指定媒体库中的演员头像，预览确认后再执行清理。",
            ),
            "missing": (
                "无演员影片扫描",
                "查找没有 Actor 信息的影片，并支持批量刷新元数据。",
            ),
            "people": (
                "重复人物与质检",
                "按 Provider ID、姓名与资料完整度识别重复 Person，并安全迁移影片关联。",
            ),
            "director": (
                "导演信息清理",
                "扫描影片 Director 信息，备份后批量移除。",
            ),
        }
        frame = self.page_frames.get(key)
        if frame is None:
            return
        self.current_page = key
        frame.tkraise()
        if key == "people":
            self.connection_card.pack_forget()
        elif not self.connection_card.winfo_manager():
            self.connection_card.pack(fill="x", pady=(0, 12), before=self.page_host)
        title, subtitle = titles[key]
        self.page_title_var.set(title)
        self.page_subtitle_var.set(subtitle)
        self.close_library_dropdown()
        for nav_key, button in self.nav_buttons.items():
            active = nav_key == key
            button.configure(
                background=PRIMARY if active else SIDEBAR,
                foreground="#FFFFFF" if active else TEXT,
                activebackground=PRIMARY_ACTIVE if active else PRIMARY_SOFT,
                activeforeground="#FFFFFF" if active else PRIMARY,
                font=("Microsoft YaHei UI", 10, "bold" if active else "normal"),
            )

    def refresh_result_counts(self) -> None:
        self.actor_result_var.set(f"{len(self.actor_rows)} 条")
        self.missing_result_var.set(f"{len(self.missing_rows)} 部")
        self.director_result_var.set(f"{len(self.director_rows)} 部")

    @staticmethod
    def normalize_scope(value: Any) -> str:
        return "all" if str(value or "").lower() == "all" else "selected"

    def top_controls(
        self,
        parent: ttk.Frame,
        selection_key: str,
        variable: tk.StringVar,
        display_var: tk.StringVar,
        scope_var: tk.StringVar,
    ) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.pack(fill="x", pady=(0, 8))

        ttk.Label(frame, text="媒体库范围", style="Muted.TLabel").pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            frame,
            text="全部媒体库",
            style="Card.TRadiobutton",
            variable=scope_var,
            value="all",
        ).pack(side="left")
        ttk.Radiobutton(
            frame,
            text="指定媒体库",
            style="Card.TRadiobutton",
            variable=scope_var,
            value="selected",
        ).pack(side="left", padx=(8, 8))

        selector_shell = tk.Frame(
            frame,
            background=CARD,
            highlightbackground=BORDER,
            highlightcolor=PRIMARY,
            highlightthickness=1,
            bd=0,
        )
        selector_shell.pack(side="left", fill="x", expand=True)

        chip_frame = tk.Frame(selector_shell, background=CARD)
        chip_frame.pack(side="left", fill="x", expand=True, padx=(7, 3), pady=4)

        dropdown_button = ttk.Button(selector_shell, text="⌄", width=3, style="Secondary.TButton")
        dropdown_button.pack(side="right", padx=(0, 3), pady=2)

        def render_chips(*_args: Any) -> None:
            for child in chip_frame.winfo_children():
                child.destroy()

            ids = parse_library_ids([variable.get()])
            names = self.library_name_maps.get(selection_key, {})
            selected_names = [names.get(library_id, "").strip() for library_id in ids]
            selected_names = [name for name in selected_names if name]

            if not ids:
                tk.Label(
                    chip_frame,
                    text="请选择媒体库",
                    background=CARD,
                    foreground="#777777",
                    bd=0,
                    padx=2,
                    pady=1,
                ).pack(side="left")
                return

            if not selected_names:
                selected_names = [f"已选择 {len(ids)} 个"]

            max_visible = 6
            for name in selected_names[:max_visible]:
                tk.Label(
                    chip_frame,
                    text=name,
                    background="#ececf0",
                    foreground="#333333",
                    bd=0,
                    padx=7,
                    pady=2,
                ).pack(side="left", padx=(0, 5))

            hidden = len(selected_names) - max_visible
            if hidden > 0:
                tk.Label(
                    chip_frame,
                    text=f"+{hidden}",
                    background="#ececf0",
                    foreground="#555555",
                    bd=0,
                    padx=7,
                    pady=2,
                ).pack(side="left")

        def toggle_dropdown(_event: Any = None) -> str:
            if self.busy or self.normalize_scope(scope_var.get()) != "selected":
                return "break"
            self.toggle_library_dropdown(
                selector_shell,
                selection_key,
                variable,
                display_var,
                scope_var,
            )
            return "break"

        selector_shell.bind("<Button-1>", toggle_dropdown)
        chip_frame.bind("<Button-1>", toggle_dropdown)
        dropdown_button.configure(command=toggle_dropdown)
        self.action_buttons.append(dropdown_button)

        def sync_scope_selector(*_args: Any) -> None:
            selected = self.normalize_scope(scope_var.get()) == "selected"
            dropdown_button.configure(state="normal" if selected and not self.busy else "disabled")
            if not selected:
                self.close_library_dropdown()

        variable.trace_add("write", render_chips)
        display_var.trace_add("write", render_chips)
        scope_var.trace_add("write", sync_scope_selector)
        self.scope_sync_callbacks.append(sync_scope_selector)
        render_chips()
        sync_scope_selector()
        return frame

    def library_selection_text(self, selection_key: str, value: str) -> str:
        ids = parse_library_ids([value])
        if not ids:
            return "尚未选择"
        names = self.library_name_maps.get(selection_key, {})
        resolved = [names.get(library_id, "").strip() for library_id in ids]
        if all(resolved):
            return "、".join(resolved)
        visible = [name for name in resolved if name]
        missing = len(ids) - len(visible)
        if visible:
            return "、".join(visible) + f"（另 {missing} 个名称待刷新）"
        return f"已保存 {len(ids)} 个媒体库（点击下拉框加载名称）"

    def library_display_name(self, selection_key: str, library_id: str) -> str:
        name = self.library_name_maps.get(selection_key, {}).get(str(library_id), "").strip()
        if name:
            return name
        ids = parse_library_ids([
            {
                "delete_actor_images": self.actor_lib_var.get(),
                "scan_missing_actors": self.missing_lib_var.get(),
                "people_quality": self.people_lib_var.get(),
                "delete_directors": self.director_lib_var.get(),
            }.get(selection_key, "")
        ])
        try:
            return f"媒体库 {ids.index(str(library_id)) + 1}"
        except ValueError:
            return "媒体库"

    def refresh_library_names(self, libraries: list[dict[str, str]]) -> None:
        available = {
            str(item.get("Id") or ""): str(item.get("Name") or "")
            for item in libraries
            if str(item.get("Id") or "").strip()
        }
        bindings = (
            ("delete_actor_images", self.actor_lib_var, self.actor_lib_name_var),
            ("scan_missing_actors", self.missing_lib_var, self.missing_lib_name_var),
            ("people_quality", self.people_lib_var, self.people_lib_name_var),
            ("delete_directors", self.director_lib_var, self.director_lib_name_var),
        )
        for selection_key, variable, display_var in bindings:
            name_map = self.library_name_maps.setdefault(selection_key, {})
            for library_id in parse_library_ids([variable.get()]):
                if available.get(library_id):
                    name_map[library_id] = available[library_id]
            display_var.set(self.library_selection_text(selection_key, variable.get()))

    def on_root_configure(self, event: tk.Event) -> None:
        if event.widget is self.root and self.library_dropdown_popup is not None:
            self.close_library_dropdown()

    def close_library_dropdown(self) -> None:
        popup = self.library_dropdown_popup
        self.library_dropdown_popup = None
        bind_id = self.library_dropdown_root_click_bind
        self.library_dropdown_root_click_bind = None
        if bind_id:
            try:
                self.root.unbind("<Button-1>", bind_id)
            except Exception:
                pass
        if popup is None:
            return
        try:
            popup.destroy()
        except Exception:
            pass

    def toggle_library_dropdown(
        self,
        anchor: tk.Frame,
        selection_key: str,
        variable: tk.StringVar,
        display_var: tk.StringVar,
        scope_var: tk.StringVar,
    ) -> None:
        if self.library_dropdown_popup is not None:
            self.close_library_dropdown()
            return

        try:
            libraries = self.client().list_libraries()
        except Exception as exc:
            self.job_error(exc)
            return

        if not libraries:
            messagebox.showwarning(APP_TITLE, "Emby 没有返回可选择的媒体库。")
            return

        self.refresh_library_names(libraries)
        current_ids = set(parse_library_ids([variable.get()]))

        popup = tk.Toplevel(self.root)
        self.library_dropdown_popup = popup
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self.root)

        shell = tk.Frame(
            popup,
            background=CARD,
            highlightbackground="#d9dde3",
            highlightthickness=1,
            bd=0,
        )
        shell.pack(fill="both", expand=True)

        body = tk.Frame(shell, background=CARD)
        body.pack(fill="both", expand=True, padx=10, pady=(9, 6))

        flags: dict[str, tk.BooleanVar] = {}

        def draw_checkbox(canvas: tk.Canvas, checked: bool) -> None:
            canvas.delete("all")
            if checked:
                canvas.create_rectangle(
                    2, 2, 16, 16,
                    outline="#2563eb",
                    fill="#2563eb",
                    width=1,
                )
                canvas.create_line(
                    5, 9, 8, 12, 13, 6,
                    fill="#ffffff",
                    width=2,
                    capstyle="round",
                    joinstyle="round",
                )
            else:
                canvas.create_rectangle(
                    2, 2, 16, 16,
                    outline="#b8bec7",
                    fill="#ffffff",
                    width=1,
                )

        for item in libraries:
            library_id = str(item["Id"])
            library_name = str(item["Name"])
            self.library_name_maps.setdefault(selection_key, {})[library_id] = library_name
            flag = tk.BooleanVar(value=library_id in current_ids)
            flags[library_id] = flag

            row = tk.Frame(body, background=CARD, bd=0, highlightthickness=0)
            row.pack(fill="x", pady=1)

            box = tk.Canvas(
                row,
                width=18,
                height=18,
                background=CARD,
                highlightthickness=0,
                bd=0,
            )
            box.pack(side="left", padx=(2, 8), pady=4)

            label = tk.Label(
                row,
                text=library_name,
                background=CARD,
                foreground="#222222",
                anchor="w",
                bd=0,
                padx=0,
                pady=0,
            )
            label.pack(side="left", fill="x", expand=True, pady=4)

            def refresh_box(
                *_args: Any,
                current_box: tk.Canvas = box,
                current_flag: tk.BooleanVar = flag,
            ) -> None:
                draw_checkbox(current_box, bool(current_flag.get()))

            flag.trace_add("write", refresh_box)
            refresh_box()

            def set_hover(
                active: bool,
                current_row: tk.Frame = row,
                current_box: tk.Canvas = box,
                current_label: tk.Label = label,
            ) -> None:
                bg = "#f7f8fa" if active else "#ffffff"
                current_row.configure(background=bg)
                current_box.configure(background=bg)
                current_label.configure(background=bg)

            def toggle_item(
                _event: Any = None,
                current_flag: tk.BooleanVar = flag,
            ) -> str:
                current_flag.set(not current_flag.get())
                self.apply_library_checkbox_selection(
                    libraries,
                    flags,
                    selection_key,
                    variable,
                    display_var,
                    scope_var,
                )
                return "break"

            for widget in (row, box, label):
                widget.bind("<Button-1>", toggle_item)
                widget.bind("<Enter>", lambda _e, r=row, b=box, l=label: set_hover(True, r, b, l))
                widget.bind("<Leave>", lambda _e, r=row, b=box, l=label: set_hover(False, r, b, l))

        tk.Frame(shell, background="#e5e7eb", height=1, bd=0).pack(fill="x", padx=10, pady=(2, 0))

        footer = tk.Frame(shell, background=CARD, bd=0)
        footer.pack(fill="x", padx=10, pady=8)

        def flat_button(parent: tk.Widget, text: str, command: Callable[[], None]) -> tk.Button:
            return tk.Button(
                parent,
                text=text,
                command=command,
                background=CARD,
                activebackground="#f3f4f6",
                foreground="#222222",
                activeforeground="#222222",
                relief="flat",
                bd=0,
                highlightthickness=1,
                highlightbackground="#d9dde3",
                highlightcolor="#c7cdd6",
                padx=12,
                pady=3,
                cursor="hand2",
            )

        flat_button(
            footer,
            "全选",
            lambda: self.set_all_library_checkboxes(
                True,
                libraries,
                flags,
                selection_key,
                variable,
                display_var,
                scope_var,
            ),
        ).pack(side="left")

        flat_button(
            footer,
            "清空",
            lambda: self.set_all_library_checkboxes(
                False,
                libraries,
                flags,
                selection_key,
                variable,
                display_var,
                scope_var,
            ),
        ).pack(side="left", padx=(7, 0))

        flat_button(
            footer,
            "完成",
            self.close_library_dropdown,
        ).pack(side="right")

        popup.update_idletasks()
        width = max(280, min(anchor.winfo_width(), 340))
        height = popup.winfo_reqheight()
        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2

        screen_height = popup.winfo_screenheight()
        if y + height > screen_height - 40:
            y = max(0, anchor.winfo_rooty() - height - 2)

        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.deiconify()
        popup.lift()
        popup.focus_force()
        popup.bind("<Escape>", lambda _event: self.close_library_dropdown())

        def close_on_root_click(_event: tk.Event) -> None:
            if self.library_dropdown_popup is popup:
                self.root.after_idle(self.close_library_dropdown)

        self.library_dropdown_root_click_bind = self.root.bind(
            "<Button-1>",
            close_on_root_click,
            add="+",
        )

        # Keep Tk variable wrappers alive while the popup is open.
        popup._library_flags = flags  # type: ignore[attr-defined]

    def set_all_library_checkboxes(
        self,
        selected: bool,
        libraries: list[dict[str, str]],
        flags: dict[str, tk.BooleanVar],
        selection_key: str,
        variable: tk.StringVar,
        display_var: tk.StringVar,
        scope_var: tk.StringVar,
    ) -> None:
        for flag in flags.values():
            flag.set(selected)
        self.apply_library_checkbox_selection(
            libraries,
            flags,
            selection_key,
            variable,
            display_var,
            scope_var,
        )

    def apply_library_checkbox_selection(
        self,
        libraries: list[dict[str, str]],
        flags: dict[str, tk.BooleanVar],
        selection_key: str,
        variable: tk.StringVar,
        display_var: tk.StringVar,
        scope_var: tk.StringVar,
    ) -> None:
        selected = [
            item
            for item in libraries
            if flags.get(str(item["Id"])) is not None
            and flags[str(item["Id"])].get()
        ]
        variable.set(",".join(str(item["Id"]) for item in selected))

        name_map = self.library_name_maps.setdefault(selection_key, {})
        for item in libraries:
            name_map[str(item["Id"])] = str(item["Name"])

        display_var.set(
            "、".join(str(item["Name"]) for item in selected)
            if selected
            else "尚未选择"
        )
        scope_var.set("selected")
        self.save_all_settings(show_message=False)

    def make_tree(self, parent: tk.Widget, columns: list[tuple[str, str, int]]) -> ttk.Treeview:
        wrap = ttk.Frame(parent, style="Card.TFrame")
        wrap.pack(fill="both", expand=True)
        names = [c[0] for c in columns]
        tree = ttk.Treeview(
            wrap,
            columns=names,
            show="headings",
            selectmode="extended",
            style="Modern.Treeview",
        )
        heading_titles = {key: title for key, title, _width in columns}
        tree._heading_titles = heading_titles  # type: ignore[attr-defined]
        tree._sort_state = {}  # type: ignore[attr-defined]
        for key, title, width in columns:
            tree.heading(
                key,
                text=title,
                command=lambda current_tree=tree, column=key: self.sort_tree(
                    current_tree,
                    column,
                ),
            )
            tree.column(key, width=width, minwidth=80, anchor="w")
        tree.bind(
            "<Double-1>",
            lambda event, current_tree=tree: self.open_tree_directory(event, current_tree),
            add="+",
        )
        y = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return tree

    def sort_tree(self, tree: ttk.Treeview, column: str) -> None:
        sort_state: dict[str, bool] = getattr(tree, "_sort_state", {})
        descending = sort_state.get(column, False)
        rows = [
            (tree_sort_key(tree.set(item_id, column)), item_id)
            for item_id in tree.get_children("")
        ]
        rows.sort(key=lambda item: item[0], reverse=descending)
        for index, (_value, item_id) in enumerate(rows):
            tree.move(item_id, "", index)

        sort_state.clear()
        sort_state[column] = not descending
        tree._sort_state = sort_state  # type: ignore[attr-defined]

        heading_titles: dict[str, str] = getattr(tree, "_heading_titles", {})
        for key in tree["columns"]:
            title = heading_titles.get(str(key), str(key))
            suffix = ""
            if str(key) == column:
                suffix = " ▼" if descending else " ▲"
            tree.heading(
                key,
                text=f"{title}{suffix}",
                command=lambda current_tree=tree, current_column=str(key): self.sort_tree(
                    current_tree,
                    current_column,
                ),
            )

    def open_tree_directory(self, event: tk.Event, tree: ttk.Treeview) -> str | None:
        if tree.identify_region(event.x, event.y) != "cell":
            return None

        column_id = tree.identify_column(event.x)
        if not column_id.startswith("#"):
            return None
        try:
            column_index = int(column_id[1:]) - 1
        except ValueError:
            return None

        columns = [str(value) for value in tree["columns"]]
        if column_index < 0 or column_index >= len(columns):
            return None
        if columns[column_index] != "directory":
            return None

        item_id = tree.identify_row(event.y)
        if not item_id:
            return None

        raw_directory = str(tree.set(item_id, "directory") or "").strip()
        # 演员列表可能汇总多个影片目录。双击时打开列表中的第一个目录，
        # 避免一次操作弹出大量资源管理器窗口。
        directory = raw_directory.split(" | ", 1)[0].strip()
        directory = complete_directory_path(directory, self.directory_prefix_var.get())
        if not directory:
            messagebox.showwarning(APP_TITLE, "该条目没有可用的目录路径。")
            return "break"

        try:
            if sys.platform == "win32":
                os.startfile(directory)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", directory])
            else:
                subprocess.Popen(["xdg-open", directory])
            self.status_var.set(f"已打开目录：{directory}")
        except Exception as exc:
            messagebox.showerror(
                APP_TITLE,
                f"无法打开目录：\n{directory}\n\n{exc}\n\n"
                "如果 Emby 返回的是服务器本地路径，请在通用设置中填写“打开目录路径前缀”。",
            )
        return "break"

    def clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)
        if tree is self.actor_tree:
            self.actor_rows = []
        elif tree is self.missing_tree:
            self.missing_rows = []
        elif tree is self.director_tree:
            self.director_rows = []
        self.refresh_result_counts()

    def collect_settings(self) -> dict[str, Any]:
        try:
            timeout = max(1, int(self.timeout_var.get().strip() or "60"))
        except ValueError:
            timeout = 60
            self.timeout_var.set("60")
        return {
            "connection": {
                "url": self.url_var.get().strip(),
                "api_key": self.api_key_var.get().strip(),
                "verify_ssl": bool(self.verify_ssl_var.get()),
                "timeout": timeout,
            },
            "paths": {
                "directory_prefix": self.directory_prefix_var.get().strip(),
            },
            "libraries": {
                "delete_actor_images": self.actor_lib_var.get().strip(),
                "scan_missing_actors": self.missing_lib_var.get().strip(),
                "people_quality": self.people_lib_var.get().strip(),
                "delete_directors": self.director_lib_var.get().strip(),
            },
            "library_names": {
                key: dict(value) for key, value in self.library_name_maps.items()
            },
            "scopes": {
                "delete_actor_images": self.normalize_scope(self.actor_scope_var.get()),
                "scan_missing_actors": self.normalize_scope(self.missing_scope_var.get()),
                "people_quality": self.normalize_scope(self.people_scope_var.get()),
                "delete_directors": self.normalize_scope(self.director_scope_var.get()),
            },
            "scan_missing_actors": {"include_video": bool(self.include_video_var.get())},
        }

    def save_all_settings(self, show_message: bool = True) -> None:
        self.settings = self.collect_settings()
        try:
            save_settings(self.settings)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"保存设置失败：\n{exc}")
            return
        self.status_var.set(f"设置已保存：{settings_path()}")
        if show_message:
            messagebox.showinfo(APP_TITLE, f"设置已保存到：\n{settings_path()}")

    def on_close(self) -> None:
        if not self.busy:
            self.save_all_settings(show_message=False)
        self.root.destroy()

    def client(self) -> EmbyClient:
        url = self.url_var.get().strip()
        key = self.api_key_var.get().strip()
        if not url:
            raise EmbyError("请填写 Emby 地址。")
        if not key:
            raise EmbyError("请填写 API Key。")
        try:
            timeout = max(1, int(self.timeout_var.get().strip() or "60"))
        except ValueError as exc:
            raise EmbyError("超时必须是整数秒数。") from exc
        return EmbyClient(url, key, verify_ssl=self.verify_ssl_var.get(), timeout=timeout)

    def libraries(self, value: str) -> list[str]:
        ids = parse_library_ids([value])
        if not ids:
            raise EmbyError("请选择“指定媒体库”后至少选择一个媒体库。")
        return ids

    def scope_libraries(self, scope: str, value: str) -> list[str | None]:
        if self.normalize_scope(scope) == "all":
            return [None]
        return self.libraries(value)

    def set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        self.sidebar_status_var.set("处理中…" if busy else "就绪")
        for btn in self.action_buttons:
            try:
                btn.configure(state="disabled" if busy else "normal")
            except Exception:
                pass
        for callback in self.scope_sync_callbacks:
            try:
                callback()
            except Exception:
                pass
        if text:
            self.status_var.set(text)

    def run_job(self, label: str, worker: Callable[[], Any], done: Callable[[Any], None] | None = None) -> None:
        if self.busy:
            return
        self.save_all_settings(show_message=False)
        self.set_busy(True, label)

        def target() -> None:
            try:
                result = worker()
            except Exception as exc:
                self.root.after(0, lambda err=exc: self.job_error(err))
                return
            self.root.after(0, lambda value=result: self.job_done(label, value, done))

        threading.Thread(target=target, daemon=True).start()

    def job_error(self, exc: Exception) -> None:
        self.set_busy(False, f"失败：{exc}")
        messagebox.showerror(APP_TITLE, str(exc))

    def job_done(self, label: str, result: Any, done: Callable[[Any], None] | None) -> None:
        self.set_busy(False, f"完成：{label}")
        if done:
            done(result)

    def test_connection(self) -> None:
        try:
            client = self.client()
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> tuple[dict[str, Any], list[dict[str, str]]]:
            return client.get_json("/System/Info"), client.list_libraries()

        def done(result: tuple[dict[str, Any], list[dict[str, str]]]) -> None:
            info, libraries = result
            self.refresh_library_names(libraries)
            self.save_all_settings(show_message=False)
            server_name = info.get("ServerName") or info.get("Name") or "Emby Server"
            version = info.get("Version") or "未知"
            self.connection_status_var.set(f"已连接 · {server_name} · v{version}")
            messagebox.showinfo(
                APP_TITLE,
                f"连接成功。\n服务器：{server_name}\n版本：{version}\n媒体库：{len(libraries)} 个",
            )

        self.run_job("正在测试 Emby 连接……", worker, done)


def run_gui() -> int:
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if sys.platform == "win32" and "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    EmbyBatchApp(root)
    root.mainloop()
    return 0
