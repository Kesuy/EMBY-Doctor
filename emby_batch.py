#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Emby Media Library Batch Processor.

Batch utilities for selected Emby libraries:
1. Delete Primary images for actors appearing in the selected libraries.
2. Scan movies that contain no Actor entries.
3. Delete Director entries from movies while preserving other People metadata.

Destructive commands are dry-run by default and require --execute.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

__version__ = "1.0.0"


class EmbyError(RuntimeError):
    pass


class EmbyClient:
    def __init__(self, base_url: str, api_key: str, verify_ssl: bool = True, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.ssl_context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()

    def api_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        if self.base_url.lower().endswith("/emby"):
            return self.base_url + path
        return self.base_url + "/emby" + path

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> tuple[int, bytes]:
        url = self.api_url(path)
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url += "?" + query

        body = None
        headers = {
            "X-Emby-Token": self.api_key,
            "Accept": "application/json",
            "User-Agent": f"EmbyMediaLibraryBatchProcessor/{__version__}",
        }
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ssl_context, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace").strip()
            except Exception:
                pass
            raise EmbyError(f"HTTP {exc.code} {method} {path}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise EmbyError(f"无法连接 Emby：{exc.reason}") from exc

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        _, raw = self._request("GET", path, params=params)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def post_json(self, path: str, data: dict[str, Any]) -> int:
        status, _ = self._request("POST", path, data=data)
        return status

    def delete(self, path: str) -> int:
        status, _ = self._request("DELETE", path)
        return status

    def query_items(
        self,
        library_id: str,
        *,
        include_item_types: str = "Movie",
        fields: str = "People,Path,ProviderIds",
        page_size: int = 500,
    ) -> Iterable[dict[str, Any]]:
        start = 0
        while True:
            data = self.get_json(
                "/Items",
                {
                    "ParentId": library_id,
                    "Recursive": "true",
                    "IncludeItemTypes": include_item_types,
                    "Fields": fields,
                    "StartIndex": start,
                    "Limit": page_size,
                    "SortBy": "SortName",
                    "SortOrder": "Ascending",
                },
            )
            items = data.get("Items") or []
            total = int(data.get("TotalRecordCount", len(items)))
            for item in items:
                yield item
            start += len(items)
            if not items or start >= total:
                break

    def query_actors_with_primary_image(self, library_id: str, page_size: int = 500) -> Iterable[dict[str, Any]]:
        start = 0
        while True:
            data = self.get_json(
                "/Persons",
                {
                    "ParentId": library_id,
                    "Recursive": "true",
                    "PersonTypes": "Actor",
                    "ImageTypes": "Primary",
                    "EnableImages": "true",
                    "StartIndex": start,
                    "Limit": page_size,
                    "SortBy": "SortName",
                    "SortOrder": "Ascending",
                },
            )
            items = data.get("Items") or []
            total = int(data.get("TotalRecordCount", len(items)))
            for item in items:
                if item.get("Id") and has_primary_image(item):
                    yield item
            start += len(items)
            if not items or start >= total:
                break

    def get_admin_user_id(self) -> tuple[str, str]:
        data = self.get_json("/Users/Query", {"IsDisabled": "false", "Limit": 100})
        for user in data.get("Items") or []:
            policy = user.get("Policy") or {}
            if policy.get("IsAdministrator") and user.get("Id"):
                return str(user["Id"]), str(user.get("Name") or "Administrator")
        raise EmbyError("没有找到可用的 Emby 管理员用户，请使用 --user-id 手动指定。")

    def get_full_item(self, user_id: str, item_id: str) -> dict[str, Any]:
        return self.get_json(
            f"/Users/{urllib.parse.quote(user_id, safe='')}/Items/{urllib.parse.quote(item_id, safe='')}"
        )


def has_primary_image(person: dict[str, Any]) -> bool:
    return bool(person.get("PrimaryImageTag") or (person.get("ImageTags") or {}).get("Primary"))


def people_of_type(item: dict[str, Any], person_type: str) -> list[dict[str, Any]]:
    wanted = person_type.strip().lower()
    return [
        p
        for p in (item.get("People") or [])
        if str(p.get("Type") or "").strip().lower() == wanted
    ]


def has_actor(item: dict[str, Any]) -> bool:
    return bool(people_of_type(item, "Actor"))


def remove_directors(item: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(item)
    result["People"] = [
        p
        for p in (result.get("People") or [])
        if str(p.get("Type") or "").strip().lower() != "director"
    ]
    # UserData is user-specific playback state rather than editable metadata.
    result.pop("UserData", None)
    return result


def parse_library_ids(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part and part not in result:
                result.append(part)
    return result


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_client(args: argparse.Namespace) -> EmbyClient:
    url = (args.url or os.environ.get("EMBY_URL") or "").strip()
    api_key = (args.api_key or os.environ.get("EMBY_API_KEY") or "").strip()
    if not url:
        raise EmbyError("缺少 Emby 地址。请使用 --url 或 EMBY_URL。")
    if not api_key:
        raise EmbyError("缺少 API Key。请使用 --api-key 或 EMBY_API_KEY。")
    return EmbyClient(url, api_key, verify_ssl=not args.no_verify_ssl, timeout=args.timeout)


def require_libraries(args: argparse.Namespace) -> list[str]:
    ids = parse_library_ids(args.library_id)
    if not ids:
        raise EmbyError("至少需要一个 --library-id。多个媒体库可重复参数或使用逗号分隔。")
    return ids


def cmd_delete_actor_images(args: argparse.Namespace) -> int:
    client = build_client(args)
    libraries = require_libraries(args)
    actors: dict[str, dict[str, Any]] = {}

    print("扫描指定媒体库中有 Primary 头像的演员……")
    for library_id in libraries:
        count = 0
        for person in client.query_actors_with_primary_image(library_id, args.page_size):
            person_id = str(person["Id"])
            actors[person_id] = {"Id": person_id, "Name": person.get("Name") or "未知演员"}
            count += 1
        print(f"  媒体库 {library_id}: {count} 条演员记录")

    ordered = sorted(actors.values(), key=lambda x: str(x["Name"]).casefold())
    print(f"去重后共有 {len(ordered)} 个演员头像待处理。")
    print("警告：Emby Person 是全局共享对象；删除后，同一演员在其他媒体库中的头像也会消失。")
    for i, actor in enumerate(ordered, 1):
        print(f"[{i}] {actor['Name']} [{actor['Id']}]")

    if not args.execute:
        print("\nDRY-RUN：未删除任何头像。确认无误后添加 --execute。")
        return 0

    success = failed = 0
    for i, actor in enumerate(ordered, 1):
        try:
            client.delete(f"/Items/{urllib.parse.quote(actor['Id'], safe='')}/Images/Primary")
            success += 1
            print(f"[{i}/{len(ordered)}] ✓ {actor['Name']}")
        except EmbyError as exc:
            failed += 1
            print(f"[{i}/{len(ordered)}] ✗ {actor['Name']}: {exc}")
    print(f"完成：成功 {success}，失败 {failed}。")
    return 0 if failed == 0 else 2


def cmd_scan_missing_actors(args: argparse.Namespace) -> int:
    client = build_client(args)
    libraries = require_libraries(args)
    missing: list[dict[str, Any]] = []
    total = 0

    item_types = "Movie,Video" if args.include_video else "Movie"
    for library_id in libraries:
        library_total = library_missing = 0
        for movie in client.query_items(
            library_id,
            include_item_types=item_types,
            fields="People,Path,ProviderIds",
            page_size=args.page_size,
        ):
            total += 1
            library_total += 1
            if not has_actor(movie):
                library_missing += 1
                missing.append(
                    {
                        "LibraryId": library_id,
                        "Id": str(movie.get("Id") or ""),
                        "Name": movie.get("Name") or "",
                        "Path": movie.get("Path") or "",
                        "ProviderIds": movie.get("ProviderIds") or {},
                    }
                )
        print(f"媒体库 {library_id}: 扫描 {library_total}，无演员 {library_missing}")

    print(f"总计扫描 {total} 部，发现 {len(missing)} 部没有 Actor 信息。")
    for i, movie in enumerate(missing, 1):
        print(f"[{i}] {movie['Name']} [{movie['Id']}]")
        if movie["Path"]:
            print(f"    {movie['Path']}")

    if not args.no_csv:
        output = Path(args.csv or f"reports/emby_movies_without_actors_{timestamp()}.csv")
        ensure_parent(output)
        with output.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["LibraryId", "ItemId", "Name", "Path", "ProviderIds"])
            for movie in missing:
                writer.writerow(
                    [
                        movie["LibraryId"],
                        movie["Id"],
                        movie["Name"],
                        movie["Path"],
                        json.dumps(movie["ProviderIds"], ensure_ascii=False),
                    ]
                )
        print(f"CSV 已保存：{output.resolve()}")
    return 0


def cmd_delete_directors(args: argparse.Namespace) -> int:
    client = build_client(args)
    libraries = require_libraries(args)

    candidates: dict[str, dict[str, Any]] = {}
    for library_id in libraries:
        scanned = with_director = 0
        for movie in client.query_items(
            library_id,
            include_item_types="Movie",
            fields="People,Path",
            page_size=args.page_size,
        ):
            scanned += 1
            directors = people_of_type(movie, "Director")
            if not directors:
                continue
            with_director += 1
            item_id = str(movie.get("Id") or "")
            candidates[item_id] = {
                "Id": item_id,
                "Name": movie.get("Name") or item_id,
                "Path": movie.get("Path") or "",
                "Directors": [str(p.get("Name") or "") for p in directors],
            }
        print(f"媒体库 {library_id}: 扫描 {scanned}，含导演 {with_director}")

    ordered = sorted(candidates.values(), key=lambda x: str(x["Name"]).casefold())
    print(f"去重后共有 {len(ordered)} 部影片含 Director 信息。")
    for i, movie in enumerate(ordered, 1):
        print(f"[{i}] {movie['Name']} [{movie['Id']}] 导演：{', '.join(movie['Directors'])}")

    if not args.execute:
        print("\nDRY-RUN：未修改任何影片。确认无误后添加 --execute。")
        print("注意：若本地 NFO 中仍包含 <director>，以后刷新元数据时导演可能再次被导入。")
        return 0

    user_id = args.user_id
    if user_id:
        print(f"使用指定用户 ID：{user_id}")
    else:
        user_id, user_name = client.get_admin_user_id()
        print(f"自动使用管理员用户：{user_name} [{user_id}]")

    full_items: list[dict[str, Any]] = []
    fetch_failed = 0
    for i, movie in enumerate(ordered, 1):
        try:
            item = client.get_full_item(user_id, movie["Id"])
            if people_of_type(item, "Director"):
                full_items.append(item)
            else:
                print(f"[{i}/{len(ordered)}] - 已无导演：{movie['Name']}")
        except EmbyError as exc:
            fetch_failed += 1
            print(f"[{i}/{len(ordered)}] ✗ 读取失败 {movie['Name']}: {exc}")

    if not full_items:
        print("没有可修改的影片。")
        return 2 if fetch_failed else 0

    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"emby_director_backup_{timestamp()}.json"
    with backup_path.open("w", encoding="utf-8") as f:
        json.dump(full_items, f, ensure_ascii=False, indent=2)
    print(f"修改前完整元数据已备份到本地：{backup_path.resolve()}")

    success = failed = 0
    for i, item in enumerate(full_items, 1):
        item_id = str(item.get("Id") or "")
        name = str(item.get("Name") or item_id)
        directors = [str(p.get("Name") or "") for p in people_of_type(item, "Director")]
        try:
            payload = remove_directors(item)
            client.post_json(f"/Items/{urllib.parse.quote(item_id, safe='')}", payload)
            success += 1
            print(f"[{i}/{len(full_items)}] ✓ {name} | 删除：{', '.join(directors)}")
        except EmbyError as exc:
            failed += 1
            print(f"[{i}/{len(full_items)}] ✗ {name}: {exc}")

    print(f"完成：成功 {success}，更新失败 {failed}，读取失败 {fetch_failed}。")
    print(f"备份：{backup_path.resolve()}")
    return 0 if failed == 0 and fetch_failed == 0 else 2


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", help="Emby 地址，例如 http://192.168.1.10:8096；也可用 EMBY_URL")
    parser.add_argument("--api-key", help="Emby API Key；也可用 EMBY_API_KEY")
    parser.add_argument(
        "--library-id",
        action="append",
        help="媒体库 ID。可重复使用，也可用逗号分隔多个 ID。",
    )
    parser.add_argument("--no-verify-ssl", action="store_true", help="忽略 HTTPS 证书校验（自签名证书场景）")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP 超时秒数，默认 60")
    parser.add_argument("--page-size", type=int, default=500, help="分页大小，默认 500")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emby-batch",
        description="Emby Media Library Batch Processor",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_actor = sub.add_parser("delete-actor-images", help="删除指定媒体库涉及演员的 Primary 头像")
    add_connection_args(p_actor)
    p_actor.add_argument("--execute", action="store_true", help="真正执行；不加时仅预览")
    p_actor.set_defaults(func=cmd_delete_actor_images)

    p_scan = sub.add_parser("scan-missing-actors", help="扫描没有 Actor 信息的影片")
    add_connection_args(p_scan)
    p_scan.add_argument("--include-video", action="store_true", help="同时扫描 Video 类型")
    p_scan.add_argument("--csv", help="CSV 输出路径；默认 reports/ 下带时间戳文件")
    p_scan.add_argument("--no-csv", action="store_true", help="不输出 CSV")
    p_scan.set_defaults(func=cmd_scan_missing_actors)

    p_director = sub.add_parser("delete-directors", help="删除指定媒体库所有影片的 Director 信息")
    add_connection_args(p_director)
    p_director.add_argument("--user-id", help="用于获取完整项目的 Emby 用户 ID；默认自动找管理员")
    p_director.add_argument("--backup-dir", default="backups", help="本地备份目录，默认 ./backups")
    p_director.add_argument("--execute", action="store_true", help="真正执行；不加时仅预览")
    p_director.set_defaults(func=cmd_delete_directors)
    return parser


def interactive_args(parser: argparse.ArgumentParser) -> list[str]:
    print("Emby Media Library Batch Processor")
    print("1. 删除指定媒体库演员头像")
    print("2. 扫描没有演员信息的影片")
    print("3. 删除指定媒体库影片导演信息")
    choice = input("选择功能 [1-3]：").strip()
    command = {"1": "delete-actor-images", "2": "scan-missing-actors", "3": "delete-directors"}.get(choice)
    if not command:
        parser.print_help()
        return []
    url = input("Emby 地址（例 http://192.168.1.10:8096）：").strip()
    api_key = input("API Key：").strip()
    library_ids = input("媒体库 ID（多个用逗号分隔）：").strip()
    argv = [command, "--url", url, "--api-key", api_key, "--library-id", library_ids]
    if command in {"delete-actor-images", "delete-directors"}:
        execute = input("当前默认仅预览。是否真正执行？输入 YES 确认：").strip()
        if execute == "YES":
            argv.append("--execute")
    return argv


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    if not actual_argv:
        if sys.stdin.isatty():
            actual_argv = interactive_args(parser)
            if not actual_argv:
                return 0
        else:
            parser.print_help()
            return 0
    args = parser.parse_args(actual_argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except EmbyError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
