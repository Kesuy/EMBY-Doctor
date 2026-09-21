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


def complete_directory_path(directory: str, prefix: str) -> str:
    """Convert an Emby-side directory into a locally openable path.

    Existing UNC paths are preserved. When a prefix is configured, POSIX
    roots and Windows drive roots are treated as the remote share-relative
    portion and appended to that prefix.
    """
    value = str(directory or "").strip()
    if not value:
        return ""
    if value.startswith("\\\\"):
        return value

    root = str(prefix or "").strip()
    if not root:
        return value

    normalized = value.replace("/", "\\")
    drive, tail = ntpath.splitdrive(normalized)
    if drive:
        normalized = tail
    return root.rstrip("\\/") + "\\" + normalized.lstrip("\\/")


def default_settings() -> dict[str, Any]:
    return {
        "connection": {
            "url": "",
            "api_key": "",
            "verify_ssl": True,
            "timeout": 60,
        },
        "paths": {
            "directory_prefix": "",
        },
        "libraries": {
            "delete_actor_images": "",
            "scan_missing_actors": "",
            "delete_directors": "",
        },
        "library_names": {
            "delete_actor_images": {},
            "scan_missing_actors": {},
            "delete_directors": {},
        },
        "scopes": {
            "delete_actor_images": "selected",
            "scan_missing_actors": "selected",
            "delete_directors": "selected",
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
        for section in (
            "connection",
            "paths",
            "libraries",
            "library_names",
            "scopes",
            "scan_missing_actors",
        ):
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
            ("媒体库", "LibraryId"),
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
