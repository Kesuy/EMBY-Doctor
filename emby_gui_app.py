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


class EmbyBatchApp(ActorTabMixin, MissingActorsTabMixin, DirectorTabMixin):
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE}  v{__version__}")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)
        self.logo_image: tk.PhotoImage | None = None
        self.apply_branding()

        self.settings = load_settings()
        self.busy = False
        self.actor_rows: list[dict[str, Any]] = []
        self.missing_rows: list[dict[str, Any]] = []
        self.director_rows: list[dict[str, Any]] = []
        self.action_buttons: list[Any] = []
        self.scope_sync_callbacks: list[Callable[[], None]] = []

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
        self.director_lib_var = tk.StringVar(value=str(libs.get("delete_directors") or ""))
        self.library_name_maps: dict[str, dict[str, str]] = {}
        for key in ("delete_actor_images", "scan_missing_actors", "delete_directors"):
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
        self.director_lib_name_var = tk.StringVar(
            value=self.library_selection_text("delete_directors", self.director_lib_var.get())
        )
        self.actor_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("delete_actor_images")))
        self.missing_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("scan_missing_actors")))
        self.director_scope_var = tk.StringVar(value=self.normalize_scope(scopes.get("delete_directors")))
        self.include_video_var = tk.BooleanVar(
            value=bool(self.settings["scan_missing_actors"].get("include_video", False))
        )
        self.directory_prefix_var = tk.StringVar(value=str(paths.get("directory_prefix") or ""))
        self.status_var = tk.StringVar(value=f"设置文件：{settings_path()}")

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def apply_branding(self) -> None:
        try:
            self.logo_image = tk.PhotoImage(file=str(resource_path("assets/emby.png")))
            self.root.iconphoto(True, self.logo_image)
        except Exception:
            self.logo_image = None

    def build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        conn = ttk.LabelFrame(outer, text="Emby 通用连接设置", padding=10)
        conn.pack(fill="x")
        conn.columnconfigure(1, weight=1)
        conn.columnconfigure(3, weight=1)

        ttk.Label(conn, text="Emby 地址").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(conn, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(conn, text="API Key").grid(row=0, column=2, sticky="w", padx=(12, 6), pady=4)
        self.api_entry = ttk.Entry(conn, textvariable=self.api_key_var, show="●")
        self.api_entry.grid(row=0, column=3, sticky="ew", pady=4)

        ttk.Checkbutton(
            conn,
            text="显示 API Key",
            variable=self.show_key_var,
            command=lambda: self.api_entry.configure(show="" if self.show_key_var.get() else "●"),
        ).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Checkbutton(conn, text="校验 HTTPS 证书", variable=self.verify_ssl_var).grid(
            row=1, column=1, sticky="w", pady=4
        )
        ttk.Label(conn, text="超时(秒)").grid(row=1, column=2, sticky="e", padx=(12, 6), pady=4)
        ttk.Entry(conn, textvariable=self.timeout_var, width=8).grid(row=1, column=3, sticky="w", pady=4)

        ttk.Label(conn, text="打开目录路径前缀").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        ttk.Entry(conn, textvariable=self.directory_prefix_var).grid(
            row=2, column=1, columnspan=3, sticky="ew", pady=4
        )
        ttk.Label(
            conn,
            text=r"可选，例如 \\192.168.1.10；打开结果目录时会补全为 \\192.168.1.10\结果路径",
        ).grid(row=3, column=1, columnspan=3, sticky="w", pady=(0, 4))

        btns = ttk.Frame(conn)
        btns.grid(row=4, column=0, columnspan=4, sticky="e", pady=(8, 0))
        b_test = ttk.Button(btns, text="测试连接", command=self.test_connection)
        b_test.pack(side="left", padx=4)
        b_save = ttk.Button(btns, text="保存设置", command=self.save_all_settings)
        b_save.pack(side="left", padx=4)
        self.action_buttons.extend([b_test, b_save])

        ttk.Label(
            outer,
            text="提示：settings.json 会保存在 EXE 同目录，并包含 API Key 明文。请勿将该文件上传或分享。",
        ).pack(fill="x", pady=(6, 4))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True, pady=(4, 6))
        self.actor_tab = ttk.Frame(notebook, padding=10)
        self.missing_tab = ttk.Frame(notebook, padding=10)
        self.director_tab = ttk.Frame(notebook, padding=10)
        notebook.add(self.actor_tab, text="删除演员头像")
        notebook.add(self.missing_tab, text="扫描无演员影片")
        notebook.add(self.director_tab, text="删除导演信息")

        self.build_actor_tab()
        self.build_missing_tab()
        self.build_director_tab()
        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(fill="x")

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
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 8))

        ttk.Radiobutton(frame, text="全部媒体库", variable=scope_var, value="all").pack(side="left")
        ttk.Radiobutton(frame, text="指定媒体库", variable=scope_var, value="selected").pack(
            side="left", padx=(8, 8)
        )
        ttk.Label(frame, text="媒体库").pack(side="left")

        selector = ttk.Menubutton(frame, textvariable=display_var)
        selector.pack(side="left", fill="x", expand=True, padx=(8, 0))
        menu = tk.Menu(selector, tearoff=False)
        selector.configure(menu=menu)
        menu.configure(
            postcommand=lambda: self.populate_library_menu(
                menu,
                selection_key,
                variable,
                display_var,
                scope_var,
            )
        )
        self.action_buttons.append(selector)

        def sync_scope_selector(*_args: Any) -> None:
            selected = self.normalize_scope(scope_var.get()) == "selected"
            selector.configure(state="normal" if selected and not self.busy else "disabled")

        scope_var.trace_add("write", sync_scope_selector)
        self.scope_sync_callbacks.append(sync_scope_selector)
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
            ("delete_directors", self.director_lib_var, self.director_lib_name_var),
        )
        for selection_key, variable, display_var in bindings:
            name_map = self.library_name_maps.setdefault(selection_key, {})
            for library_id in parse_library_ids([variable.get()]):
                if available.get(library_id):
                    name_map[library_id] = available[library_id]
            display_var.set(self.library_selection_text(selection_key, variable.get()))

    def populate_library_menu(
        self,
        menu: tk.Menu,
        selection_key: str,
        variable: tk.StringVar,
        display_var: tk.StringVar,
        scope_var: tk.StringVar,
    ) -> None:
        menu.delete(0, "end")
        try:
            libraries = self.client().list_libraries()
        except Exception as exc:
            menu.add_command(label="加载媒体库失败", state="disabled")
            self.status_var.set(f"读取媒体库失败：{exc}")
            self.root.after_idle(
                lambda err=exc: messagebox.showerror(APP_TITLE, f"读取媒体库失败：\n{err}")
            )
            return

        if not libraries:
            menu.add_command(label="没有可用的媒体库", state="disabled")
            return

        self.refresh_library_names(libraries)
        current_ids = set(parse_library_ids([variable.get()]))
        flags: dict[str, tk.BooleanVar] = {}
        name_map = self.library_name_maps.setdefault(selection_key, {})

        for item in libraries:
            library_id = str(item["Id"])
            library_name = str(item["Name"])
            name_map[library_id] = library_name
            flag = tk.BooleanVar(value=library_id in current_ids)
            flags[library_id] = flag
            menu.add_checkbutton(
                label=library_name,
                variable=flag,
                command=lambda: self.apply_library_menu_selection(
                    libraries,
                    flags,
                    selection_key,
                    variable,
                    display_var,
                    scope_var,
                ),
            )

        menu.add_separator()
        menu.add_command(
            label="全选",
            command=lambda: self.set_all_library_menu_items(
                True,
                libraries,
                flags,
                selection_key,
                variable,
                display_var,
                scope_var,
            ),
        )
        menu.add_command(
            label="清空选择",
            command=lambda: self.set_all_library_menu_items(
                False,
                libraries,
                flags,
                selection_key,
                variable,
                display_var,
                scope_var,
            ),
        )

        # Keep Tk variable wrappers alive for the lifetime of this posted menu.
        menu._library_flags = flags  # type: ignore[attr-defined]

    def set_all_library_menu_items(
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
        self.apply_library_menu_selection(
            libraries,
            flags,
            selection_key,
            variable,
            display_var,
            scope_var,
        )

    def apply_library_menu_selection(
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

    def make_tree(self, parent: ttk.Frame, columns: list[tuple[str, str, int]]) -> ttk.Treeview:
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        names = [c[0] for c in columns]
        tree = ttk.Treeview(wrap, columns=names, show="headings", selectmode="extended")
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
                "delete_directors": self.director_lib_var.get().strip(),
            },
            "library_names": {
                key: dict(value) for key, value in self.library_name_maps.items()
            },
            "scopes": {
                "delete_actor_images": self.normalize_scope(self.actor_scope_var.get()),
                "scan_missing_actors": self.normalize_scope(self.missing_scope_var.get()),
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
