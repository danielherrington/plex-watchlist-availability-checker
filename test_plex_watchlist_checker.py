#!/usr/bin/env python3
import unittest
from plex_watchlist_checker import normalize_title, check_watchlist

class TestPlexWatchlistChecker(unittest.TestCase):
    def test_normalize_title(self):
        self.assertEqual(normalize_title("Inception"), "inception")
        self.assertEqual(normalize_title("Spider-Man: No Way Home"), "spiderman no way home")
        self.assertEqual(normalize_title("Amélie"), "amelie")
        self.assertEqual(normalize_title("  The  Matrix  "), "the matrix")
        self.assertEqual(normalize_title(""), "")

    def test_check_watchlist(self):
        # Mock class for plex items
        class MockItem:
            def __init__(self, title, guid, type, year=None, guids=None, thumb=None):
                self.title = title
                self.guid = guid
                self.type = type
                self.year = year
                self.guids = guids
                self.thumb = thumb
                self.watchlistedAt = "2026-07-27"
                
        # Watchlist mockup
        wl_item1 = MockItem("Inception", "plex://movie/1", "movie", 2010)
        wl_item2 = MockItem("Breaking Bad", "plex://show/2", "show")
        wl_item3 = MockItem("Missing Movie", "plex://movie/3", "movie", 2025)
        watchlist = [wl_item1, wl_item2, wl_item3]
        
        # Local library mockup
        local_guids = {"plex://movie/1"} # Match for Inception
        local_titles = {
            "breaking bad": [{"type": "show", "year": 2008}] # Fallback match for Breaking Bad
        }
        
        missing, total = check_watchlist(watchlist, local_guids, local_titles)
        
        self.assertEqual(total, 3)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['title'], "Missing Movie")

if __name__ == '__main__':
    unittest.main()
