from __future__ import annotations

import sys
import threading
from typing import Any, Callable
import tkinter as tk
from tkinter import messagebox, ttk

from emby_batch import EmbyClient, EmbyError, __version__, parse_library_ids
from emby_gui import APP_TITLE, load_settings, resource_path, save_settings, settings_path
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
        self.action_buttons: list[ttk.Button] = []

        self.url_var = tk.StringVar(value=str(self.settings["connection"].get("url") or ""))
        self.api_key_var = tk.StringVar(value=str(self.settings["connection"].get("api_key") or ""))
        self.verify_ssl_var = tk.BooleanVar(value=bool(self.settings["connection"].get("verify_ssl", True)))
        self.show_key_var = tk.BooleanVar(value=False)
        self.timeout_var = tk.StringVar(value=str(self.settings["connection"].get("timeout", 60)))

        libs = self.settings["libraries"]
        scopes = self.settings["scopes"]
        paths = self.settings["paths"]
        self.actor_lib_var = tk.StringVar(value=str(libs.get("delete_actor_images") or ""))
        self.missing_lib_var = tk.StringVar(value=str(libs.get("scan_missing_actors") or ""))
        self.director_lib_var = tk.StringVar(value=str(libs.get("delete_directors") or ""))
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
        variable: tk.StringVar,
        scope_var: tk.StringVar,
    ) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(0, 8))

        ttk.Radiobutton(frame, text="全部媒体库", variable=scope_var, value="all").pack(side="left")
        ttk.Radiobutton(frame, text="指定媒体库", variable=scope_var, value="selected").pack(
            side="left", padx=(8, 8)
        )
        ttk.Label(frame, text="媒体库 ID").pack(side="left")
        entry = ttk.Entry(frame, textvariable=variable)
        entry.pack(side="left", fill="x", expand=True, padx=8)

        def sync_scope_entry(*_args: Any) -> None:
            entry.configure(state="normal" if scope_var.get() == "selected" else "disabled")

        scope_var.trace_add("write", sync_scope_entry)
        sync_scope_entry()
        return frame

    def make_tree(self, parent: ttk.Frame, columns: list[tuple[str, str, int]]) -> ttk.Treeview:
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=True)
        names = [c[0] for c in columns]
        tree = ttk.Treeview(wrap, columns=names, show="headings", selectmode="extended")
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=80, anchor="w")
        y = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return tree

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
            raise EmbyError("请选择“指定媒体库”后填写至少一个媒体库 ID。")
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

        def worker() -> dict[str, Any]:
            return client.get_json("/System/Info")

        def done(result: dict[str, Any]) -> None:
            server_name = result.get("ServerName") or result.get("Name") or "Emby Server"
            version = result.get("Version") or "未知"
            messagebox.showinfo(APP_TITLE, f"连接成功。\n服务器：{server_name}\n版本：{version}")

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
