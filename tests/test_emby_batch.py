import unittest

from emby_batch import (
    EmbyClient,
    has_actor,
    has_primary_image,
    parse_library_ids,
    people_of_type,
    remove_directors,
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


class GuiConfigurationTests(unittest.TestCase):
    def test_default_gui_settings_have_independent_library_ids(self):
        from emby_gui import default_settings

        cfg = default_settings()
        libs = cfg["libraries"]
        scopes = cfg["scopes"]
        expected = {"delete_actor_images", "scan_missing_actors", "delete_directors"}
        self.assertEqual(set(libs), expected)
        self.assertEqual(set(scopes), expected)
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


if __name__ == "__main__":
    unittest.main()
