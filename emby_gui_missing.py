from __future__ import annotations

from typing import Any
from tkinter import messagebox, ttk

from emby_batch import has_actor
from emby_gui import APP_TITLE, export_missing_csv, media_directory


class MissingActorsTabMixin:
    def build_missing_tab(self) -> None:
        controls = self.top_controls(
            self.missing_tab,
            self.missing_lib_var,
            self.missing_scope_var,
        )
        ttk.Checkbutton(controls, text="同时扫描 Video", variable=self.include_video_var).pack(side="left", padx=3)
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
                scope_label = "全部媒体库" if library_id is None else str(library_id)
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
