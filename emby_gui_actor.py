from __future__ import annotations

import urllib.parse
from typing import Any
from tkinter import messagebox, ttk

from emby_gui import APP_TITLE, export_actor_csv, media_directory
from emby_gui_theme import RoundedButton


class ActorTabMixin:
    def build_actor_tab(self) -> None:
        toolbar_card = self.make_card(self.actor_tab)
        toolbar_card.pack(fill="x", pady=(0, 10))
        toolbar = ttk.Frame(toolbar_card, style="Card.TFrame", padding=(14, 12))
        toolbar.pack(fill="both", expand=True)

        ttk.Label(toolbar, text="处理范围", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.top_controls(
            toolbar,
            "delete_actor_images",
            self.actor_lib_var,
            self.actor_lib_name_var,
            self.actor_scope_var,
        )

        actions = ttk.Frame(toolbar, style="Card.TFrame")
        actions.pack(fill="x", pady=(4, 0))
        ttk.Label(
            actions,
            text="注意：Emby 的 Person 为全局共享对象，删除头像会影响其他媒体库中的同一演员。",
            style="Muted.TLabel",
        ).pack(side="left", fill="x", expand=True)

        b_clear = RoundedButton(
            actions,
            text="清空列表",
            variant="ghost",
            command=lambda: self.clear_tree(self.actor_tree),
        )
        b_clear.pack(side="right")
        b_csv = RoundedButton(actions, text="导出 CSV", variant="secondary", command=self.export_actor_rows)
        b_csv.pack(side="right", padx=(0, 6))
        b_exec = RoundedButton(actions, text="执行删除", variant="danger", command=self.execute_actor_images)
        b_exec.pack(side="right", padx=(0, 6))
        b_scan = RoundedButton(actions, text="扫描预览", variant="primary", command=self.scan_actor_images)
        b_scan.pack(side="right", padx=(0, 6))
        self.action_buttons.extend([b_scan, b_exec, b_csv, b_clear])

        result_card = self.make_card(self.actor_tab)
        result_card.pack(fill="both", expand=True)
        result = ttk.Frame(result_card, style="Card.TFrame", padding=(14, 12))
        result.pack(fill="both", expand=True)

        result_head = ttk.Frame(result, style="Card.TFrame")
        result_head.pack(fill="x", pady=(0, 8))
        ttk.Label(result_head, text="扫描结果", style="Section.TLabel").pack(side="left")
        ttk.Label(result_head, textvariable=self.actor_result_var, style="Muted.TLabel").pack(side="right")

        self.actor_tree = self.make_tree(
            result,
            [
                ("name", "演员", 180),
                ("id", "Person ID", 150),
                ("directory", "影片所在目录", 560),
                ("status", "状态", 140),
            ],
        )

    def scan_actor_images(self) -> None:
        try:
            client = self.client()
            libraries = self.scope_libraries(self.actor_scope_var.get(), self.actor_lib_var.get())
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> list[dict[str, Any]]:
            actor_directories: dict[str, set[str]] = {}

            # Build an actor -> movie-directory map from the selected libraries.
            for library_id in libraries:
                for movie in client.query_items(
                    library_id,
                    include_item_types="Movie,Video",
                    fields="People,Path",
                ):
                    directory = media_directory(movie.get("Path") or "")
                    for person in movie.get("People") or []:
                        if str(person.get("Type") or "").strip().lower() != "actor":
                            continue
                        person_id = str(person.get("Id") or "")
                        if person_id and directory:
                            actor_directories.setdefault(person_id, set()).add(directory)

            actors: dict[str, dict[str, Any]] = {}
            for library_id in libraries:
                for person in client.query_actors_with_primary_image(library_id):
                    person_id = str(person.get("Id") or "")
                    if person_id:
                        directories = sorted(actor_directories.get(person_id, set()), key=str.casefold)
                        actors[person_id] = {
                            "Id": person_id,
                            "Name": person.get("Name") or "未知演员",
                            "Directory": " | ".join(directories),
                            "Status": "待删除",
                        }
            return sorted(actors.values(), key=lambda x: str(x["Name"]).casefold())

        def done(rows: list[dict[str, Any]]) -> None:
            self.clear_tree(self.actor_tree)
            self.actor_rows = rows
            for row in rows:
                self.actor_tree.insert(
                    "",
                    "end",
                    iid=row["Id"],
                    values=(row["Name"], row["Id"], row["Directory"], row["Status"]),
                )
            self.refresh_result_counts()
            self.status_var.set(f"演员头像扫描完成：{len(rows)} 个")

        self.run_job("正在扫描演员头像及关联影片目录……", worker, done)

    def execute_actor_images(self) -> None:
        if not self.actor_rows:
            messagebox.showwarning(APP_TITLE, "请先点击“扫描预览”。")
            return
        if not messagebox.askyesno(
            APP_TITLE,
            f"确认删除列表中 {len(self.actor_rows)} 个演员的 Primary 头像？\n\n此操作会影响其他媒体库中共享的同一演员。",
            icon="warning",
        ):
            return
        rows = [dict(x) for x in self.actor_rows]
        try:
            client = self.client()
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> list[dict[str, Any]]:
            for row in rows:
                try:
                    client.delete(f"/Items/{urllib.parse.quote(row['Id'], safe='')}/Images/Primary")
                    row["Status"] = "已删除"
                except Exception as exc:
                    row["Status"] = f"失败：{exc}"
            return rows

        def done(result: list[dict[str, Any]]) -> None:
            self.actor_rows = result
            for row in result:
                if self.actor_tree.exists(row["Id"]):
                    self.actor_tree.item(
                        row["Id"],
                        values=(row["Name"], row["Id"], row["Directory"], row["Status"]),
                    )
            ok = sum(1 for x in result if x["Status"] == "已删除")
            self.refresh_result_counts()
            self.status_var.set(f"演员头像删除完成：成功 {ok}/{len(result)}")

        self.run_job("正在删除演员头像……", worker, done)

    def export_actor_rows(self) -> None:
        if not self.actor_rows:
            messagebox.showwarning(APP_TITLE, "当前列表为空，请先扫描。")
            return
        try:
            output = export_actor_csv(self.actor_rows)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"导出失败：\n{exc}")
            return
        self.status_var.set(f"CSV 已导出：{output}")
        messagebox.showinfo(APP_TITLE, f"CSV 已保存到：\n{output}")
