from __future__ import annotations

import urllib.parse
from typing import Any
from tkinter import messagebox, ttk

from emby_gui import APP_TITLE


class ActorTabMixin:
    def build_actor_tab(self) -> None:
        controls = self.top_controls(self.actor_tab, self.actor_lib_var)
        b_scan = ttk.Button(controls, text="扫描预览", command=self.scan_actor_images)
        b_scan.pack(side="left", padx=3)
        b_exec = ttk.Button(controls, text="执行删除", command=self.execute_actor_images)
        b_exec.pack(side="left", padx=3)
        b_clear = ttk.Button(controls, text="清空列表", command=lambda: self.clear_tree(self.actor_tree))
        b_clear.pack(side="left", padx=3)
        self.action_buttons.extend([b_scan, b_exec, b_clear])

        ttk.Label(
            self.actor_tab,
            text="注意：Emby 演员 Person 是全局共享对象；删除头像后，同一演员在其他媒体库中的头像也会消失。",
        ).pack(fill="x", pady=(0, 6))

        self.actor_tree = self.make_tree(
            self.actor_tab,
            [("name", "演员", 260), ("id", "Person ID", 220), ("status", "状态", 240)],
        )

    def scan_actor_images(self) -> None:
        try:
            client = self.client()
            libraries = self.libraries(self.actor_lib_var.get())
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> list[dict[str, Any]]:
            actors: dict[str, dict[str, Any]] = {}
            for library_id in libraries:
                for person in client.query_actors_with_primary_image(library_id):
                    person_id = str(person.get("Id") or "")
                    if person_id:
                        actors[person_id] = {
                            "Id": person_id,
                            "Name": person.get("Name") or "未知演员",
                            "Status": "待删除",
                        }
            return sorted(actors.values(), key=lambda x: str(x["Name"]).casefold())

        def done(rows: list[dict[str, Any]]) -> None:
            self.clear_tree(self.actor_tree)
            self.actor_rows = rows
            for row in rows:
                self.actor_tree.insert("", "end", iid=row["Id"], values=(row["Name"], row["Id"], row["Status"]))
            self.status_var.set(f"演员头像扫描完成：{len(rows)} 个")

        self.run_job("正在扫描演员头像……", worker, done)

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
                    self.actor_tree.item(row["Id"], values=(row["Name"], row["Id"], row["Status"]))
            ok = sum(1 for x in result if x["Status"] == "已删除")
            self.status_var.set(f"演员头像删除完成：成功 {ok}/{len(result)}")

        self.run_job("正在删除演员头像……", worker, done)
