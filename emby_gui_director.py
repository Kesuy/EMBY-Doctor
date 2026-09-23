from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any
from tkinter import messagebox, ttk

from emby_batch import people_of_type, remove_directors
from emby_gui import APP_TITLE, export_director_csv, media_directory, save_director_backup
from emby_gui_theme import RoundedButton


class DirectorTabMixin:
    def build_director_tab(self) -> None:
        toolbar_card = self.make_card(self.director_tab)
        toolbar_card.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(toolbar_card, style="Card.TFrame", padding=(14, 12))
        toolbar.pack(fill="both", expand=True)

        ttk.Label(toolbar, text="处理范围", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.top_controls(
            toolbar,
            "delete_directors",
            self.director_lib_var,
            self.director_lib_name_var,
            self.director_scope_var,
        )

        actions = ttk.Frame(toolbar, style="Card.TFrame")
        actions.pack(fill="x", pady=(4, 0))
        ttk.Label(
            actions,
            text="执行前会自动备份完整影片元数据；若 NFO 仍含 <director>，后续刷新可能重新导入。",
            style="Muted.TLabel",
        ).pack(side="left", fill="x", expand=True)

        b_clear = RoundedButton(
            actions,
            text="清空列表",
            variant="ghost",
            command=lambda: self.clear_tree(self.director_tree),
        )
        b_clear.pack(side="right")
        b_csv = RoundedButton(actions, text="导出 CSV", variant="secondary", command=self.export_directors)
        b_csv.pack(side="right", padx=(0, 6))
        b_exec = RoundedButton(actions, text="执行删除", variant="danger", command=self.execute_directors)
        b_exec.pack(side="right", padx=(0, 6))
        b_scan = RoundedButton(actions, text="扫描预览", variant="primary", command=self.scan_directors)
        b_scan.pack(side="right", padx=(0, 6))
        self.action_buttons.extend([b_scan, b_exec, b_csv, b_clear])

        result_card = self.make_card(self.director_tab)
        result_card.pack(fill="both", expand=True)
        result = ttk.Frame(result_card, style="Card.TFrame", padding=(14, 12))
        result.pack(fill="both", expand=True)

        result_head = ttk.Frame(result, style="Card.TFrame")
        result_head.pack(fill="x", pady=(0, 8))
        ttk.Label(result_head, text="导演信息列表", style="Section.TLabel").pack(side="left")
        ttk.Label(result_head, textvariable=self.director_result_var, style="Muted.TLabel").pack(side="right")

        self.director_tree = self.make_tree(
            result,
            [
                ("name", "影片", 180),
                ("id", "Item ID", 110),
                ("directors", "导演", 180),
                ("path", "文件路径", 310),
                ("directory", "影片所在目录", 310),
                ("status", "状态", 110),
            ],
        )

    def scan_directors(self) -> None:
        try:
            client = self.client()
            libraries = self.scope_libraries(self.director_scope_var.get(), self.director_lib_var.get())
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> list[dict[str, Any]]:
            candidates: dict[str, dict[str, Any]] = {}
            for library_id in libraries:
                for movie in client.query_items(
                    library_id,
                    include_item_types="Movie",
                    fields="People,Path",
                ):
                    directors = people_of_type(movie, "Director")
                    if not directors:
                        continue
                    item_id = str(movie.get("Id") or "")
                    path = movie.get("Path") or ""
                    if item_id:
                        candidates[item_id] = {
                            "Id": item_id,
                            "Name": movie.get("Name") or item_id,
                            "Path": path,
                            "Directory": media_directory(path),
                            "Directors": [str(p.get("Name") or "") for p in directors],
                            "Status": "待删除",
                        }
            return sorted(candidates.values(), key=lambda x: str(x["Name"]).casefold())

        def done(rows: list[dict[str, Any]]) -> None:
            self.clear_tree(self.director_tree)
            self.director_rows = rows
            for row in rows:
                self.director_tree.insert(
                    "",
                    "end",
                    iid=row["Id"],
                    values=(
                        row["Name"],
                        row["Id"],
                        ", ".join(row["Directors"]),
                        row["Path"],
                        row["Directory"],
                        row["Status"],
                    ),
                )
            self.refresh_result_counts()
            self.status_var.set(f"导演信息扫描完成：{len(rows)} 部影片")

        self.run_job("正在扫描导演信息……", worker, done)

    def execute_directors(self) -> None:
        if not self.director_rows:
            messagebox.showwarning(APP_TITLE, "请先点击“扫描预览”。")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            f"确认删除列表中 {len(self.director_rows)} 部影片的 Director 信息？\n\n执行前会自动备份完整元数据。",
            icon="warning",
        ):
            return
        rows = [dict(x) for x in self.director_rows]
        try:
            client = self.client()
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> tuple[list[dict[str, Any]], Path | None]:
            user_id, _ = client.get_admin_user_id()
            fetched: list[tuple[dict[str, Any], dict[str, Any]]] = []
            backups: list[dict[str, Any]] = []

            for row in rows:
                try:
                    item = client.get_full_item(user_id, row["Id"])
                    if not people_of_type(item, "Director"):
                        row["Status"] = "已无导演"
                        continue
                    backups.append(item)
                    fetched.append((row, item))
                except Exception as exc:
                    row["Status"] = f"读取失败：{exc}"

            backup_path = save_director_backup(backups) if backups else None
            for row, item in fetched:
                try:
                    client.post_json(
                        f"/Items/{urllib.parse.quote(row['Id'], safe='')}",
                        remove_directors(item),
                    )
                    row["Status"] = "已删除"
                except Exception as exc:
                    row["Status"] = f"失败：{exc}"
            return rows, backup_path

        def done(result: tuple[list[dict[str, Any]], Path | None]) -> None:
            rows_result, backup_path = result
            self.director_rows = rows_result
            for row in rows_result:
                if self.director_tree.exists(row["Id"]):
                    self.director_tree.item(
                        row["Id"],
                        values=(
                            row["Name"],
                            row["Id"],
                            ", ".join(row["Directors"]),
                            row["Path"],
                            row["Directory"],
                            row["Status"],
                        ),
                    )
            ok = sum(1 for x in rows_result if x["Status"] == "已删除")
            msg = f"导演信息删除完成：成功 {ok}/{len(rows_result)}"
            if backup_path:
                msg += f"；备份：{backup_path}"
            self.refresh_result_counts()
            self.status_var.set(msg)
            if backup_path:
                messagebox.showinfo(APP_TITLE, f"处理完成。\n\n备份文件：\n{backup_path}")

        self.run_job("正在备份并删除导演信息……", worker, done)

    def export_directors(self) -> None:
        if not self.director_rows:
            messagebox.showwarning(APP_TITLE, "当前列表为空，请先扫描。")
            return
        try:
            output = export_director_csv(self.director_rows)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：\n{exc}")
            return
        self.status_var.set(f"CSV 已导出：{output}")
        messagebox.showinfo(APP_TITLE, f"CSV 已保存到：\n{output}")
