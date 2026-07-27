#!/usr/bin/env python3
import unittest
from plex_watchlist_checker import (
    normalize_title,
    check_watchlist,
    index_watchlist,
    check_unwatched_not_watchlist
)

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
            def __init__(self, title, guid, type, year=None):
                self.title = title
                self.guid = guid
                self.type = type
                self.year = year
                self.watchlistedAt = "2026-07-27"
                
        wl_item1 = MockItem("Inception", "plex://movie/1", "movie", 2010)
        wl_item2 = MockItem("Breaking Bad", "plex://show/2", "show")
        wl_item3 = MockItem("Missing Movie", "plex://movie/3", "movie", 2025)
        watchlist = [wl_item1, wl_item2, wl_item3]
        
        local_guids = {"plex://movie/1"} # Match Inception
        local_titles = {
            "breaking bad": [{"type": "show", "year": 2008}] # Fallback Match Breaking Bad
        }
        
        missing, total = check_watchlist(watchlist, local_guids, local_titles)
        
        self.assertEqual(total, 3)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['title'], "Missing Movie")

    def test_index_watchlist_and_check_unwatched(self):
        # Mock class for plex items
        class MockItem:
            def __init__(self, title, guid, type, year=None):
                self.title = title
                self.guid = guid
                self.type = type
                self.year = year
                
        wl_item = MockItem("Inception", "plex://movie/1", "movie", 2010)
        watchlist = [wl_item]
        
        # Index watchlist
        wl_guids, wl_titles = index_watchlist(watchlist)
        self.assertIn("plex://movie/1", wl_guids)
        self.assertIn("inception", wl_titles)
        
        # Unwatched local items
        unwatched_items = [
            {
                'title': 'Inception',
                'year': 2010,
                'type': 'movie',
                'ratingKey': '123',
                'guid': 'plex://movie/1',
                'viewed_episodes': 0,
                'total_episodes': 0,
                'poster_url': ''
            },
            {
                'title': 'The Matrix',
                'year': 1999,
                'type': 'movie',
                'ratingKey': '456',
                'guid': 'plex://movie/4',
                'viewed_episodes': 0,
                'total_episodes': 0,
                'poster_url': ''
            }
        ]
        
        # Check gaps (should find The Matrix as a gap, since Inception is in watchlist)
        gaps = check_unwatched_not_watchlist(unwatched_items, wl_guids, wl_titles, "mock_server_id")
        
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]['title'], 'The Matrix')
        self.assertEqual(gaps[0]['plex_link'], 'https://app.plex.tv/desktop/#!/server/mock_server_id/details?key=%2Flibrary%2Fmetadata%2F456')

if __name__ == '__main__':
    unittest.main()
