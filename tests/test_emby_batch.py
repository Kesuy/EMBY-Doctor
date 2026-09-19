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
        self.assertEqual(set(libs), {"delete_actor_images", "scan_missing_actors", "delete_directors"})
        self.assertTrue(cfg["connection"]["verify_ssl"])

    def test_gui_version_entry_does_not_require_tkinter_mainloop(self):
        from emby_gui import main

        self.assertEqual(main(["--version"]), 0)


if __name__ == "__main__":
    unittest.main()
