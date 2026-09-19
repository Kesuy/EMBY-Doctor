#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""GUI entry and local persistence helpers for Emby Media Library Batch Processor."""

from __future__ import annotations

import csv
import json
import ntpath
import os
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

from emby_batch import __version__, timestamp

APP_TITLE = "Emby 媒体库批处理"
SETTINGS_FILE = "settings.json"


def app_dir() -> Path:
    """Directory used for settings, reports and backups.

    A frozen one-file build uses the directory containing the EXE instead of
    PyInstaller's temporary extraction directory.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """Directory containing bundled read-only application resources."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


def resource_path(relative: str) -> Path:
    return bundle_dir() / relative


def settings_path() -> Path:
    return app_dir() / SETTINGS_FILE


def media_directory(path: str) -> str:
    """Return the parent directory without the media filename.

    Emby may run on Linux while this GUI runs on Windows, so handle both
    POSIX and Windows path styles independent of the local OS.
    """
    value = str(path or "").strip()
    if not value:
        return ""
    if "\\" in value or re.match(r"^[A-Za-z]:[\\/]", value):
        return ntpath.dirname(value.rstrip("\\/"))
    return posixpath.dirname(value.rstrip("/"))


def default_settings() -> dict[str, Any]:
    return {
        "connection": {
            "url": "",
            "api_key": "",
            "verify_ssl": True,
            "timeout": 60,
        },
        "libraries": {
            "delete_actor_images": "",
            "scan_missing_actors": "",
            "delete_directors": "",
        },
        "scan_missing_actors": {
            "include_video": False,
        },
    }


def load_settings() -> dict[str, Any]:
    cfg = default_settings()
    path = settings_path()
    if not path.exists():
        return cfg
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return cfg

    if isinstance(loaded, dict):
        for section in ("connection", "libraries", "scan_missing_actors"):
            value = loaded.get(section)
            if isinstance(value, dict):
                cfg[section].update(value)
    return cfg


def save_settings(cfg: dict[str, Any]) -> None:
    path = settings_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _csv_value(value: Any) -> Any:
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple, set)):
        return " | ".join(str(x) for x in value)
    return value


def export_rows_csv(
    filename_prefix: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
) -> Path:
    out_dir = app_dir() / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{filename_prefix}_{timestamp()}.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([title for title, _ in columns])
        for row in rows:
            writer.writerow([_csv_value(row.get(key, "")) for _, key in columns])
    return output


def export_actor_csv(rows: list[dict[str, Any]]) -> Path:
    return export_rows_csv(
        "emby_actor_images",
        [
            ("演员", "Name"),
            ("Person ID", "Id"),
            ("影片所在目录", "Directory"),
            ("状态", "Status"),
        ],
        rows,
    )


def export_missing_csv(rows: list[dict[str, Any]]) -> Path:
    return export_rows_csv(
        "emby_movies_without_actors",
        [
            ("媒体库 ID", "LibraryId"),
            ("Item ID", "Id"),
            ("影片", "Name"),
            ("文件路径", "Path"),
            ("影片所在目录", "Directory"),
            ("ProviderIds", "ProviderIds"),
        ],
        rows,
    )


def export_director_csv(rows: list[dict[str, Any]]) -> Path:
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["DirectorsText"] = ", ".join(str(x) for x in (row.get("Directors") or []))
        prepared.append(item)
    return export_rows_csv(
        "emby_directors",
        [
            ("影片", "Name"),
            ("Item ID", "Id"),
            ("导演", "DirectorsText"),
            ("文件路径", "Path"),
            ("影片所在目录", "Directory"),
            ("状态", "Status"),
        ],
        prepared,
    )


def save_director_backup(items: list[dict[str, Any]]) -> Path:
    out_dir = app_dir() / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"emby_director_backup_{timestamp()}.json"
    output.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args or "-V" in args:
        if sys.stdout is not None:
            print(f"Emby Media Library Batch Processor {__version__}")
        return 0

    try:
        from emby_gui_app import run_gui
    except Exception as exc:  # pragma: no cover - platform dependent
        if sys.stderr is not None:
            print(f"无法启动图形界面：{exc}", file=sys.stderr)
        return 2
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
