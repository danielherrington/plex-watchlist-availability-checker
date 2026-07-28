#!/usr/bin/env python3
import unittest
from unittest.mock import patch
import datetime
from processor import (
    normalize_title,
    check_watchlist,
    index_watchlist,
    check_unwatched_not_watchlist,
    calculate_movie_sagas,
    calculate_tv_show_schedules
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
        
        missing, total = check_watchlist(watchlist, local_guids, local_titles, [])
        
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

    @patch('processor.load_sagas')
    def test_calculate_movie_sagas(self, mock_load_sagas):
        # Mock sagas.json content
        mock_load_sagas.return_value = {
            "James Bond": ["Dr. No", "From Russia with Love", "Goldfinger"]
        }
        
        local_titles = {
            "dr no": [{
                "title": "Dr. No",
                "type": "movie",
                "year": 1962,
                "isPlayed": True,
                "ratingKey": "1001",
                "poster_url": ""
            }],
            "from russia with love": [{
                "title": "From Russia with Love",
                "type": "movie",
                "year": 1963,
                "isPlayed": False,
                "ratingKey": "1002",
                "poster_url": ""
            }]
            # Goldfinger is missing
        }
        
        active_sagas, sagas_progress = calculate_movie_sagas(local_titles, "mock_server_id")
        
        # Progress stats
        self.assertEqual(len(sagas_progress), 1)
        self.assertEqual(sagas_progress[0]['title'], "James Bond")
        self.assertEqual(sagas_progress[0]['watched_movies'], 1)
        self.assertEqual(sagas_progress[0]['total_movies'], 3)
        self.assertEqual(sagas_progress[0]['percentage'], 33)
        self.assertEqual(sagas_progress[0]['next_movie'], "From Russia with Love")
        self.assertEqual(sagas_progress[0]['next_movie_status'], "available")
        
        # Active sagas for Continue Watching
        self.assertEqual(len(active_sagas), 1)
        self.assertEqual(active_sagas[0]['title'], "James Bond")
        self.assertEqual(active_sagas[0]['status'], "available")
        self.assertEqual(active_sagas[0]['next_movie']['title'], "From Russia with Love")
        self.assertEqual(active_sagas[0]['plex_link'], "https://app.plex.tv/desktop/#!/server/mock_server_id/details?key=%2Flibrary%2Fmetadata%2F1002")

    @patch('processor.query_tvmaze')
    def test_calculate_tv_show_schedules(self, mock_query_tvmaze):
        # Mock TVmaze response
        mock_query_tvmaze.return_value = {
            "_embedded": {
                "episodes": [
                    {"season": 1, "number": 1, "name": "Pilot", "airdate": "2026-07-20"},
                    {"season": 1, "number": 2, "name": "Next Ep", "airdate": "2026-08-05"} # future episode relative to test
                ]
            }
        }
        
        # Today is 2026-07-28
        in_progress_shows = [{
            'title': 'Silo',
            'last_watched': {
                'season': 1,
                'episode': 1,
                'title': 'Pilot'
            },
            'next_ep_local': None, # Not available locally
            'viewed_episodes': 1,
            'total_episodes': 1,
            'ratingKey': '2001',
            'guid': 'plex://show/2001',
            'poster_url': ''
        }]
        
        # Run schedules check
        tv_schedules = calculate_tv_show_schedules(in_progress_shows, "mock_server_id")
        
        self.assertEqual(len(tv_schedules), 1)
        self.assertEqual(tv_schedules[0]['title'], "Silo")
        self.assertEqual(tv_schedules[0]['status'], "mid_season_upcoming")
        self.assertIn("airing on 2026-08-05", tv_schedules[0]['status_label'])
        self.assertEqual(tv_schedules[0]['next_episode']['season'], 1)
        self.assertEqual(tv_schedules[0]['next_episode']['episode'], 2)

if __name__ == '__main__':
    unittest.main()
