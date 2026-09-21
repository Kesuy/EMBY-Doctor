from __future__ import annotations

import os
import subprocess
import sys
from typing import Any
import tkinter as tk
from tkinter import messagebox, ttk

from emby_batch import has_actor
from emby_gui import APP_TITLE, complete_directory_path, export_missing_csv, media_directory


class MissingActorsTabMixin:
    def build_missing_tab(self) -> None:
        controls = self.top_controls(
            self.missing_tab,
            "scan_missing_actors",
            self.missing_lib_var,
            self.missing_lib_name_var,
            self.missing_scope_var,
        )
        ttk.Checkbutton(controls, text="同时扫描普通视频（Video）", variable=self.include_video_var).pack(side="left", padx=3)
        b_scan = ttk.Button(controls, text="开始扫描", command=self.scan_missing_actors)
        b_scan.pack(side="left", padx=3)
        b_csv = ttk.Button(controls, text="导出 CSV", command=self.export_missing)
        b_csv.pack(side="left", padx=3)
        b_clear = ttk.Button(controls, text="清空列表", command=lambda: self.clear_tree(self.missing_tree))
        b_clear.pack(side="left", padx=3)
        self.action_buttons.extend([b_scan, b_csv, b_clear])

        self.missing_tree = self.make_tree(
            self.missing_tab,
            [
                ("name", "影片", 180),
                ("id", "Item ID", 120),
                ("library", "扫描范围", 110),
                ("path", "文件路径", 330),
                ("directory", "影片所在目录", 330),
            ],
        )
        self.missing_context_iid = ""
        self.missing_context_menu = tk.Menu(self.missing_tree, tearoff=False)
        self.missing_context_menu.add_command(label="复制影片名", command=self.copy_missing_names)
        self.missing_context_menu.add_command(label="刷新元数据", command=self.refresh_missing_metadata)
        self.missing_context_menu.add_separator()
        self.missing_context_menu.add_command(label="打开所在目录", command=self.open_missing_directory)
        self.missing_tree.bind("<Button-3>", self.show_missing_context_menu)

    def show_missing_context_menu(self, event: tk.Event) -> None:
        iid = self.missing_tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.missing_tree.selection():
            self.missing_tree.selection_set(iid)
        self.missing_tree.focus(iid)
        self.missing_context_iid = iid
        try:
            self.missing_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.missing_context_menu.grab_release()

    def selected_missing_rows(self) -> list[dict[str, Any]]:
        selected = set(self.missing_tree.selection())
        if not selected and self.missing_context_iid:
            selected = {self.missing_context_iid}
        return [row for row in self.missing_rows if row.get("_TreeId") in selected]

    def copy_missing_names(self) -> None:
        rows = self.selected_missing_rows()
        if not rows:
            messagebox.showwarning(APP_TITLE, "请先选择至少一部影片。")
            return
        names = "\n".join(str(row.get("Name") or "") for row in rows)
        self.root.clipboard_clear()
        self.root.clipboard_append(names)
        self.status_var.set(f"已复制 {len(rows)} 个影片名")

    def refresh_missing_metadata(self) -> None:
        rows = self.selected_missing_rows()
        if not rows:
            messagebox.showwarning(APP_TITLE, "请先选择至少一部影片。")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            f"确认刷新选中的 {len(rows)} 部影片元数据？\n\n"
            "将使用 Emby 完整元数据刷新并替换现有元数据，不替换已有图片。",
            icon="warning",
        ):
            return
        try:
            client = self.client()
        except Exception as exc:
            self.job_error(exc)
            return
        targets = [dict(row) for row in rows]

        def worker() -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            for row in targets:
                item = dict(row)
                try:
                    client.refresh_metadata(str(row.get("Id") or ""))
                    item["RefreshError"] = ""
                except Exception as exc:
                    item["RefreshError"] = str(exc)
                result.append(item)
            return result

        def done(result: list[dict[str, Any]]) -> None:
            failed = [row for row in result if row.get("RefreshError")]
            ok = len(result) - len(failed)
            self.status_var.set(f"元数据刷新已提交：成功 {ok}/{len(result)}")
            if failed:
                detail = "\n".join(
                    f"{row.get('Name') or row.get('Id')}: {row.get('RefreshError')}"
                    for row in failed[:8]
                )
                if len(failed) > 8:
                    detail += f"\n……另有 {len(failed) - 8} 项失败"
                messagebox.showwarning(APP_TITLE, f"部分刷新请求失败：\n{detail}")

        self.run_job("正在提交元数据刷新……", worker, done)

    def open_missing_directory(self) -> None:
        row = None
        if self.missing_context_iid:
            row = next(
                (x for x in self.missing_rows if x.get("_TreeId") == self.missing_context_iid),
                None,
            )
        if row is None:
            rows = self.selected_missing_rows()
            row = rows[0] if rows else None
        if row is None:
            messagebox.showwarning(APP_TITLE, "请先选择一部影片。")
            return

        directory = complete_directory_path(
            str(row.get("Directory") or ""),
            self.directory_prefix_var.get(),
        )
        if not directory:
            messagebox.showwarning(APP_TITLE, "该影片没有可用的目录路径。")
            return
        try:
            if sys.platform == "win32":
                os.startfile(directory)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", directory])
            else:
                subprocess.Popen(["xdg-open", directory])
        except Exception as exc:
            messagebox.showerror(
                APP_TITLE,
                f"无法打开目录：\n{directory}\n\n{exc}\n\n"
                "如果 Emby 返回的是服务器本地路径，请在通用设置中填写“打开目录路径前缀”。",
            )

    def scan_missing_actors(self) -> None:
        try:
            client = self.client()
            libraries = self.scope_libraries(self.missing_scope_var.get(), self.missing_lib_var.get())
            item_types = "Movie,Video" if self.include_video_var.get() else "Movie"
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> list[dict[str, Any]]:
            missing: list[dict[str, Any]] = []
            for library_id in libraries:
                scope_label = (
                    "全部媒体库"
                    if library_id is None
                    else self.library_display_name("scan_missing_actors", str(library_id))
                )
                for movie in client.query_items(
                    library_id,
                    include_item_types=item_types,
                    fields="People,Path,ProviderIds",
                ):
                    if not has_actor(movie):
                        path = movie.get("Path") or ""
                        missing.append(
                            {
                                "LibraryId": scope_label,
                                "Id": str(movie.get("Id") or ""),
                                "Name": movie.get("Name") or "",
                                "Path": path,
                                "Directory": media_directory(path),
                                "ProviderIds": movie.get("ProviderIds") or {},
                            }
                        )
            return missing

        def done(rows: list[dict[str, Any]]) -> None:
            self.clear_tree(self.missing_tree)
            self.missing_rows = rows
            for i, row in enumerate(rows):
                iid = f"{row['LibraryId']}:{row['Id']}:{i}"
                row["_TreeId"] = iid
                self.missing_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        row["Name"],
                        row["Id"],
                        row["LibraryId"],
                        row["Path"],
                        row["Directory"],
                    ),
                )
            self.status_var.set(f"无演员影片扫描完成：{len(rows)} 部")

        self.run_job("正在扫描无演员影片……", worker, done)

    def export_missing(self) -> None:
        if not self.missing_rows:
            messagebox.showwarning(APP_TITLE, "当前列表为空，请先扫描。")
            return
        try:
            output = export_missing_csv(self.missing_rows)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：\n{exc}")
            return
        self.status_var.set(f"CSV 已导出：{output}")
        messagebox.showinfo(APP_TITLE, f"CSV 已保存到：\n{output}")
