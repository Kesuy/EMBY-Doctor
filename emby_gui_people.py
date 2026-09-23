from __future__ import annotations

import base64
import threading
import urllib.parse
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

from emby_gui import APP_TITLE
from emby_gui_theme import (
    BG,
    BORDER,
    CARD,
    DANGER,
    DANGER_SOFT,
    MUTED,
    PRIMARY,
    PRIMARY_SOFT,
    SUCCESS,
    SUCCESS_SOFT,
    TEXT,
    WARNING,
    WARNING_SOFT,
    AutoHideScrollbar,
)
from emby_people import (
    build_duplicate_candidates,
    person_completeness,
    person_provider_ids,
    replace_person_reference,
)


class PeopleQualityTabMixin:
    def build_people_quality_tab(self) -> None:
        self.person_candidates: list[dict[str, Any]] = []
        self.person_catalog: dict[str, dict[str, Any]] = {}
        self.person_associations: dict[str, list[dict[str, Any]]] = {}
        self.people_candidate_by_iid: dict[str, dict[str, Any]] = {}
        self.people_selected_candidate: dict[str, Any] | None = None
        self.people_photo_refs: dict[str, tk.PhotoImage] = {}
        self.people_image_generation = 0
        self.duplicate_count_var = tk.StringVar(value="候选 0 组")
        self.avatar_count_var = tk.StringVar(value="待处理 0 人")
        self.conflict_count_var = tk.StringVar(value="冲突 0 组")
        self.people_migration_hint_var = tk.StringVar(value="请选择候选人物进行比较。")
        self.people_exact_name_only_var = tk.BooleanVar(value=False)
        self.people_subpage = "duplicate"
        self.people_subnav_buttons: dict[str, tk.Button] = {}
        self.people_subframes: dict[str, tk.Frame] = {}

        intro = self.make_card(self.people_tab)
        intro.pack(fill="x", pady=(0, 10))
        intro_inner = tk.Frame(intro, background=CARD, bd=0)
        intro_inner.pack(fill="x", padx=16, pady=13)

        title_box = tk.Frame(intro_inner, background=CARD, bd=0)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="重复人物与质检",
            background=CARD,
            foreground=TEXT,
            font=("Microsoft YaHei UI", 15, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            title_box,
            text="集中处理重复 Person、头像缺失和资料冲突。重复人物采用“迁移关联”方式治理，不自动删除 Person 实体。",
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        tk.Label(
            intro_inner,
            text="安全迁移 · 不删除实体",
            background=SUCCESS_SOFT,
            foreground=SUCCESS,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=5,
        ).pack(side="right")

        scope_card = self.make_card(self.people_tab)
        scope_card.pack(fill="x", pady=(0, 10))
        scope_inner = tk.Frame(scope_card, background=CARD, bd=0)
        scope_inner.pack(fill="x", padx=14, pady=10)
        self.top_controls(
            scope_inner,
            "people_quality",
            self.people_lib_var,
            self.people_lib_name_var,
            self.people_scope_var,
        )

        tabs = self.make_card(self.people_tab)
        tabs.pack(fill="x", pady=(0, 10))
        tab_row = tk.Frame(tabs, background=CARD, bd=0)
        tab_row.pack(fill="x", padx=10, pady=(6, 0))
        self._people_subnav_button(tab_row, "duplicate", "重复人物")
        self._people_subnav_button(tab_row, "avatar", "头像质量")
        self._people_subnav_button(tab_row, "conflict", "资料冲突")

        host = tk.Frame(self.people_tab, background=BG, bd=0)
        host.pack(fill="both", expand=True)
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)

        duplicate_frame = tk.Frame(host, background=BG, bd=0)
        avatar_frame = tk.Frame(host, background=BG, bd=0)
        conflict_frame = tk.Frame(host, background=BG, bd=0)
        self.people_subframes = {
            "duplicate": duplicate_frame,
            "avatar": avatar_frame,
            "conflict": conflict_frame,
        }
        for frame in self.people_subframes.values():
            frame.grid(row=0, column=0, sticky="nsew")

        self._build_duplicate_people_view(duplicate_frame)
        self._build_avatar_quality_view(avatar_frame)
        self._build_profile_conflict_view(conflict_frame)
        self.show_people_subpage("duplicate")

    def _people_subnav_button(self, parent: tk.Widget, key: str, text: str) -> None:
        button = tk.Button(
            parent,
            text=text,
            command=lambda current=key: self.show_people_subpage(current),
            relief="flat",
            bd=0,
            highlightthickness=0,
            background=CARD,
            foreground=MUTED,
            activebackground=CARD,
            activeforeground=PRIMARY,
            padx=10,
            pady=8,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10),
        )
        button.pack(side="left", padx=(0, 8))
        self.people_subnav_buttons[key] = button

    def show_people_subpage(self, key: str) -> None:
        frame = self.people_subframes.get(key)
        if frame is None:
            return
        self.people_subpage = key
        frame.tkraise()
        for nav_key, button in self.people_subnav_buttons.items():
            active = nav_key == key
            button.configure(
                foreground=PRIMARY if active else MUTED,
                font=("Microsoft YaHei UI", 10, "bold" if active else "normal"),
            )

    def _build_duplicate_people_view(self, parent: tk.Widget) -> None:
        action_card = self.make_card(parent)
        action_card.pack(fill="x", pady=(0, 10))
        action = tk.Frame(action_card, background=CARD, bd=0)
        action.pack(fill="x", padx=14, pady=11)

        b_scan = ttk.Button(
            action,
            text="扫描重复人物",
            style="Primary.TButton",
            command=lambda: self.scan_people_audit("duplicate"),
        )
        b_scan.pack(side="left")
        self.action_buttons.append(b_scan)

        tk.Label(
            action,
            text="按 Provider ID、姓名与人物资料完整度识别高置信重复 Person，选中候选后在右侧比较。",
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(12, 12))
        ttk.Checkbutton(
            action,
            text="仅名称完全相同",
            style="Card.TCheckbutton",
            variable=self.people_exact_name_only_var,
            command=self.populate_people_audit_views,
        ).pack(side="left")
        tk.Label(
            action,
            textvariable=self.duplicate_count_var,
            background="#F5F7FA",
            foreground=PRIMARY,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=5,
        ).pack(side="right")

        body = tk.Frame(parent, background=BG, bd=0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=8)
        body.grid_rowconfigure(0, weight=1)

        left_card = self.make_card(body)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left = tk.Frame(left_card, background=CARD, bd=0)
        left.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(
            left,
            text="重复候选",
            background=CARD,
            foreground=PRIMARY,
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            left,
            text="按置信度排序；单击一组在右侧比较。",
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x", pady=(2, 8))

        tree_wrap = tk.Frame(left, background=CARD, bd=0)
        tree_wrap.pack(fill="both", expand=True)
        self.duplicate_tree = ttk.Treeview(
            tree_wrap,
            columns=("score", "pair"),
            show="headings",
            selectmode="browse",
            style="Modern.Treeview",
        )
        self.duplicate_tree.heading("score", text="置信度")
        self.duplicate_tree.heading("pair", text="人物")
        self.duplicate_tree.column("score", width=70, minwidth=64, anchor="center", stretch=False)
        self.duplicate_tree.column("pair", width=260, minwidth=180, anchor="w")
        y = AutoHideScrollbar(
            tree_wrap,
            orient="vertical",
            command=self.duplicate_tree.yview,
            style="Modern.Vertical.TScrollbar",
        )
        self.duplicate_tree.configure(yscrollcommand=y.set)
        self.duplicate_tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)
        self.duplicate_tree.bind("<<TreeviewSelect>>", self.on_duplicate_select)

        right_card = self.make_card(body)
        right_card.grid(row=0, column=1, sticky="nsew")
        self.duplicate_detail = tk.Frame(right_card, background=CARD, bd=0)
        self.duplicate_detail.pack(fill="both", expand=True, padx=12, pady=10)

        detail_header = tk.Frame(self.duplicate_detail, background=CARD, bd=0)
        detail_header.pack(fill="x", pady=(0, 8))
        self.duplicate_title_var = tk.StringVar(value="请选择重复候选")
        self.duplicate_reason_var = tk.StringVar(value="")
        tk.Label(
            detail_header,
            textvariable=self.duplicate_title_var,
            background=CARD,
            foreground=PRIMARY,
            font=("Microsoft YaHei UI", 12, "bold"),
            anchor="w",
        ).pack(side="left")
        tk.Label(
            detail_header,
            textvariable=self.duplicate_reason_var,
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(8, 0))

        self.duplicate_confidence_var = tk.StringVar(value="置信度 —")
        tk.Label(
            detail_header,
            textvariable=self.duplicate_confidence_var,
            background=WARNING_SOFT,
            foreground=WARNING,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=9,
            pady=4,
        ).pack(side="right", padx=(8, 0))
        self.swap_keep_button = ttk.Button(
            detail_header,
            text="交换保留方向",
            style="Secondary.TButton",
            command=self.swap_duplicate_direction,
        )
        self.swap_keep_button.pack(side="right")

        compare = tk.Frame(self.duplicate_detail, background=CARD, bd=0)
        compare.pack(fill="both", expand=True)
        compare.grid_columnconfigure(0, weight=1)
        compare.grid_columnconfigure(1, weight=1)
        compare.grid_rowconfigure(0, weight=1)

        self.keep_panel = tk.Frame(
            compare,
            background="#F6FAFF",
            highlightbackground="#CFE2FF",
            highlightthickness=1,
            bd=0,
        )
        self.keep_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.duplicate_panel = tk.Frame(
            compare,
            background="#FFF8F8",
            highlightbackground="#F4D2D2",
            highlightthickness=1,
            bd=0,
        )
        self.duplicate_panel.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        self.keep_name_var = tk.StringVar(value="—")
        self.keep_id_var = tk.StringVar(value="Person ID: —")
        self.keep_assoc_var = tk.StringVar(value="关联影片：—")
        self.keep_score_var = tk.StringVar(value="资料完整度：—")
        self.keep_provider_var = tk.StringVar(value="—")
        self.dup_name_var = tk.StringVar(value="—")
        self.dup_id_var = tk.StringVar(value="Person ID: —")
        self.dup_assoc_var = tk.StringVar(value="关联影片：—")
        self.dup_score_var = tk.StringVar(value="资料完整度：—")
        self.dup_provider_var = tk.StringVar(value="—")

        self.keep_image_label = self._build_person_compare_panel(
            self.keep_panel,
            "建议保留",
            PRIMARY,
            PRIMARY_SOFT,
            self.keep_name_var,
            self.keep_id_var,
            self.keep_assoc_var,
            self.keep_score_var,
            self.keep_provider_var,
        )
        self.dup_image_label = self._build_person_compare_panel(
            self.duplicate_panel,
            "重复人物",
            DANGER,
            DANGER_SOFT,
            self.dup_name_var,
            self.dup_id_var,
            self.dup_assoc_var,
            self.dup_score_var,
            self.dup_provider_var,
        )

        footer = tk.Frame(self.duplicate_detail, background=CARD, bd=0)
        footer.pack(fill="x", pady=(10, 0))
        tk.Label(
            footer,
            textvariable=self.people_migration_hint_var,
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
            justify="left",
        ).pack(side="left", fill="x", expand=True)

        self.migrate_button = ttk.Button(
            footer,
            text="迁移右侧关联 → 保留左侧人物",
            style="Primary.TButton",
            command=self.migrate_selected_duplicate,
        )
        self.migrate_button.pack(side="right")

    def _build_person_compare_panel(
        self,
        panel: tk.Frame,
        badge_text: str,
        badge_fg: str,
        badge_bg: str,
        name_var: tk.StringVar,
        id_var: tk.StringVar,
        assoc_var: tk.StringVar,
        score_var: tk.StringVar,
        provider_var: tk.StringVar,
    ) -> tk.Label:
        top = tk.Frame(panel, background=panel.cget("background"), bd=0)
        top.pack(fill="x", padx=12, pady=(12, 8))

        image_label = tk.Label(
            top,
            text="无头像",
            width=14,
            height=7,
            background="#EAF0F7",
            foreground="#95A2B3",
            font=("Microsoft YaHei UI", 10),
            bd=0,
        )
        image_label.pack(side="left", padx=(0, 12))

        info = tk.Frame(top, background=panel.cget("background"), bd=0)
        info.pack(side="left", fill="both", expand=True)
        tk.Label(
            info,
            text=badge_text,
            background=badge_bg,
            foreground=badge_fg,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=7,
            pady=3,
        ).pack(anchor="w")
        tk.Label(
            info,
            textvariable=name_var,
            background=panel.cget("background"),
            foreground=PRIMARY,
            font=("Microsoft YaHei UI", 12, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(6, 1))
        tk.Label(
            info,
            textvariable=id_var,
            background=panel.cget("background"),
            foreground=TEXT,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            info,
            textvariable=assoc_var,
            background=panel.cget("background"),
            foreground=TEXT,
            font=("Microsoft YaHei UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(3, 0))
        tk.Label(
            info,
            textvariable=score_var,
            background=panel.cget("background"),
            foreground=MUTED,
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).pack(fill="x", pady=(3, 0))

        provider_box = tk.Frame(
            panel,
            background="#F7F9FC",
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        provider_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        tk.Label(
            provider_box,
            text="Provider IDs",
            background="#F7F9FC",
            foreground=MUTED,
            font=("Microsoft YaHei UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=9, pady=(8, 3))
        tk.Label(
            provider_box,
            textvariable=provider_var,
            background="#F7F9FC",
            foreground=PRIMARY,
            font=("Consolas", 9),
            anchor="nw",
            justify="left",
            wraplength=360,
        ).pack(fill="both", expand=True, padx=9, pady=(0, 8))

        return image_label

    def _build_avatar_quality_view(self, parent: tk.Widget) -> None:
        card = self.make_card(parent)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, background=CARD, bd=0)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        head = tk.Frame(inner, background=CARD, bd=0)
        head.pack(fill="x", pady=(0, 9))
        b_scan = ttk.Button(
            head,
            text="扫描头像质量",
            style="Primary.TButton",
            command=lambda: self.scan_people_audit("avatar"),
        )
        b_scan.pack(side="left")
        self.action_buttons.append(b_scan)
        tk.Label(
            head,
            text="当前质检聚焦缺失 Primary 头像的人物，按关联影片数量优先显示。",
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(12, 0))
        tk.Label(
            head,
            textvariable=self.avatar_count_var,
            background="#F5F7FA",
            foreground=WARNING,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=5,
        ).pack(side="right")

        self.avatar_tree = self.make_tree(
            inner,
            [
                ("name", "人物", 200),
                ("id", "Person ID", 140),
                ("assoc", "关联影片", 100),
                ("providers", "Provider IDs", 110),
                ("status", "状态", 120),
            ],
        )

    def _build_profile_conflict_view(self, parent: tk.Widget) -> None:
        card = self.make_card(parent)
        card.pack(fill="both", expand=True)
        inner = tk.Frame(card, background=CARD, bd=0)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        head = tk.Frame(inner, background=CARD, bd=0)
        head.pack(fill="x", pady=(0, 9))
        b_scan = ttk.Button(
            head,
            text="扫描资料冲突",
            style="Primary.TButton",
            command=lambda: self.scan_people_audit("conflict"),
        )
        b_scan.pack(side="left")
        self.action_buttons.append(b_scan)
        tk.Label(
            head,
            text="检查重复候选中同一 Provider 出现不同 ID 的情况，避免误合并。",
            background=CARD,
            foreground=MUTED,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=(12, 0))
        tk.Label(
            head,
            textvariable=self.conflict_count_var,
            background="#F5F7FA",
            foreground=DANGER,
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=10,
            pady=5,
        ).pack(side="right")

        self.conflict_tree = self.make_tree(
            inner,
            [
                ("pair", "人物候选", 340),
                ("providers", "冲突 Provider", 260),
                ("confidence", "置信度", 100),
                ("reason", "识别依据", 180),
            ],
        )

    def scan_people_audit(self, target: str = "duplicate") -> None:
        try:
            client = self.client()
        except Exception as exc:
            self.job_error(exc)
            return

        labels = {
            "duplicate": "正在扫描重复人物……",
            "avatar": "正在扫描人物头像……",
            "conflict": "正在扫描人物资料冲突……",
        }

        def worker() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
            library_ids = self.scope_libraries(
                self.people_scope_var.get(),
                self.people_lib_var.get(),
            )

            person_map: dict[str, dict[str, Any]] = {}
            associations: dict[str, list[dict[str, Any]]] = {}

            for library_id in library_ids:
                for person in client.query_people(library_id):
                    person_id = str(person.get("Id") or "").strip()
                    if person_id and person_id not in person_map:
                        person_map[person_id] = person

                for movie in client.query_items(
                    library_id,
                    include_item_types="Movie,Video",
                    fields="People,Path",
                ):
                    movie_id = str(movie.get("Id") or "")
                    if not movie_id:
                        continue
                    entry = {
                        "Id": movie_id,
                        "Name": str(movie.get("Name") or movie_id),
                        "Path": str(movie.get("Path") or ""),
                        "LibraryId": str(library_id or ""),
                    }
                    for person in movie.get("People") or []:
                        person_id = str(person.get("Id") or "").strip()
                        if person_id:
                            bucket = associations.setdefault(person_id, [])
                            if not any(item["Id"] == movie_id for item in bucket):
                                bucket.append(entry)

            persons = list(person_map.values())
            counts = {person_id: len(items) for person_id, items in associations.items()}
            candidates = build_duplicate_candidates(persons, counts)
            return persons, associations, candidates

        def done(
            result: tuple[
                list[dict[str, Any]],
                dict[str, list[dict[str, Any]]],
                list[dict[str, Any]],
            ]
        ) -> None:
            persons, associations, candidates = result
            self.person_catalog = {
                str(person.get("Id") or ""): person
                for person in persons
                if str(person.get("Id") or "")
            }
            self.person_associations = associations
            self.person_candidates = candidates
            self.populate_people_audit_views()
            self.show_people_subpage(target)
            self.status_var.set(
                f"人物质检扫描完成：Person {len(persons)} 个，重复候选 {len(candidates)} 组"
            )

        self.run_job(labels.get(target, labels["duplicate"]), worker, done)

    def populate_people_audit_views(self) -> None:
        for item in self.duplicate_tree.get_children():
            self.duplicate_tree.delete(item)
        self.people_candidate_by_iid.clear()

        visible_candidates = list(self.person_candidates)
        if self.people_exact_name_only_var.get():
            visible_candidates = [
                candidate
                for candidate in visible_candidates
                if str(candidate["Left"].get("Name") or "").strip()
                == str(candidate["Right"].get("Name") or "").strip()
            ]

        for index, candidate in enumerate(visible_candidates):
            iid = f"dup-{index}"
            left = candidate["Left"]
            right = candidate["Right"]
            pair = f"{left.get('Name') or '未知'}  ←  {right.get('Name') or '未知'}"
            self.duplicate_tree.insert(
                "",
                "end",
                iid=iid,
                values=(f"{candidate['Confidence']}分", pair),
            )
            self.people_candidate_by_iid[iid] = candidate

        if self.people_exact_name_only_var.get():
            self.duplicate_count_var.set(
                f"候选 {len(visible_candidates)} / {len(self.person_candidates)} 组"
            )
        else:
            self.duplicate_count_var.set(f"候选 {len(self.person_candidates)} 组")

        for item in self.avatar_tree.get_children():
            self.avatar_tree.delete(item)
        avatar_rows: list[tuple[int, dict[str, Any]]] = []
        for person_id, person in self.person_catalog.items():
            has_image = bool(
                person.get("PrimaryImageTag")
                or (person.get("ImageTags") or {}).get("Primary")
            )
            if has_image:
                continue
            avatar_rows.append((len(self.person_associations.get(person_id, [])), person))
        avatar_rows.sort(key=lambda value: (-value[0], str(value[1].get("Name") or "").casefold()))
        for index, (assoc_count, person) in enumerate(avatar_rows):
            providers = person_provider_ids(person)
            self.avatar_tree.insert(
                "",
                "end",
                iid=f"avatar-{index}",
                values=(
                    person.get("Name") or "未知人物",
                    person.get("Id") or "",
                    assoc_count,
                    len(providers),
                    "缺少头像",
                ),
            )
        self.avatar_count_var.set(f"待处理 {len(avatar_rows)} 人")

        for item in self.conflict_tree.get_children():
            self.conflict_tree.delete(item)
        conflicts = [candidate for candidate in self.person_candidates if candidate.get("Conflicts")]
        for index, candidate in enumerate(conflicts):
            left = candidate["Left"]
            right = candidate["Right"]
            self.conflict_tree.insert(
                "",
                "end",
                iid=f"conflict-{index}",
                values=(
                    f"{left.get('Name') or '未知'}  ↔  {right.get('Name') or '未知'}",
                    "、".join(candidate.get("Conflicts") or []),
                    f"{candidate['Confidence']}分",
                    candidate.get("Reason") or "",
                ),
            )
        self.conflict_count_var.set(f"冲突 {len(conflicts)} 组")

        visible_rows = self.duplicate_tree.get_children()
        if visible_rows:
            first = visible_rows[0]
            self.duplicate_tree.selection_set(first)
            self.duplicate_tree.focus(first)
            self.render_duplicate_candidate(self.people_candidate_by_iid[first])
        else:
            self.people_selected_candidate = None
            self.render_empty_duplicate_detail()

    def on_duplicate_select(self, _event: tk.Event | None = None) -> None:
        selected = self.duplicate_tree.selection()
        if not selected:
            return
        candidate = self.people_candidate_by_iid.get(selected[0])
        if candidate:
            self.render_duplicate_candidate(candidate)

    def render_empty_duplicate_detail(self) -> None:
        self.duplicate_title_var.set("未发现重复候选")
        self.duplicate_reason_var.set("")
        self.duplicate_confidence_var.set("置信度 —")
        self.keep_name_var.set("—")
        self.keep_id_var.set("Person ID: —")
        self.keep_assoc_var.set("关联影片：—")
        self.keep_score_var.set("资料完整度：—")
        self.keep_provider_var.set("—")
        self.dup_name_var.set("—")
        self.dup_id_var.set("Person ID: —")
        self.dup_assoc_var.set("关联影片：—")
        self.dup_score_var.set("资料完整度：—")
        self.dup_provider_var.set("—")
        self.people_migration_hint_var.set("扫描完成后，可在此处比较重复 Person。")
        self.migrate_button.configure(state="disabled", text="无可迁移关联")
        self._set_person_image_placeholder(self.keep_image_label)
        self._set_person_image_placeholder(self.dup_image_label)

    def render_duplicate_candidate(self, candidate: dict[str, Any]) -> None:
        self.people_selected_candidate = candidate
        left = candidate["Left"]
        right = candidate["Right"]
        left_id = str(left.get("Id") or "")
        right_id = str(right.get("Id") or "")
        left_assoc = len(self.person_associations.get(left_id, []))
        right_assoc = len(self.person_associations.get(right_id, []))

        self.duplicate_title_var.set(
            f"{left.get('Name') or '未知人物'}  ←  {right.get('Name') or '未知人物'}"
        )
        self.duplicate_reason_var.set(candidate.get("Reason") or "")
        self.duplicate_confidence_var.set(f"置信度 {candidate.get('Confidence', '—')}")

        self.keep_name_var.set(str(left.get("Name") or "未知人物"))
        self.keep_id_var.set(f"Person ID: {left_id or '—'}")
        self.keep_assoc_var.set(f"关联影片：{left_assoc} 部")
        self.keep_score_var.set(
            f"资料完整度：{person_completeness(left, left_assoc)} / 100"
        )
        self.keep_provider_var.set(self._provider_text(left))

        self.dup_name_var.set(str(right.get("Name") or "未知人物"))
        self.dup_id_var.set(f"Person ID: {right_id or '—'}")
        self.dup_assoc_var.set(f"关联影片：{right_assoc} 部")
        self.dup_score_var.set(
            f"资料完整度：{person_completeness(right, right_assoc)} / 100"
        )
        self.dup_provider_var.set(self._provider_text(right))

        conflict_text = ""
        if candidate.get("Conflicts"):
            conflict_text = f"；Provider 冲突：{'、'.join(candidate['Conflicts'])}"
        if right_assoc > 0:
            self.migrate_button.configure(
                state="normal",
                text="迁移右侧关联 → 保留左侧人物",
            )
            self.people_migration_hint_var.set(
                f"预计迁移 {right_assoc} 部关联影片{conflict_text}\n"
                "迁移只修改当前选择媒体库范围内的影片 People 关联，不会自动删除右侧 Person 实体。"
            )
        else:
            self.migrate_button.configure(
                state="disabled",
                text="无可迁移关联",
            )
            self.people_migration_hint_var.set(
                "右侧 Person 在当前媒体库范围内没有关联影片，因此没有可执行的迁移。\n"
                "可交换保留方向，或调整上方媒体库范围后重新扫描。"
            )

        self.people_image_generation += 1
        self.people_photo_refs.clear()
        generation = self.people_image_generation
        self._load_person_image(left, self.keep_image_label, "keep", generation)
        self._load_person_image(right, self.dup_image_label, "duplicate", generation)

    @staticmethod
    def _provider_text(person: dict[str, Any]) -> str:
        providers = person_provider_ids(person)
        if not providers:
            return "—"
        return "\n".join(
            f"{key} = {value}"
            for key, value in sorted(providers.items(), key=lambda item: item[0].casefold())
        )

    def _set_person_image_placeholder(self, label: tk.Label, text: str = "无头像") -> None:
        label.configure(image="", text=text)
        key = str(label)
        self.people_photo_refs.pop(key, None)

    def _load_person_image(
        self,
        person: dict[str, Any],
        label: tk.Label,
        side: str,
        generation: int,
    ) -> None:
        has_image = bool(
            person.get("PrimaryImageTag")
            or (person.get("ImageTags") or {}).get("Primary")
        )
        person_id = str(person.get("Id") or "")
        if not has_image or not person_id:
            self._set_person_image_placeholder(label)
            return

        self._set_person_image_placeholder(label, "加载中…")

        def worker() -> None:
            try:
                raw = self.client().get_bytes(
                    f"/Items/{urllib.parse.quote(person_id, safe='')}/Images/Primary",
                    {"maxWidth": 120, "maxHeight": 160, "format": "png"},
                )
            except Exception:
                raw = b""

            def done() -> None:
                if generation != self.people_image_generation or not raw:
                    if generation == self.people_image_generation:
                        self._set_person_image_placeholder(label)
                    return
                try:
                    encoded = base64.b64encode(raw).decode("ascii")
                    image = tk.PhotoImage(data=encoded)
                    label.configure(image=image, text="")
                    self.people_photo_refs[f"{side}:{person_id}:{generation}"] = image
                except Exception:
                    self._set_person_image_placeholder(label)

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def swap_duplicate_direction(self) -> None:
        candidate = self.people_selected_candidate
        if not candidate:
            return
        candidate["Left"], candidate["Right"] = candidate["Right"], candidate["Left"]
        candidate["LeftScore"], candidate["RightScore"] = (
            candidate.get("RightScore", 0),
            candidate.get("LeftScore", 0),
        )
        self.render_duplicate_candidate(candidate)

        selected = self.duplicate_tree.selection()
        if selected:
            left = candidate["Left"]
            right = candidate["Right"]
            self.duplicate_tree.item(
                selected[0],
                values=(
                    f"{candidate['Confidence']}分",
                    f"{left.get('Name') or '未知'}  ←  {right.get('Name') or '未知'}",
                ),
            )

    def migrate_selected_duplicate(self) -> None:
        candidate = self.people_selected_candidate
        if not candidate:
            messagebox.showwarning(APP_TITLE, "请先选择一组重复人物。")
            return

        keep_person = dict(candidate["Left"])
        duplicate_person = dict(candidate["Right"])
        keep_id = str(keep_person.get("Id") or "")
        duplicate_id = str(duplicate_person.get("Id") or "")
        associations = list(self.person_associations.get(duplicate_id, []))
        if not associations:
            messagebox.showinfo(
                APP_TITLE,
                "右侧人物当前没有关联影片。人物实体不会被自动删除，可重新扫描确认状态。",
            )
            return

        conflict_note = ""
        if candidate.get("Conflicts"):
            conflict_note = (
                "\n\n检测到 Provider ID 冲突："
                + "、".join(candidate["Conflicts"])
                + "。请确认保留方向正确。"
            )

        if not messagebox.askyesno(
            APP_TITLE,
            f"确认把右侧人物“{duplicate_person.get('Name') or duplicate_id}”的 "
            f"{len(associations)} 部关联影片迁移到左侧“{keep_person.get('Name') or keep_id}”？"
            f"\n\n只修改影片 People 关联，不会删除 Person 实体。{conflict_note}",
            icon="warning",
        ):
            return

        try:
            client = self.client()
        except Exception as exc:
            self.job_error(exc)
            return

        def worker() -> tuple[int, list[dict[str, str]], list[dict[str, Any]]]:
            user_id, _ = client.get_admin_user_id()
            success = 0
            failed: list[dict[str, str]] = []
            updated_movies: list[dict[str, Any]] = []
            for movie in associations:
                movie_id = str(movie.get("Id") or "")
                try:
                    full_item = client.get_full_item(user_id, movie_id)
                    payload, replaced = replace_person_reference(
                        full_item,
                        duplicate_person,
                        keep_person,
                    )
                    if replaced <= 0:
                        continue
                    client.post_json(
                        f"/Items/{urllib.parse.quote(movie_id, safe='')}",
                        payload,
                    )
                    verified = client.get_full_item(user_id, movie_id)
                    verified_ids = {
                        str(person.get("Id") or "").strip()
                        for person in (verified.get("People") or [])
                    }
                    if duplicate_id in verified_ids or keep_id not in verified_ids:
                        raise RuntimeError("Emby 返回的 People 关联未按目标 Person ID 更新")
                    success += 1
                    updated_movies.append(movie)
                except Exception as exc:
                    failed.append(
                        {
                            "Id": movie_id,
                            "Name": str(movie.get("Name") or movie_id),
                            "Error": str(exc),
                        }
                    )
            return success, failed, updated_movies

        def done(
            result: tuple[int, list[dict[str, str]], list[dict[str, Any]]]
        ) -> None:
            success, failed, updated_movies = result
            keep_bucket = self.person_associations.setdefault(keep_id, [])
            known = {str(item.get("Id") or "") for item in keep_bucket}
            for movie in updated_movies:
                movie_id = str(movie.get("Id") or "")
                if movie_id not in known:
                    keep_bucket.append(movie)
                    known.add(movie_id)

            failed_ids = {str(item.get("Id") or "") for item in failed}
            self.person_associations[duplicate_id] = [
                movie
                for movie in associations
                if str(movie.get("Id") or "") in failed_ids
            ]
            self.render_duplicate_candidate(candidate)
            self.status_var.set(
                f"迁移完成：更新 {success} 个 Movie，失败 {len(failed)}；Person 实体未自动删除。"
            )
            if failed:
                detail = "\n".join(
                    f"{item.get('Name') or item.get('Id')}: {item.get('Error')}"
                    for item in failed[:8]
                )
                if len(failed) > 8:
                    detail += f"\n……另有 {len(failed) - 8} 项失败"
                messagebox.showwarning(
                    APP_TITLE,
                    f"迁移完成，但有部分影片更新失败：\n\n{detail}\n\n"
                    "建议重新扫描确认重复关系。",
                )
            else:
                messagebox.showinfo(
                    APP_TITLE,
                    f"迁移完成：更新 {success} 个 Movie。\n\n"
                    "人物实体没有被自动删除；建议重新扫描确认重复关系。",
                )

        self.run_job("正在迁移人物关联……", worker, done)
