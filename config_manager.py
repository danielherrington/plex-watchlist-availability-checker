import os
import json

CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(CONFIG_DIR, ".plex_config.json")
SAGAS_FILE = os.path.join(CONFIG_DIR, "sagas.json")
WATCH_NEXT_FILE = os.path.join(CONFIG_DIR, "watch_next.json")
IGNORED_SHOWS_FILE = os.path.join(CONFIG_DIR, "ignored_shows.json")
TVMAZE_CACHE_FILE = os.path.join(CONFIG_DIR, ".tvmaze_cache.json")

def load_config():
    """Loads configuration from the local JSON file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load config file: {e}")
    return {}

def save_config(config):
    """Saves configuration to the local JSON file."""
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save config file: {e}")

def load_sagas():
    """Loads defined movie collections (sagas) from sagas.json."""
    if os.path.exists(SAGAS_FILE):
        try:
            with open(SAGAS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load sagas file: {e}")
    return {}

def load_watch_next():
    """Loads watch next items from watch_next.json, creating it if missing."""
    if os.path.exists(WATCH_NEXT_FILE):
        try:
            with open(WATCH_NEXT_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load watch_next file: {e}")
    else:
        save_watch_next([])
    return []

def save_watch_next(titles):
    """Saves watch next items to watch_next.json."""
    try:
        with open(WATCH_NEXT_FILE, "w") as f:
            json.dump(titles, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save watch_next file: {e}")

def load_ignored_shows():
    """Loads ignored TV shows from ignored_shows.json, creating it if missing."""
    if os.path.exists(IGNORED_SHOWS_FILE):
        try:
            with open(IGNORED_SHOWS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load ignored_shows file: {e}")
    else:
        save_ignored_shows([])
    return []

def save_ignored_shows(titles):
    """Saves ignored shows to ignored_shows.json."""
    try:
        with open(IGNORED_SHOWS_FILE, "w") as f:
            json.dump(titles, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save ignored_shows file: {e}")

def load_tvmaze_cache():
    """Loads the TVmaze API cache."""
    if os.path.exists(TVMAZE_CACHE_FILE):
        try:
            with open(TVMAZE_CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_tvmaze_cache(cache):
    """Saves the TVmaze API cache."""
    try:
        with open(TVMAZE_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=4)
    except Exception as e:
        print(f"Warning: Failed to save tvmaze cache: {e}")

import time
import threading

class PlexMemoryCache:
    def __init__(self, ttl=300):
        self.ttl = ttl
        self.cache = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() - entry['timestamp'] < self.ttl:
                    return entry['data']
                else:
                    del self.cache[key]
            return None

    def set(self, key, data):
        with self.lock:
            self.cache[key] = {
                'timestamp': time.time(),
                'data': data
            }

    def clear(self):
        with self.lock:
            self.cache.clear()

global_plex_cache = PlexMemoryCache(ttl=300)
