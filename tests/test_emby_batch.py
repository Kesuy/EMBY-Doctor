import sys
import unittest

from emby_batch import (
    EmbyClient,
    has_actor,
    has_primary_image,
    parse_library_ids,
    people_of_type,
    remove_directors,
)
from emby_people import (
    build_duplicate_candidates,
    normalize_person_name,
    person_completeness,
    replace_person_reference,
)


class PureFunctionTests(unittest.TestCase):
    def test_api_url_adds_emby_prefix(self):
        c = EmbyClient("http://localhost:8096", "x")
        self.assertEqual(c.api_url("/Items"), "http://localhost:8096/emby/Items")

    def test_api_url_does_not_duplicate_emby_prefix(self):
        c = EmbyClient("http://localhost:8096/emby", "x")
        self.assertEqual(c.api_url("/Items"), "http://localhost:8096/emby/Items")

    def test_refresh_metadata_uses_full_refresh_and_keeps_images(self):
        calls = []

        class RecordingClient(EmbyClient):
            def _request(self, method, path, *, params=None, data=None):
                calls.append((method, path, params, data))
                return 204, b""

        c = RecordingClient("http://localhost:8096", "x")
        self.assertEqual(c.refresh_metadata("12/3"), 204)
        method, path, params, data = calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/Items/12%2F3/Refresh")
        self.assertEqual(params["MetadataRefreshMode"], "FullRefresh")
        self.assertEqual(params["ImageRefreshMode"], "FullRefresh")
        self.assertEqual(params["ReplaceAllMetadata"], "true")
        self.assertEqual(params["ReplaceAllImages"], "false")
        self.assertIsNone(data)

    def test_list_libraries_returns_sorted_id_name_pairs(self):
        class RecordingClient(EmbyClient):
            def get_json(self, path, params=None):
                self.assert_path = path
                return {
                    "Items": [
                        {"Id": "2", "Name": "电视剧"},
                        {"Id": "1", "Name": "电影"},
                        {"Id": "", "Name": "忽略"},
                    ]
                }

        c = RecordingClient("http://localhost:8096", "x")
        self.assertEqual(
            c.list_libraries(),
            [
                {"Id": "1", "Name": "电影"},
                {"Id": "2", "Name": "电视剧"},
            ],
        )
        self.assertEqual(c.assert_path, "/Library/MediaFolders")

    def test_parse_library_ids(self):
        self.assertEqual(parse_library_ids(["1,2", "2", " 3 "]), ["1", "2", "3"])

    def test_has_primary_image(self):
        self.assertTrue(has_primary_image({"PrimaryImageTag": "abc"}))
        self.assertTrue(has_primary_image({"ImageTags": {"Primary": "def"}}))
        self.assertFalse(has_primary_image({"ImageTags": {}}))

    def test_actor_detection_ignores_other_people(self):
        item = {"People": [{"Name": "D", "Type": "Director"}]}
        self.assertFalse(has_actor(item))
        item["People"].append({"Name": "A", "Type": "Actor"})
        self.assertTrue(has_actor(item))

    def test_remove_directors_preserves_other_people_and_input(self):
        original = {
            "Name": "Movie",
            "People": [
                {"Name": "Actor A", "Type": "Actor"},
                {"Name": "Director D", "Type": "Director"},
                {"Name": "Writer W", "Type": "Writer"},
            ],
            "UserData": {"Played": True},
        }
        updated = remove_directors(original)
        self.assertEqual([p["Name"] for p in people_of_type(updated, "Actor")], ["Actor A"])
        self.assertEqual(people_of_type(updated, "Director"), [])
        self.assertEqual([p["Name"] for p in people_of_type(updated, "Writer")], ["Writer W"])
        self.assertNotIn("UserData", updated)
        self.assertEqual(len(original["People"]), 3)

    def test_query_people_pages_and_requests_profile_fields(self):
        calls = []

        class RecordingClient(EmbyClient):
            def get_json(self, path, params=None):
                calls.append((path, dict(params or {})))
                start = int((params or {}).get("StartIndex", 0))
                if start == 0:
                    return {
                        "Items": [{"Id": "10", "Name": "A"}, {"Id": "11", "Name": "B"}],
                        "TotalRecordCount": 3,
                    }
                return {
                    "Items": [{"Id": "12", "Name": "C"}],
                    "TotalRecordCount": 3,
                }

        c = RecordingClient("http://localhost:8096", "x")
        rows = list(c.query_people(page_size=2))
        self.assertEqual([row["Id"] for row in rows], ["10", "11", "12"])
        self.assertEqual(calls[0][0], "/Persons")
        self.assertIn("ProviderIds", calls[0][1]["Fields"])
        self.assertTrue(calls[0][1]["EnableImages"])

    def test_duplicate_people_detects_same_name_and_prefers_more_complete_profile(self):
        persons = [
            {
                "Id": "1",
                "Name": "横山 みれい",
                "ProviderIds": {"Tmdb": "100"},
                "PrimaryImageTag": "img",
                "Overview": "bio",
            },
            {
                "Id": "2",
                "Name": "横山みれい",
                "ProviderIds": {"MetaTube": "abc"},
            },
        ]
        candidates = build_duplicate_candidates(persons, {"1": 8, "2": 1})
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["Confidence"], 90)
        self.assertEqual(candidates[0]["Left"]["Id"], "1")
        self.assertEqual(candidates[0]["Right"]["Id"], "2")
        self.assertGreater(
            person_completeness(candidates[0]["Left"], 8),
            person_completeness(candidates[0]["Right"], 1),
        )
        self.assertEqual(normalize_person_name("横山 みれい"), normalize_person_name("横山みれい"))

    def test_duplicate_people_shared_provider_id_has_highest_confidence(self):
        persons = [
            {"Id": "1", "Name": "Alice A", "ProviderIds": {"Tmdb": "123"}},
            {"Id": "2", "Name": "Alice B", "ProviderIds": {"Tmdb": "123"}},
        ]
        candidates = build_duplicate_candidates(persons)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["Confidence"], 100)
        self.assertEqual(candidates[0]["Reason"], "Provider ID 一致")

    def test_replace_person_reference_preserves_roles_and_deduplicates(self):
        original = {
            "Name": "Movie",
            "People": [
                {"Id": "2", "Name": "重复人物", "Type": "Actor", "Role": "A"},
                {"Id": "1", "Name": "保留人物", "Type": "Actor", "Role": "A"},
                {"Id": "2", "Name": "重复人物", "Type": "Actor", "Role": "B"},
                {"Id": "9", "Name": "导演", "Type": "Director", "Role": ""},
            ],
            "UserData": {"Played": True},
        }
        updated, replaced = replace_person_reference(
            original,
            {"Id": "2", "Name": "重复人物"},
            {"Id": "1", "Name": "保留人物"},
        )
        self.assertEqual(replaced, 2)
        actors = people_of_type(updated, "Actor")
        self.assertEqual(
            [(p["Id"], p["Name"], p["Role"]) for p in actors],
            [("1", "保留人物", "A"), ("1", "保留人物", "B")],
        )
        self.assertEqual(len(people_of_type(updated, "Director")), 1)
        self.assertNotIn("UserData", updated)
        self.assertEqual(original["People"][0]["Id"], "2")


class GuiConfigurationTests(unittest.TestCase):
    def test_default_gui_settings_have_independent_library_ids(self):
        from emby_gui import default_settings

        cfg = default_settings()
        libs = cfg["libraries"]
        scopes = cfg["scopes"]
        expected = {"delete_actor_images", "scan_missing_actors", "delete_directors"}
        self.assertEqual(set(libs), expected)
        self.assertEqual(set(scopes), expected)
        self.assertEqual(set(cfg["library_names"]), expected)
        self.assertTrue(all(cfg["library_names"][key] == {} for key in expected))
        self.assertTrue(all(scopes[key] == "selected" for key in expected))
        self.assertTrue(cfg["connection"]["verify_ssl"])
        self.assertEqual(cfg["paths"]["directory_prefix"], "")

    def test_media_directory_supports_windows_and_posix_paths(self):
        from emby_gui import media_directory

        self.assertEqual(
            media_directory(r"D:\\Media\\JAV\\ABC-123\\ABC-123.mp4"),
            r"D:\\Media\\JAV\\ABC-123",
        )
        self.assertEqual(
            media_directory("/media/JAV/ABC-123/ABC-123.mp4"),
            "/media/JAV/ABC-123",
        )
        self.assertEqual(media_directory(""), "")

    def test_complete_directory_path_supports_network_prefix(self):
        from emby_gui import complete_directory_path

        prefix = r"\\192.168.123.111"
        self.assertEqual(
            complete_directory_path("/vol1/JAV/ABC-123", prefix),
            r"\\192.168.123.111\vol1\JAV\ABC-123",
        )
        self.assertEqual(
            complete_directory_path(r"D:\Media\JAV\ABC-123", r"\\server\media"),
            r"\\server\media\Media\JAV\ABC-123",
        )
        self.assertEqual(
            complete_directory_path(r"\\server\share\ABC-123", prefix),
            r"\\server\share\ABC-123",
        )
        self.assertEqual(complete_directory_path("/vol1/JAV/ABC-123", ""), "/vol1/JAV/ABC-123")

    def test_tree_sort_key_handles_numbers_text_and_empty_values(self):
        from emby_gui_app import tree_sort_key

        values = ["10", "2", "beta", "Alpha", ""]
        self.assertEqual(
            sorted(values, key=tree_sort_key),
            ["2", "10", "Alpha", "beta", ""],
        )

    def test_gui_version_entry_does_not_require_tkinter_mainloop(self):
        from emby_gui import main

        self.assertEqual(main(["--version"]), 0)

    @unittest.skipUnless(sys.platform == "win32", "Tk window construction smoke test is Windows-only")
    def test_gui_constructs_with_people_quality_page(self):
        import tkinter as tk

        from emby_gui_app import EmbyBatchApp

        root = tk.Tk()
        root.withdraw()
        try:
            app = EmbyBatchApp(root)
            self.assertIn("people", app.page_frames)
            self.assertIn("people", app.nav_buttons)
            self.assertTrue(hasattr(app, "duplicate_tree"))
            self.assertTrue(hasattr(app, "avatar_tree"))
            self.assertTrue(hasattr(app, "conflict_tree"))
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
