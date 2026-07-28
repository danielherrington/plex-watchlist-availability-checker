#!/usr/bin/env python3
"""
Plex Watchlist Checker & GAP Analyzer
Advanced Media Hub: Tracks Watchlist gaps, Unwatched library gaps, TV Show schedules, Movie Saga progress, Watch Next Queue, and Ignored Shows.
"""

import os
import sys
import json
import argparse
import time
import re
import unicodedata
import webbrowser
import datetime
import requests
from urllib.parse import quote

try:
    from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
except ImportError:
    print("Error: The 'plexapi' package is not installed.")
    print("Please install it using: pip install plexapi")
    sys.exit(1)

# Configuration File Paths
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".plex_config.json")
SAGAS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sagas.json")
TVMAZE_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tvmaze_cache.json")
WATCH_NEXT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch_next.json")
IGNORED_SHOWS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ignored_shows.json")

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
        try:
            with open(WATCH_NEXT_FILE, "w") as f:
                json.dump([], f)
        except Exception:
            pass
    return []

def load_ignored_shows():
    """Loads ignored TV shows from ignored_shows.json, creating it if missing."""
    if os.path.exists(IGNORED_SHOWS_FILE):
        try:
            with open(IGNORED_SHOWS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load ignored_shows file: {e}")
    else:
        try:
            with open(IGNORED_SHOWS_FILE, "w") as f:
                json.dump([], f)
        except Exception:
            pass
    return []

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
    except Exception:
        pass

def query_tvmaze(show_title):
    """Queries TVmaze API for TV show episode lists, utilizing a 24-hour local cache."""
    cache = load_tvmaze_cache()
    now = time.time()
    
    # Check cache
    if show_title in cache:
        cached_data = cache[show_title]
        # Expire cache after 24 hours
        if now - cached_data.get('timestamp', 0) < 86400:
            return cached_data.get('data')
            
    # Query API
    url = "https://api.tvmaze.com/singlesearch/shows"
    try:
        # Search TVmaze and embed episodes guide
        r = requests.get(url, params={"q": show_title, "embed": "episodes"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            # Save to cache
            cache[show_title] = {
                'timestamp': now,
                'data': data
            }
            save_tvmaze_cache(cache)
            return data
    except Exception as e:
        print(f"Warning: Failed to fetch TVmaze details for '{show_title}': {e}")
        
    # Fallback to expired cache if request fails (e.g., offline)
    if show_title in cache:
        return cache[show_title].get('data')
    return None

def authenticate_plex(force_login=False):
    """Authenticates with Plex via PIN (OAuth) flow or cached token."""
    config = load_config()
    token = config.get("token")

    if token and not force_login:
        try:
            print("Authenticating with cached Plex token...")
            account = MyPlexAccount(token=token)
            print(f"Successfully logged in as: {account.username}")
            return account
        except Exception as e:
            print(f"Cached token invalid or expired: {e}")
            print("Restarting authentication flow...")

    # PIN OAuth Flow
    print("\n" + "="*60)
    print("               PLEX AUTHENTICATION REQUIRED")
    print("="*60)
    print("This tool uses Plex's secure OAuth flow. Your password is never shared.")
    
    try:
        pinlogin = MyPlexPinLogin(oauth=True)
    except Exception as e:
        print(f"Error starting OAuth flow: {e}")
        sys.exit(1)

    url = pinlogin.oauthUrl()
    print("\n1. Open the following URL in your web browser:")
    print(f"\n   \033[1;33m{url}\033[0m\n")
    print("2. Sign in to your Plex account and authorize the application.")
    print("="*60 + "\n")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    start_time = time.time()
    login_success = False
    timeout = 300

    while time.time() - start_time < timeout:
        elapsed = int(time.time() - start_time)
        remaining = timeout - elapsed
        print(f"\rWaiting for authorization... {remaining}s remaining (Ctrl+C to cancel)", end="", flush=True)
        
        try:
            if pinlogin.checkLogin():
                login_success = True
                break
        except Exception:
            pass
            
        time.sleep(2)

    print()
    
    if login_success and pinlogin.token:
        token = pinlogin.token
        config["token"] = token
        save_config(config)
        
        account = MyPlexAccount(token=token)
        print(f"\nSuccessfully logged in as: {account.username}")
        return account
    else:
        print("\nAuthentication failed or timed out. Please try again.")
        sys.exit(1)

def select_server(account, target_server_name=None):
    """Selects the Plex Server to compare against."""
    print("Fetching list of available Plex Servers...")
    resources = account.resources()
    servers = [r for r in resources if r.provides == 'server']

    if not servers:
        print("Error: No Plex Servers found associated with this account.")
        sys.exit(1)

    config = load_config()
    saved_server = config.get("server_name")

    selected = None

    if target_server_name:
        for s in servers:
            if s.name.lower() == target_server_name.lower():
                selected = s
                break
        if not selected:
            print(f"Error: Specified server '{target_server_name}' not found.")
            print("Available servers:")
            for s in servers:
                print(f"  - {s.name}")
            sys.exit(1)
    elif saved_server:
        for s in servers:
            if s.name == saved_server:
                selected = s
                break

    if not selected:
        if len(servers) == 1:
            selected = servers[0]
            print(f"Automatically selected server: {selected.name}")
        else:
            print("\nMultiple Plex Servers found:")
            for idx, s in enumerate(servers):
                status = "Owner" if s.owned else "Shared"
                print(f"  [{idx + 1}] {s.name} ({status})")
            
            while True:
                try:
                    choice = input(f"\nSelect server (1-{len(servers)}): ").strip()
                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(servers):
                        selected = servers[choice_idx]
                        break
                except (ValueError, IndexError):
                    pass
                print(f"Invalid selection. Please choose a number from 1 to {len(servers)}.")

    config["server_name"] = selected.name
    save_config(config)
    return selected

def normalize_title(title):
    """Normalizes title for fallback fuzzy matching (accents, cases, punctuation)."""
    if not title:
        return ""
    title = title.lower()
    title = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('utf-8')
    title = re.sub(r'[^a-z0-9\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def build_local_library_index(plex_server, watch_next_titles, ignored_shows_norm):
    """Fetches local server library, indexes items, and gathers TV show/unwatched history."""
    print(f"\nConnecting to Plex Server: {plex_server.name}...")
    try:
        plex = plex_server.connect()
        print(f"Connected to: {plex.friendlyName}")
    except Exception as e:
        print(f"Error: Failed to connect to server: {e}")
        sys.exit(1)

    machine_id = plex.machineIdentifier
    local_guids = set()
    local_titles = {} # Maps normalized_title -> list of movie dictionary metadata
    unwatched_local_items = []
    in_progress_shows = []
    
    # Pre-normalize watch next list for quick matching
    wn_norm = {normalize_title(t) for t in watch_next_titles}

    print("Scanning server library sections (Movies & TV Shows)...")
    for section in plex.library.sections():
        if section.type == 'movie':
            print(f"  Scanning movie section: '{section.title}'...")
            try:
                items = section.all(includeGuids=1)
                for item in items:
                    # Index primary and alternate GUIDs
                    if item.guid:
                        local_guids.add(item.guid.lower())
                    if hasattr(item, 'guids') and item.guids:
                        for g in item.guids:
                            if g.id:
                                local_guids.add(g.id.lower())
                    
                    # Store detailed title mapping for saga and gap matching
                    norm_title = normalize_title(item.title)
                    is_watched = getattr(item, 'isPlayed', False) or getattr(item, 'viewCount', 0) > 0
                    
                    if norm_title:
                        if norm_title not in local_titles:
                            local_titles[norm_title] = []
                        local_titles[norm_title].append({
                            'title': item.title,
                            'type': 'movie',
                            'year': item.year if hasattr(item, 'year') else None,
                            'isPlayed': is_watched,
                            'ratingKey': item.ratingKey,
                            'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                        })
                    
                    # Store unwatched movies
                    if not is_watched:
                        unwatched_local_items.append({
                            'title': item.title,
                            'year': item.year if hasattr(item, 'year') else None,
                            'type': 'movie',
                            'ratingKey': item.ratingKey,
                            'guid': item.guid,
                            'viewed_episodes': 0,
                            'total_episodes': 0,
                            'watch_next': norm_title in wn_norm,
                            'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                        })
            except Exception as e:
                print(f"    Warning: Failed to scan section '{section.title}': {e}")
                
        elif section.type == 'show':
            print(f"  Scanning TV section: '{section.title}'...")
            try:
                items = section.all(includeGuids=1)
                for item in items:
                    norm_title = normalize_title(item.title)
                    
                    # Skip permanently ignored shows
                    if norm_title in ignored_shows_norm:
                        continue

                    if item.guid:
                        local_guids.add(item.guid.lower())
                    if hasattr(item, 'guids') and item.guids:
                        for g in item.guids:
                            if g.id:
                                local_guids.add(g.id.lower())
                    
                    if norm_title:
                        if norm_title not in local_titles:
                            local_titles[norm_title] = []
                        local_titles[norm_title].append({
                            'title': item.title,
                            'type': 'show',
                            'year': item.year if hasattr(item, 'year') else None,
                            'ratingKey': item.ratingKey,
                            'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                        })

                    total_episodes = getattr(item, 'leafCount', 0)
                    viewed_episodes = getattr(item, 'viewedLeafCount', 0)
                    unwatched_count = getattr(item, 'unwatchedLeafCount', 0)

                    # Gather unwatched TV shows (gaps)
                    if unwatched_count > 0 and viewed_episodes == 0:
                        unwatched_local_items.append({
                            'title': item.title,
                            'year': item.year if hasattr(item, 'year') else None,
                            'type': 'show',
                            'ratingKey': item.ratingKey,
                            'guid': item.guid,
                            'viewed_episodes': viewed_episodes,
                            'total_episodes': total_episodes,
                            'watch_next': norm_title in wn_norm,
                            'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                        })

                    # Gather in-progress TV Shows (history started)
                    if viewed_episodes > 0:
                        try:
                            # Retrieve episode watches
                            episodes = item.episodes()
                            episodes = sorted(episodes, key=lambda x: (x.parentIndex or 0, x.index or 0))
                            
                            last_watched = None
                            for ep in episodes:
                                if getattr(ep, 'isPlayed', False) or getattr(ep, 'viewCount', 0) > 0:
                                    last_watched = ep
                                    
                            next_ep_local = None
                            if last_watched:
                                last_idx = episodes.index(last_watched)
                                if last_idx + 1 < len(episodes):
                                    next_ep_local = episodes[last_idx + 1]
                                    
                            in_progress_shows.append({
                                'title': item.title,
                                'last_watched': {
                                    'season': last_watched.parentIndex if last_watched else 1,
                                    'episode': last_watched.index if last_watched else 0,
                                    'title': last_watched.title if last_watched else "None"
                                } if last_watched else None,
                                'next_ep_local': {
                                    'season': next_ep_local.parentIndex,
                                    'episode': next_ep_local.index,
                                    'title': next_ep_local.title,
                                    'ratingKey': next_ep_local.ratingKey,
                                    'air_date': next_ep_local.originallyAvailableAt.strftime('%Y-%m-%d') if next_ep_local.originallyAvailableAt else None
                                } if next_ep_local else None,
                                'viewed_episodes': viewed_episodes,
                                'total_episodes': total_episodes,
                                'ratingKey': item.ratingKey,
                                'guid': item.guid,
                                'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                            })
                        except Exception as e:
                            print(f"    Warning: Failed to fetch episode watches for '{item.title}': {e}")
            except Exception as e:
                print(f"    Warning: Failed to scan section '{section.title}': {e}")
                
    return local_guids, local_titles, unwatched_local_items, in_progress_shows, machine_id

def fetch_watchlist(account, libtype=None):
    """Fetches items from the user's Plex Watchlist."""
    print("\nFetching your Plex Watchlist...")
    try:
        watchlist_items = account.watchlist(maxresults=5000)
        if libtype:
            watchlist_items = [i for i in watchlist_items if i.type == libtype]
        print(f"Retrieved {len(watchlist_items)} watchlist items.")
        return watchlist_items
    except Exception as e:
        print(f"Error fetching watchlist: {e}")
        sys.exit(1)

def check_watchlist(watchlist, local_guids, local_titles, watch_next_titles):
    """Compares watchlist items against local server library to find missing files."""
    print("\nComparing Watchlist against Plex Server...")
    missing_items = []
    total_checked = 0
    matched_count = 0
    wn_norm = {normalize_title(t) for t in watch_next_titles}

    for item in watchlist:
        total_checked += 1
        is_matched = False
        
        if item.guid and item.guid.lower() in local_guids:
            is_matched = True
            
        if not is_matched and item.guid:
            guid_cleaned = item.guid.lower()
            if guid_cleaned in local_guids:
                is_matched = True
                
        if not is_matched:
            norm_title = normalize_title(item.title)
            if norm_title in local_titles:
                for candidate in local_titles[norm_title]:
                    candidate_type = candidate['type']
                    item_type = item.type
                    type_match = (
                        candidate_type == item_type or
                        (candidate_type in ['show', 'tv'] and item_type in ['show', 'tv'])
                    )
                    
                    if type_match:
                        if item_type == 'movie':
                            cand_year = candidate['year']
                            item_year = item.year if hasattr(item, 'year') and item.year else None
                            if cand_year and item_year and abs(cand_year - item_year) <= 1:
                                is_matched = True
                                break
                        else:
                            is_matched = True
                            break
                            
        if is_matched:
            matched_count += 1
        else:
            rating_key = item.guid.rsplit('/', 1)[-1] if item.guid else ""
            
            watchlisted_date = "Unknown Date"
            for attr in ['watchlistedAt', 'addedAt', 'created_at']:
                if hasattr(item, attr) and getattr(item, attr):
                    val = getattr(item, attr)
                    if isinstance(val, datetime.datetime):
                        watchlisted_date = val.strftime('%Y-%m-%d')
                        break
                    elif isinstance(val, str):
                        watchlisted_date = val.split('T')[0]
                        break

            poster_url = ""
            if hasattr(item, 'thumb') and item.thumb:
                if item.thumb.startswith('http'):
                    poster_url = item.thumb
                elif item.thumb.startswith('/'):
                    poster_url = f"https://metadata.provider.plex.tv{item.thumb}"
            elif hasattr(item, 'thumbUrl') and item.thumbUrl:
                poster_url = item.thumbUrl

            missing_items.append({
                'title': item.title,
                'year': item.year if hasattr(item, 'year') else None,
                'type': item.type,
                'ratingKey': rating_key,
                'guid': item.guid,
                'added_at': watchlisted_date,
                'watch_next': normalize_title(item.title) in wn_norm,
                'poster_url': poster_url
            })

    return missing_items, total_checked

def index_watchlist(watchlist):
    """Indexes watchlist items by GUID and title for reverse lookup."""
    wl_guids = set()
    wl_titles = {}
    for item in watchlist:
        if item.guid:
            wl_guids.add(item.guid.lower())
        norm_title = normalize_title(item.title)
        if norm_title:
            if norm_title not in wl_titles:
                wl_titles[norm_title] = []
            wl_titles[norm_title].append({
                'type': item.type,
                'year': item.year if hasattr(item, 'year') else None
            })
    return wl_guids, wl_titles

def check_unwatched_not_watchlist(unwatched_local_items, wl_guids, wl_titles, machine_id):
    """Identifies unwatched local server items that are not present in the user's watchlist."""
    print("Finding unwatched server items not in watchlist...")
    unwatched_not_watchlist = []
    
    for item in unwatched_local_items:
        is_in_watchlist = False
        
        if item['guid'] and item['guid'].lower() in wl_guids:
            is_in_watchlist = True
            
        if not is_in_watchlist:
            norm_title = normalize_title(item['title'])
            if norm_title in wl_titles:
                for candidate in wl_titles[norm_title]:
                    type_match = (
                        candidate['type'] == item['type'] or
                        (candidate['type'] in ['show', 'tv'] and item['type'] in ['show', 'tv'])
                    )
                    if type_match:
                        if item['type'] == 'movie':
                            if candidate['year'] and item['year'] and abs(candidate['year'] - item['year']) <= 1:
                                is_in_watchlist = True
                                break
                        else:
                            is_in_watchlist = True
                            break
                            
        if not is_in_watchlist:
            local_link = f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{item['ratingKey']}"
            
            unwatched_not_watchlist.append({
                'title': item['title'],
                'year': item['year'],
                'type': item['type'],
                'ratingKey': item['ratingKey'],
                'guid': item['guid'],
                'viewed_episodes': item['viewed_episodes'],
                'total_episodes': item['total_episodes'],
                'watch_next': item.get('watch_next', False),
                'poster_url': item['poster_url'],
                'plex_link': local_link
            })
            
    return unwatched_not_watchlist

def calculate_tv_show_schedules(in_progress_shows, machine_id):
    """Integrates TVmaze API to trace next available/missing/upcoming episodes of TV shows."""
    print("\nTracing TV Show Continue Watching & Schedules...")
    tv_schedule_list = []
    today = datetime.date.today()
    
    for show in in_progress_shows:
        title = show['title']
        last_watched = show['last_watched']
        next_ep_local = show['next_ep_local']
        is_watchlist_only = show.get('is_watchlist_only', False)
        
        next_ep_metadata = None
        status = "completed"
        status_label = "Show fully watched"
        plex_link = ""
        
        # Query TVmaze for full episode guide
        tvmaze_data = query_tvmaze(title)
        
        if tvmaze_data and '_embedded' in tvmaze_data and 'episodes' in tvmaze_data['_embedded']:
            episodes = tvmaze_data['_embedded']['episodes']
            # Sort episodes chronologically
            episodes = sorted(episodes, key=lambda x: (x.get('season', 0), x.get('number', 0)))
            
            # Trace last watched season to detect season transitions
            if is_watchlist_only:
                v_count = show['viewed_episodes']
                last_watched_season = episodes[v_count - 1].get('season', 1) if v_count > 0 else 1
            else:
                last_watched_season = last_watched['season'] if last_watched else 1

            next_tvmaze_ep = None
            if is_watchlist_only:
                v_count = show['viewed_episodes']
                if v_count < len(episodes):
                    next_tvmaze_ep = episodes[v_count]
            else:
                s_watched = last_watched['season'] if last_watched else 0
                e_watched = last_watched['episode'] if last_watched else 0
                for ep in episodes:
                    ep_season = ep.get('season', 0)
                    ep_number = ep.get('number', 0)
                    if (ep_season, ep_number) > (s_watched, e_watched):
                        next_tvmaze_ep = ep
                        break
                    
            if next_tvmaze_ep:
                ep_season = next_tvmaze_ep['season']
                ep_number = next_tvmaze_ep['number']
                ep_title = next_tvmaze_ep.get('name', 'TBA')
                airdate_str = next_tvmaze_ep.get('airdate')
                is_new_season = ep_season > last_watched_season
                
                next_ep_metadata = {
                    'season': ep_season,
                    'episode': ep_number,
                    'title': ep_title,
                    'air_date': airdate_str,
                    'ratingKey': show['ratingKey']
                }
                
                # Compare availability against local server
                # Case 1: Next episode matches our local "next episode file"
                if next_ep_local and next_ep_local['season'] == ep_season and next_ep_local['episode'] == ep_number:
                    status = "available"
                    status_label = f"Episode S{ep_season:02d}E{ep_number:02d} available on server"
                    plex_link = f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{next_ep_local['ratingKey']}"
                else:
                    # Case 2: Episode not on local server - check release date
                    if airdate_str:
                        try:
                            air_date = datetime.datetime.strptime(airdate_str, '%Y-%m-%d').date()
                            if air_date > today:
                                days_away = (air_date - today).days
                                if is_new_season:
                                    status = "new_season_upcoming"
                                    if days_away == 1:
                                        status_label = f"New Season {ep_season:02d} starts tomorrow!"
                                    else:
                                        status_label = f"New Season {ep_season:02d} starts on {airdate_str} (in {days_away} days)"
                                else:
                                    status = "mid_season_upcoming"
                                    if days_away == 1:
                                        status_label = f"S{ep_season:02d}E{ep_number:02d} airing tomorrow"
                                    else:
                                        status_label = f"S{ep_season:02d}E{ep_number:02d} airing on {airdate_str} (in {days_away} days)"
                            else:
                                if is_new_season:
                                    status = "new_season_missing"
                                    status_label = f"New Season S{ep_season:02d} released! (Missing from server)"
                                else:
                                    status = "missing"
                                    status_label = f"S{ep_season:02d}E{ep_number:02d} aired on {airdate_str} (Missing from server)"
                        except Exception:
                            status = "missing"
                            status_label = f"S{ep_season:02d}E{ep_number:02d} (Missing from server)"
                    else:
                        status = "missing"
                        status_label = f"S{ep_season:02d}E{ep_number:02d} (Airing details TBA - Missing)"
                    
                    # Generate Discover link for watchlist-only shows
                    discover_key = show['ratingKey']
                    plex_link = f"https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F{discover_key}"
            else:
                # All episodes in guide have been watched
                status = "caught_up"
                status_label = "All Caught Up (No upcoming episodes)"
                discover_key = show['ratingKey']
                plex_link = f"https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F{discover_key}"
        else:
            # Fallback if TVmaze lookup fails: Use local next episode if we have it
            if next_ep_local:
                status = "available"
                status_label = f"Episode S{next_ep_local['season']:02d}E{next_ep_local['episode']:02d} available"
                plex_link = f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{next_ep_local['ratingKey']}"
                next_ep_metadata = {
                    'season': next_ep_local['season'],
                    'episode': next_ep_local['episode'],
                    'title': next_ep_local['title'],
                    'air_date': next_ep_local['air_date']
                }
            else:
                status = "caught_up"
                status_label = "All Caught Up (Schedules offline)"
                discover_key = show['ratingKey']
                plex_link = f"https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F{discover_key}"
                
        # Only include shows that are not fully caught up in Continue Watching
        if status != "caught_up":
            tv_schedule_list.append({
                'title': title,
                'type': 'show',
                'ratingKey': show['ratingKey'],
                'viewed_episodes': show['viewed_episodes'],
                'total_episodes': show['total_episodes'],
                'poster_url': show['poster_url'],
                'status': status,
                'status_label': status_label,
                'plex_link': plex_link,
                'next_episode': next_ep_metadata
            })
            
    return tv_schedule_list

def calculate_movie_sagas(local_titles, machine_id):
    """Loads sagas.json and determines completion stats and next available/missing movies."""
    print("Calculating Movie Sagas watch progress...")
    sagas_data = load_sagas()
    
    active_sagas = []
    all_sagas_progress = []
    
    for saga_name, movie_list in sagas_data.items():
        total_movies = len(movie_list)
        watched_count = 0
        present_count = 0
        next_movie = None
        
        # Track saga movie matches
        for idx, movie_title in enumerate(movie_list):
            norm_title = normalize_title(movie_title)
            movie_in_library = False
            movie_watched = False
            lib_item = None
            
            if norm_title in local_titles:
                for candidate in local_titles[norm_title]:
                    if candidate['type'] == 'movie':
                        movie_in_library = True
                        lib_item = candidate
                        if candidate['isPlayed']:
                            movie_watched = True
                            break
                            
            if movie_in_library:
                present_count += 1
            if movie_watched:
                watched_count += 1
            elif next_movie is None:
                # The first unwatched movie in the saga is the next-up movie
                next_movie = {
                    'title': movie_title,
                    'index': idx + 1,
                    'status': 'available' if movie_in_library else 'missing',
                    'ratingKey': lib_item['ratingKey'] if lib_item else "",
                    'poster_url': lib_item['poster_url'] if lib_item else "",
                    'plex_link': f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{lib_item['ratingKey']}" if lib_item else ""
                }
                
        percentage = int((watched_count / total_movies) * 100) if total_movies > 0 else 0
        
        # Populate all sagas stats for Saga Browser
        all_sagas_progress.append({
            'title': saga_name,
            'watched_movies': watched_count,
            'total_movies': total_movies,
            'percentage': percentage,
            'next_movie': next_movie['title'] if next_movie else "Saga Completed",
            'next_movie_status': next_movie['status'] if next_movie else "completed"
        })
        
        # Saga is "active" if it has been started but not finished
        if watched_count > 0 and watched_count < total_movies and next_movie:
            status_label = f"Next up: {next_movie['title']} - " + ("Available to watch" if next_movie['status'] == 'available' else "Missing from server")
            active_sagas.append({
                'title': saga_name,
                'type': 'saga',
                'viewed_episodes': watched_count,   # Map to common variable for UI sorting
                'total_episodes': total_movies,      # Map to common variable for UI sorting
                'poster_url': next_movie['poster_url'],
                'status': next_movie['status'],
                'status_label': status_label,
                'plex_link': next_movie['plex_link'],
                'next_movie': {
                    'title': next_movie['title'],
                    'index': next_movie['index']
                }
            })
            
    return active_sagas, all_sagas_progress

def generate_html_report(missing_items, unwatched_local_gaps, continue_watching, sagas_progress, ignored_shows, server_name):
    """Generates a premium glassmorphism dark-mode HTML report with 5 tabs and ignore controls."""
    html_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "missing_watchlist.html")
    
    # Pre-sort lists for injection
    missing_items.sort(key=lambda x: x.get('added_at', '0000-00-00'), reverse=True)
    unwatched_local_gaps.sort(key=lambda x: x.get('title', '').lower())
    continue_watching.sort(key=lambda x: x.get('title', '').lower())
    sagas_progress.sort(key=lambda x: x.get('title', '').lower())

    # Build JSON items
    missing_json = json.dumps(missing_items)
    unwatched_json = json.dumps(unwatched_local_gaps)
    continue_watching_json = json.dumps(continue_watching)
    sagas_progress_json = json.dumps(sagas_progress)
    ignored_json = json.dumps([t.lower() for t in ignored_shows])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Plex Watchlist & Media Hub Analyzer</title>
    <!-- Google Fonts Outfit -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #0d0e10;
            --surface-color: #16181b;
            --border-color: rgba(255, 255, 255, 0.05);
            --accent-color: #e5a93b;
            --accent-hover: #f0b84c;
            --text-primary: #ffffff;
            --text-secondary: #9e9fa5;
            --movie-badge: #0a84ff;
            --show-badge: #30d158;
            --missing-badge: #ff453a;
            --upcoming-badge: #ff9f0a;
            --card-bg-gradient: linear-gradient(135deg, rgba(255, 255, 255, 0.03) 0%, rgba(255, 255, 255, 0.01) 100%);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Outfit', sans-serif;
        }}

        body {{
            background-color: var(--bg-color);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 2rem;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(229, 169, 59, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(10, 132, 255, 0.03) 0%, transparent 40%);
            background-attachment: fixed;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        /* Header Styling */
        header {{
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1.5rem;
        }}

        .title-area h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #ffffff 30%, #a5a6b0 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}

        .title-area p {{
            color: var(--text-secondary);
            font-size: 1rem;
        }}

        .server-badge {{
            background: rgba(229, 169, 59, 0.1);
            color: var(--accent-color);
            padding: 0.4rem 0.8rem;
            border-radius: 50px;
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid rgba(229, 169, 59, 0.2);
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }}

        /* Navigation Tabs */
        .tabs-container {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1px;
            flex-wrap: wrap;
        }}

        .tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 1.1rem;
            font-weight: 600;
            padding: 0.8rem 1.2rem;
            cursor: pointer;
            position: relative;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            outline: none;
        }}

        .tab-btn:hover {{
            color: var(--text-primary);
        }}

        .tab-btn.active {{
            color: var(--accent-color);
        }}

        .tab-btn.active::after {{
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            width: 100%;
            height: 2px;
            background: var(--accent-color);
        }}

        .tab-count {{
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-secondary);
            padding: 0.1rem 0.6rem;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 700;
        }}

        .tab-btn.active .tab-count {{
            background: rgba(229, 169, 59, 0.15);
            color: var(--accent-color);
        }}

        /* Control Panel (Filters, Search) */
        .control-panel {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.2rem 1.5rem;
            margin-bottom: 2.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1.5rem;
            backdrop-filter: blur(10px);
            background-image: var(--card-bg-gradient);
        }}

        .search-box {{
            position: relative;
            flex: 1;
            min-width: 280px;
            max-width: 450px;
        }}

        .search-box input {{
            width: 100%;
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 0.8rem 1rem 0.8rem 2.5rem;
            color: var(--text-primary);
            font-size: 0.95rem;
            outline: none;
            transition: all 0.3s ease;
        }}

        .search-box input:focus {{
            border-color: var(--accent-color);
            box-shadow: 0 0 0 2px rgba(229, 169, 59, 0.15);
        }}

        .search-box svg {{
            position: absolute;
            left: 0.9rem;
            top: 50%;
            transform: translateY(-50%);
            fill: var(--text-secondary);
            width: 16px;
            height: 16px;
            pointer-events: none;
        }}

        .filter-groups {{
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
        }}

        .filter-group {{
            display: flex;
            background: rgba(0, 0, 0, 0.15);
            padding: 4px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        .filter-btn {{
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 0.5rem 1rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }}

        .filter-btn.active {{
            background: var(--accent-color);
            color: var(--bg-color);
            font-weight: 600;
        }}

        .sort-select {{
            background: rgba(0, 0, 0, 0.15);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.6rem 1rem;
            border-radius: 8px;
            outline: none;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 500;
        }}

        .sort-select:focus {{
            border-color: var(--accent-color);
        }}

        /* Grid */
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
            gap: 1.8rem;
        }}

        /* Card Item */
        .card {{
            background: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            backdrop-filter: blur(10px);
            background-image: var(--card-bg-gradient);
            position: relative;
        }}

        .card:hover {{
            transform: translateY(-8px);
            border-color: rgba(229, 169, 59, 0.3);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
        }}

        .poster-container {{
            aspect-ratio: 2/3;
            width: 100%;
            position: relative;
            background-color: rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}

        .poster {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s ease;
        }}

        .card:hover .poster {{
            transform: scale(1.05);
        }}

        /* Poster Fallback Style */
        .poster-fallback {{
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 1.5rem;
            text-align: center;
            background: linear-gradient(135deg, #1d2126 0%, #111215 100%);
            color: var(--text-secondary);
        }}

        .fallback-icon {{
            font-size: 2.5rem;
            margin-bottom: 0.8rem;
            opacity: 0.5;
        }}

        .fallback-text {{
            font-size: 0.95rem;
            font-weight: 500;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }}

        .type-badge {{
            position: absolute;
            top: 10px;
            right: 10px;
            padding: 0.3rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            backdrop-filter: blur(8px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }}

        .type-badge.movie {{
            background: rgba(10, 132, 255, 0.2);
            color: var(--movie-badge);
            border: 1px solid rgba(10, 132, 255, 0.3);
        }}

        .type-badge.show {{
            background: rgba(48, 209, 88, 0.2);
            color: var(--show-badge);
            border: 1px solid rgba(48, 209, 88, 0.3);
        }}

        .type-badge.saga {{
            background: rgba(229, 169, 59, 0.2);
            color: var(--accent-color);
            border: 1px solid rgba(229, 169, 59, 0.3);
        }}

        .card-body {{
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            flex: 1;
        }}

        .card-title {{
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 0.4rem;
            line-height: 1.3;
            color: var(--text-primary);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            height: 2.6rem;
        }}

        .card-meta {{
            display: flex;
            align-items: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 1rem;
            font-weight: 500;
        }}

        .card-meta .year {{
            color: var(--text-primary);
        }}

        .card-meta .dot {{
            margin: 0 0.4rem;
            opacity: 0.5;
        }}

        /* Progress Bar */
        .progress-container {{
            margin-bottom: 1.2rem;
            width: 100%;
        }}

        .progress-bar {{
            width: 100%;
            height: 5px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            overflow: hidden;
            margin-bottom: 0.4rem;
        }}

        .progress-fill {{
            height: 100%;
            background: var(--show-badge);
            border-radius: 10px;
            transition: width 0.3s ease;
        }}

        .progress-text {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            font-weight: 600;
        }}

        /* Status Tags */
        .status-badge {{
            font-size: 0.8rem;
            border-radius: 6px;
            padding: 0.25rem 0.5rem;
            align-self: flex-start;
            margin-bottom: 1.2rem;
            font-weight: 600;
            border: 1px solid transparent;
        }}

        .status-badge.available {{
            color: var(--show-badge);
            background: rgba(48, 209, 88, 0.1);
            border-color: rgba(48, 209, 88, 0.15);
        }}

        .status-badge.missing {{
            color: var(--missing-badge);
            background: rgba(255, 69, 58, 0.1);
            border-color: rgba(255, 69, 58, 0.15);
        }}

        .status-badge.upcoming {{
            color: var(--upcoming-badge);
            background: rgba(255, 159, 10, 0.1);
            border-color: rgba(255, 159, 10, 0.15);
        }}

        .status-badge.new_season_upcoming, .status-badge.new_season_missing {{
            color: var(--upcoming-badge);
            background: rgba(255, 159, 10, 0.1);
            border-color: rgba(255, 159, 10, 0.15);
        }}

        .status-badge.mid_season_upcoming {{
            color: #d087ff;
            background: rgba(208, 135, 255, 0.1);
            border-color: rgba(208, 135, 255, 0.15);
        }}

        .status-badge.caught_up {{
            color: var(--show-badge);
            background: rgba(48, 209, 88, 0.15);
            border-color: rgba(48, 209, 88, 0.2);
            font-weight: 700;
        }}

        .actions {{
            display: flex;
            gap: 0.4rem;
            margin-top: auto;
            flex-wrap: wrap;
        }}

        .btn {{
            flex: 1;
            padding: 0.6rem;
            border-radius: 8px;
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 600;
            text-align: center;
            transition: all 0.2s ease;
            white-space: nowrap;
        }}

        .btn-primary {{
            background: var(--accent-color);
            color: var(--bg-color);
        }}

        .btn-primary:hover {{
            background: var(--accent-hover);
        }}

        .btn-secondary {{
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }}

        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.1);
        }}

        .btn-ignore {{
            background: rgba(255, 69, 58, 0.05);
            color: var(--missing-badge);
            border: 1px solid rgba(255, 69, 58, 0.1);
            cursor: pointer;
        }}

        .btn-ignore:hover {{
            background: rgba(255, 69, 58, 0.15);
            color: #ff5b52;
            border-color: rgba(255, 69, 58, 0.25);
        }}

        .btn-queue {{
            background: rgba(255, 255, 255, 0.03);
            color: var(--text-secondary);
            border: 1px dashed var(--border-color);
            padding-left: 0.5rem;
            padding-right: 0.5rem;
            flex: 0 0 auto;
            width: auto;
        }}

        .btn-queue:hover {{
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
        }}

        .btn-queue.active {{
            background: rgba(229, 169, 59, 0.15);
            color: var(--accent-color);
            border: 1px solid rgba(229, 169, 59, 0.3);
        }}

        .btn-queue.active:hover {{
            background: rgba(229, 169, 59, 0.25);
        }}

        /* Empty State */
        .empty-state {{
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 5rem 2rem;
            background: var(--surface-color);
            border: 1px dashed var(--border-color);
            border-radius: 20px;
            grid-column: 1 / -1;
        }}

        .empty-icon {{
            font-size: 4rem;
            margin-bottom: 1rem;
            opacity: 0.5;
        }}

        .empty-state h3 {{
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }}

        .empty-state p {{
            color: var(--text-secondary);
            max-width: 400px;
        }}

        /* Scrollbar Styling */
        ::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}
        ::-webkit-scrollbar-track {{
            background: var(--bg-color);
        }}
        ::-webkit-scrollbar-thumb {{
            background: #2b2e33;
            border-radius: 10px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: #3e424a;
        }}

        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}
            header {{
                margin-bottom: 1.5rem;
            }}
            .title-area h1 {{
                font-size: 1.8rem;
            }}
            .control-panel {{
                flex-direction: column;
                align-items: stretch;
            }}
            .search-box {{
                max-width: 100%;
            }}
            .filter-groups {{
                flex-direction: column;
                align-items: stretch;
            }}
            .grid {{
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                gap: 1rem;
            }}
            .card-title {{
                font-size: 0.95rem;
                height: 2.4rem;
            }}
            .btn {{
                padding: 0.5rem;
                font-size: 0.8rem;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-area">
                <h1>Plex Media Hub</h1>
                <p>Track show release schedules, movie saga progress, and library sync gaps.</p>
            </div>
            <div>
                <div class="server-badge">
                    <svg style="width: 12px; height: 12px; fill: currentColor;" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
                    {server_name}
                </div>
            </div>
        </header>

        <!-- Navigation Tabs -->
        <nav class="tabs-container">
            <button class="tab-btn active" id="tab-continue" onclick="switchTab('continue')">
                📺 Continue Watching
                <span class="tab-count" id="badge-continue">{len(continue_watching)}</span>
            </button>
            <button class="tab-btn" id="tab-watchnext" onclick="switchTab('watchnext')">
                ★ Watch Next
                <span class="tab-count" id="badge-watchnext">0</span>
            </button>
            <button class="tab-btn" id="tab-unwatched" onclick="switchTab('unwatched')">
                📁 Unwatched Library
                <span class="tab-count" id="badge-unwatched">{len(unwatched_local_gaps)}</span>
            </button>
            <button class="tab-btn" id="tab-missing" onclick="switchTab('missing')">
                🍿 Watchlist Gaps
                <span class="tab-count" id="badge-missing">{len(missing_items)}</span>
            </button>
            <button class="tab-btn" id="tab-sagas" onclick="switchTab('sagas')">
                🏅 Saga Browser
                <span class="tab-count" id="badge-sagas">{len(sagas_progress)}</span>
            </button>
        </nav>

        <!-- Controls (Search/Filter/Sort) -->
        <section class="control-panel">
            <div class="search-box">
                <svg viewBox="0 0 24 24">
                    <path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
                </svg>
                <input type="text" id="search-input" placeholder="Search items..." oninput="filterAndRender()">
            </div>
            <div class="filter-groups">
                <div class="filter-group" id="media-filter-group">
                    <button class="filter-btn active" id="filter-all" onclick="setFilter('all')">All</button>
                    <button class="filter-btn" id="filter-movie" onclick="setFilter('movie')">Movies</button>
                    <button class="filter-btn" id="filter-show" onclick="setFilter('show')">TV Shows</button>
                </div>
                <select class="sort-select" id="sort-select" onchange="setSort(this.value)">
                    <option id="opt-added-desc" value="added-desc">Date Added (Newest First)</option>
                    <option id="opt-added-asc" value="added-asc">Date Added (Oldest First)</option>
                    <option value="title-asc">Title (A - Z)</option>
                    <option value="title-desc">Title (Z - A)</option>
                    <option value="year-desc">Release Year (Newest)</option>
                    <option value="year-asc">Release Year (Oldest)</option>
                    <option id="opt-progress-desc" value="progress-desc" style="display: none;">Watch Progress (Highest)</option>
                    <option id="opt-progress-asc" value="progress-asc" style="display: none;">Watch Progress (Lowest)</option>
                </select>
                <button class="btn btn-secondary" onclick="clearIgnored()" style="padding: 0.6rem 1rem; flex: 0;" title="Restore all shows ignored in the browser.">Reset Ignored</button>
            </div>
        </section>

        <!-- Items Grid -->
        <main class="grid" id="items-grid">
            <!-- Rendered dynamically via JS -->
        </main>

        <!-- Empty State -->
        <div class="empty-state" id="empty-state">
            <div class="empty-icon">🎉</div>
            <h3>All Caught Up!</h3>
            <p>No items found.</p>
        </div>
    </div>

    <!-- Data Injection -->
    <script>
        const continueWatching = {continue_watching_json};
        const missingItems = {missing_json};
        const unwatchedItems = {unwatched_json};
        const sagasProgress = {sagas_progress_json};
        const ignoredBackend = {ignored_json};
        
        let activeTab = 'continue';
        let currentFilter = 'all';
        let currentSort = 'title-asc';

        // Load lists from localStorage
        let localQueue = JSON.parse(localStorage.getItem('plex_watch_next') || '[]');
        let localIgnored = JSON.parse(localStorage.getItem('plex_ignored_shows') || '[]');

        function isItemInQueue(item) {{
            return item.watch_next || localQueue.includes(item.ratingKey) || localQueue.includes(item.title);
        }}

        function isShowIgnored(item) {{
            if (item.type !== 'show') return false;
            const normTitle = item.title.toLowerCase();
            return ignoredBackend.includes(normTitle) || localIgnored.includes(normTitle) || localIgnored.includes(item.ratingKey);
        }}

        function ignoreShow(ratingKey, title) {{
            const key = (ratingKey && ratingKey !== 'undefined') ? ratingKey : title.toLowerCase();
            if (!localIgnored.includes(key)) {{
                localIgnored.push(key);
                localStorage.setItem('plex_ignored_shows', JSON.stringify(localIgnored));
            }}
            updateCounts();
            filterAndRender();
        }}

        function clearIgnored() {{
            localIgnored = [];
            localStorage.removeItem('plex_ignored_shows');
            updateCounts();
            filterAndRender();
        }}

        function toggleQueue(ratingKey, title) {{
            const key = ratingKey || title;
            const idx = localQueue.indexOf(key);
            if (idx > -1) {{
                localQueue.splice(idx, 1);
            }} else {{
                localQueue.push(key);
            }}
            localStorage.setItem('plex_watch_next', JSON.stringify(localQueue));
            
            updateCounts();
            filterAndRender();
        }}

        function updateCounts() {{
            // Recount after ignores & stars
            const visibleContinue = continueWatching.filter(item => !isShowIgnored(item));
            document.getElementById('badge-continue').textContent = visibleContinue.length;

            const allUnwatched = [...unwatchedItems, ...missingItems].filter(item => !isShowIgnored(item));
            const watchNextItems = allUnwatched.filter(item => isItemInQueue(item));
            document.getElementById('badge-watchnext').textContent = watchNextItems.length;

            const visibleUnwatched = unwatchedItems.filter(item => !isShowIgnored(item));
            document.getElementById('badge-unwatched').textContent = visibleUnwatched.length;

            const visibleMissing = missingItems.filter(item => !isShowIgnored(item));
            document.getElementById('badge-missing').textContent = visibleMissing.length;
        }}

        function switchTab(tab) {{
            activeTab = tab;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            
            const sortSelect = document.getElementById('sort-select');
            const mediaFilterGroup = document.getElementById('media-filter-group');
            
            // Adjust sorting filters and media filters based on tab type
            if (activeTab === 'sagas') {{
                mediaFilterGroup.style.display = 'none'; // Sagas tab has no TV show filter
                document.getElementById('opt-added-desc').style.display = 'none';
                document.getElementById('opt-added-asc').style.display = 'none';
                document.getElementById('opt-progress-desc').style.display = 'block';
                document.getElementById('opt-progress-asc').style.display = 'block';
                
                if (currentSort.startsWith('added')) {{
                    currentSort = 'progress-desc';
                    sortSelect.value = 'progress-desc';
                }}
            }} else if (activeTab === 'continue') {{
                mediaFilterGroup.style.display = 'flex';
                document.getElementById('opt-added-desc').style.display = 'none';
                document.getElementById('opt-added-asc').style.display = 'none';
                document.getElementById('opt-progress-desc').style.display = 'block';
                document.getElementById('opt-progress-asc').style.display = 'block';
                
                if (currentSort.startsWith('added')) {{
                    currentSort = 'title-asc';
                    sortSelect.value = 'title-asc';
                }}
            }} else if (activeTab === 'unwatched' || activeTab === 'watchnext') {{
                mediaFilterGroup.style.display = 'flex';
                document.getElementById('opt-added-desc').style.display = 'none';
                document.getElementById('opt-added-asc').style.display = 'none';
                document.getElementById('opt-progress-desc').style.display = 'none';
                document.getElementById('opt-progress-asc').style.display = 'none';
                
                if (currentSort.startsWith('added') || currentSort.startsWith('progress')) {{
                    currentSort = 'title-asc';
                    sortSelect.value = 'title-asc';
                }}
            }} else {{
                // Missing watchlist gaps
                mediaFilterGroup.style.display = 'flex';
                document.getElementById('opt-added-desc').style.display = 'block';
                document.getElementById('opt-added-asc').style.display = 'block';
                document.getElementById('opt-progress-desc').style.display = 'none';
                document.getElementById('opt-progress-asc').style.display = 'none';
                
                if (currentSort.startsWith('progress')) {{
                    currentSort = 'added-desc';
                    sortSelect.value = 'added-desc';
                }}
            }}
            
            filterAndRender();
        }}

        function setFilter(filter) {{
            currentFilter = filter;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('filter-' + filter).classList.add('active');
            filterAndRender();
        }}

        function setSort(sortVal) {{
            currentSort = sortVal;
            filterAndRender();
        }}

        function filterAndRender() {{
            const searchVal = document.getElementById('search-input').value.toLowerCase().trim();
            const grid = document.getElementById('items-grid');
            const emptyState = document.getElementById('empty-state');

            let sourceList = [];
            if (activeTab === 'continue') sourceList = continueWatching;
            else if (activeTab === 'missing') sourceList = missingItems;
            else if (activeTab === 'unwatched') sourceList = unwatchedItems;
            else if (activeTab === 'sagas') sourceList = sagasProgress;
            else if (activeTab === 'watchnext') {{
                const allUnwatched = [...unwatchedItems, ...missingItems];
                sourceList = allUnwatched.filter(item => isItemInQueue(item));
            }}

            // 1. Filter
            let filtered = sourceList.filter(item => {{
                // Filter out ignored shows
                if (isShowIgnored(item)) return false;

                // Media Type Filter (applicable to everything except Sagas tab)
                if (activeTab !== 'sagas' && currentFilter !== 'all') {{
                    if (currentFilter === 'movie' && item.type === 'show') return false;
                    if (currentFilter === 'show' && (item.type === 'movie' || item.type === 'saga')) return false;
                }}
                
                // Search Filter
                if (searchVal) {{
                    const titleMatch = item.title.toLowerCase().includes(searchVal);
                    const yearMatch = item.year && item.year.toString().includes(searchVal);
                    return titleMatch || yearMatch;
                }}
                return true;
            }});

            // 2. Sort
            filtered.sort((a, b) => {{
                if (currentSort === 'title-asc') {{
                    return a.title.localeCompare(b.title);
                }} else if (currentSort === 'title-desc') {{
                    return b.title.localeCompare(a.title);
                }} else if (currentSort === 'year-desc') {{
                    const yrA = a.year || (a.next_movie ? a.next_movie.year : 0);
                    const yrB = b.year || (b.next_movie ? b.next_movie.year : 0);
                    return yrB - yrA;
                }} else if (currentSort === 'year-asc') {{
                    const yrA = a.year || (a.next_movie ? a.next_movie.year : 0);
                    const yrB = b.year || (b.next_movie ? b.next_movie.year : 0);
                    return yrA - yrB;
                }} else if (currentSort === 'added-desc') {{
                    return (b.added_at || '').localeCompare(a.added_at || '');
                }} else if (currentSort === 'added-asc') {{
                    return (a.added_at || '').localeCompare(b.added_at || '');
                }} else if (currentSort === 'progress-desc') {{
                    const progA = a.total_episodes || a.total_movies ? ((a.viewed_episodes || a.watched_movies || 0) / (a.total_episodes || a.total_movies || 1)) : 0;
                    const progB = b.total_episodes || b.total_movies ? ((b.viewed_episodes || b.watched_movies || 0) / (b.total_episodes || b.total_movies || 1)) : 0;
                    return progB - progA;
                }} else if (currentSort === 'progress-asc') {{
                    const progA = a.total_episodes || a.total_movies ? ((a.viewed_episodes || a.watched_movies || 0) / (a.total_episodes || a.total_movies || 1)) : 0;
                    const progB = b.total_episodes || b.total_movies ? ((b.viewed_episodes || b.watched_movies || 0) / (b.total_episodes || b.total_movies || 1)) : 0;
                    return progA - progB;
                }}
                return 0;
            }});

            // 3. Render
            grid.innerHTML = '';
            
            if (filtered.length === 0) {{
                emptyState.style.display = 'flex';
                if (searchVal) {{
                    emptyState.querySelector('h3').textContent = 'No Matches Found';
                    emptyState.querySelector('p').textContent = 'Try adjusting your search query.';
                }} else {{
                    emptyState.querySelector('h3').textContent = 'No Items';
                    if (activeTab === 'continue') emptyState.querySelector('p').textContent = 'You have no TV shows or Sagas in progress right now.';
                    else if (activeTab === 'missing') emptyState.querySelector('p').textContent = 'Everything in your watchlist is present on the server!';
                    else if (activeTab === 'unwatched') emptyState.querySelector('p').textContent = 'No unwatched gaps found.';
                    else if (activeTab === 'sagas') emptyState.querySelector('p').textContent = 'No Sagas loaded.';
                    else if (activeTab === 'watchnext') emptyState.querySelector('p').textContent = 'Your Watch Next queue is empty. Pin items in the Unwatched or Gaps tabs!';
                }}
            }} else {{
                emptyState.style.display = 'none';
                filtered.forEach(item => {{
                    const card = document.createElement('div');
                    card.className = 'card';

                    let typeLabel = '';
                    if (item.type === 'movie') typeLabel = 'Movie';
                    else if (item.type === 'show') typeLabel = 'TV Show';
                    else if (item.type === 'saga') typeLabel = 'Movie Saga';
                    else typeLabel = 'Saga';

                    let primaryLink = '#';
                    let primaryBtnText = 'View';
                    let metaInfoHTML = '';
                    let badgeClass = item.type;
                    let showQueueBtn = false;
                    let showIgnoreBtn = false;
                    
                    // Render styling depending on Tab
                    if (activeTab === 'continue') {{
                        const isSaga = item.type === 'saga';
                        badgeClass = item.status;
                        
                        if (isSaga) {{
                            const percentage = Math.round((item.viewed_episodes / item.total_episodes) * 100);
                            
                            primaryLink = item.plex_link;
                            primaryBtnText = item.status === 'available' ? 'Watch Now' : 'Plex Info';

                            metaInfoHTML = `
                                <div class="card-meta">
                                    <span class="year">Next Film</span>
                                </div>
                                <div class="progress-container">
                                    <div class="progress-bar">
                                        <div class="progress-fill" style="width: ${{percentage}}%;"></div>
                                    </div>
                                    <span class="progress-text">Saga Progress: ${{item.viewed_episodes}} of ${{item.total_episodes}} films watched (${{percentage}}%)</span>
                                </div>
                                <div class="status-badge ${{item.status}}">${{item.status_label}}</div>
                            `;
                        }} else {{
                            // TV Show Continue Watching
                            showIgnoreBtn = true;
                            const percentage = Math.round((item.viewed_episodes / item.total_episodes) * 100);
                            
                            primaryLink = item.plex_link || `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${{item.next_episode ? item.next_episode.ratingKey || item.next_episode.title : ''}}`;
                            primaryBtnText = item.status === 'available' ? 'Play S' + item.next_episode.season + 'E' + item.next_episode.episode : 'Info';

                            const epTitle = item.next_episode ? `"${{item.next_episode.title}}"` : 'TBA';
                            metaInfoHTML = `
                                <div class="card-meta">
                                    <span class="year">${{epTitle}}</span>
                                </div>
                                <div class="progress-container">
                                    <div class="progress-bar">
                                        <div class="progress-fill" style="width: ${{percentage}}%;"></div>
                                    </div>
                                    <span class="progress-text">${{item.viewed_episodes}} of ${{item.total_episodes}} episodes watched (${{percentage}}%)</span>
                                </div>
                                <div class="status-badge ${{item.status}}">${{item.status_label}}</div>
                            `;
                        }}
                    }} else if (activeTab === 'missing' || activeTab === 'watchnext' || activeTab === 'unwatched') {{
                        showQueueBtn = true;
                        if (item.type === 'show') showIgnoreBtn = true;

                        if (activeTab === 'missing') {{
                            primaryLink = `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${{item.ratingKey}}`;
                            primaryBtnText = 'Plex Info';
                            
                            metaInfoHTML = `
                                <div class="card-meta">
                                    <span class="year">${{item.year || 'N/A'}}</span>
                                    <span class="dot">•</span>
                                    <span class="added-date">Added ${{item.added_at}}</span>
                                </div>
                                <div class="status-badge missing">Missing from server</div>
                            `;
                        }} else {{
                            primaryLink = item.plex_link || `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${{item.ratingKey}}`;
                            primaryBtnText = item.plex_link ? 'Watch Now' : 'Plex Info';

                            if (item.type === 'movie') {{
                                metaInfoHTML = `
                                    <div class="card-meta">
                                        <span class="year">${{item.year || 'N/A'}}</span>
                                    </div>
                                    <div class="status-badge available">Unwatched Movie</div>
                                `;
                            }} else {{
                                const percentage = Math.round((item.viewed_episodes / item.total_episodes) * 100);
                                metaInfoHTML = `
                                    <div class="card-meta">
                                        <span class="year">${{item.year || 'N/A'}}</span>
                                    </div>
                                    <div class="progress-container">
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: ${{percentage}}%;"></div>
                                        </div>
                                        <span class="progress-text">${{item.viewed_episodes}} of ${{item.total_episodes}} episodes watched (${{percentage}}%)</span>
                                    </div>
                                `;
                            }}
                        }}
                    }} else if (activeTab === 'sagas') {{
                        const isComp = item.next_movie_status === 'completed';
                        badgeClass = item.next_movie_status;
                        
                        primaryLink = '#';
                        primaryBtnText = 'Progress';

                        metaInfoHTML = `
                            <div class="card-meta">
                                <span class="year">Chronological order</span>
                            </div>
                            <div class="progress-container">
                                <div class="progress-bar">
                                    <div class="progress-fill" style="width: ${{item.percentage}}%;"></div>
                                </div>
                                <span class="progress-text">${{item.watched_movies}} of ${{item.total_movies}} movies watched (${{item.percentage}}%)</span>
                            </div>
                            <div class="status-badge ${{item.next_movie_status}}">
                                ${{isComp ? 'Collection Completed' : `Next: ${{item.next_movie}} (${{item.next_movie_status}})`}}
                            </div>
                        `;
                    }}

                    const gradients = [
                        'linear-gradient(135deg, #2b3a4a 0%, #0f171e 100%)',
                        'linear-gradient(135deg, #3a2b4a 0%, #170f1e 100%)',
                        'linear-gradient(135deg, #2b4a3a 0%, #0f1e17 100%)',
                        'linear-gradient(135deg, #4a3e2b 0%, #1e170f 100%)'
                    ];
                    const grad = gradients[Math.abs(item.title.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % gradients.length];
                    const inQueue = isItemInQueue(item);

                    // Choose discover link or ignore button for the secondary action
                    let secondaryActionHTML = '';
                    if (showIgnoreBtn) {{
                        secondaryActionHTML = `<button class="btn btn-ignore" onclick="ignoreShow('${{item.ratingKey}}', '${{item.title.replace(/'/g, "\\'")}}')">Ignore</button>`;
                    }} else {{
                        const discLink = `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${{item.guid ? item.guid.split('/').pop() : ''}}`;
                        secondaryActionHTML = `<a href="${{discLink}}" target="_blank" class="btn btn-secondary">Discover</a>`;
                    }}

                    card.innerHTML = `
                        <div class="poster-container">
                            ${{item.poster_url ? `
                                <img class="poster" src="${{item.poster_url}}" alt="${{item.title}}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                            ` : ''}}
                            <div class="poster-fallback" style="${{item.poster_url ? 'display: none;' : 'display: flex;'}} background: ${{grad}};">
                                <div class="fallback-icon">${{item.type === 'movie' ? '🎬' : (item.type === 'show' ? '📺' : '🏅')}}</div>
                                <div class="fallback-text">${{item.title}}</div>
                            </div>
                            <div class="type-badge ${{badgeClass}}">${{typeLabel}}</div>
                        </div>
                        <div class="card-body">
                            <h3 class="card-title" title="${{item.title}}">${{item.title}}</h3>
                            ${{metaInfoHTML}}
                            <div class="actions">
                                ${{activeTab !== 'sagas' ? `<a href="${{primaryLink}}" target="_blank" class="btn btn-primary">${{primaryBtnText}}</a>` : ''}}
                                ${{showQueueBtn ? `
                                    <button class="btn btn-queue ${{inQueue ? 'active' : ''}}" onclick="toggleQueue('${{item.ratingKey}}', '${{item.title.replace(/'/g, "\\'")}}'')" title="${{inQueue ? 'Remove from Queue' : 'Add to Watch Next'}}">
                                        ${{inQueue ? '★' : '☆'}}
                                    </button>
                                ` : ''}}
                                ${{secondaryActionHTML}}
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                }});
            }}
        }}

        // Initial setup
        updateCounts();
        switchTab('continue');
    </script>
</body>
</html>
"""

    with open(html_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nHTML dashboard generated successfully at: {html_file_path}")
    return html_file_path

def main():
    parser = argparse.ArgumentParser(description="Plex Media Hub gap and continue watching analyzer.")
    parser.add_argument("--reauth", action="store_true", help="Force re-authentication with Plex.")
    parser.add_argument("--server", type=str, help="Specific Plex server name to connect to.")
    parser.add_argument("--type", type=str, choices=['movie', 'show'], help="Filter checking to only 'movie' or 'show'.")
    args = parser.parse_args()

    print("="*60)
    print("                 PLEX MEDIA HUB ANALYZER")
    print("="*60)

    # 1. Authenticate with Plex
    account = authenticate_plex(force_login=args.reauth)

    # 2. Select server
    server_resource = select_server(account, target_server_name=args.server)

    # 3. Load Watch Next queue config
    watch_next_titles = load_watch_next()

    # 4. Load Ignored Shows config
    ignored_shows = load_ignored_shows()
    ignored_shows_norm = {normalize_title(t) for t in ignored_shows}

    # 5. Fetch local libraries (GUIDs, Titles, Unwatched and In-Progress)
    local_guids, local_titles, unwatched_local_items, in_progress_shows, machine_id = build_local_library_index(server_resource, watch_next_titles, ignored_shows_norm)

    # 6. Fetch Watchlist
    watchlist = fetch_watchlist(account, libtype=args.type)

    # Identify in-progress shows from the watchlist that are not in local library and not ignored
    local_in_progress_titles = {normalize_title(s['title']) for s in in_progress_shows}
    for item in watchlist:
        if item.type == 'show':
            viewed_episodes = getattr(item, 'viewedLeafCount', 0)
            total_episodes = getattr(item, 'leafCount', 0)
            if viewed_episodes > 0:
                norm_title = normalize_title(item.title)
                if norm_title not in local_in_progress_titles and norm_title not in ignored_shows_norm:
                    poster_url = ""
                    if hasattr(item, 'thumb') and item.thumb:
                        if item.thumb.startswith('http'):
                            poster_url = item.thumb
                        elif item.thumb.startswith('/'):
                            poster_url = f"https://metadata.provider.plex.tv{item.thumb}"
                    elif hasattr(item, 'thumbUrl') and item.thumbUrl:
                        poster_url = item.thumbUrl

                    rating_key = item.guid.rsplit('/', 1)[-1] if item.guid else ""
                    
                    in_progress_shows.append({
                        'title': item.title,
                        'last_watched': None,
                        'next_ep_local': None,
                        'viewed_episodes': viewed_episodes,
                        'total_episodes': total_episodes,
                        'ratingKey': rating_key,
                        'guid': item.guid,
                        'poster_url': poster_url,
                        'is_watchlist_only': True
                    })
                    local_in_progress_titles.add(norm_title)

    # 7. Cross-reference Watchlist -> Local Library (Finds Missing items)
    missing_items, total_watchlist = check_watchlist(watchlist, local_guids, local_titles, watch_next_titles)

    # 8. Index Watchlist & Cross-reference Local -> Watchlist (Finds Unwatched not in Watchlist)
    wl_guids, wl_titles = index_watchlist(watchlist)
    unwatched_local_gaps = check_unwatched_not_watchlist(unwatched_local_items, wl_guids, wl_titles, machine_id)

    # 9. Trace TV Show next episode schedules via TVmaze API
    tv_schedules = calculate_tv_show_schedules(in_progress_shows, machine_id)

    # 10. Calculate Movie Sagas watch progress
    active_sagas, sagas_progress = calculate_movie_sagas(local_titles, machine_id)

    # Combine TV Shows + Movie Sagas into Continue Watching list
    continue_watching = tv_schedules + active_sagas

    # 11. Print Console Summary
    print("\n" + "="*60)
    print("                    ANALYSIS SUMMARY")
    print("="*60)
    print(f"Server Name:           {server_resource.name}")
    print(f"Total Watchlist Items: {total_watchlist}")
    print(f"Continue Watching:     {len(continue_watching)} active items")
    print(f"Missing from Server:   {len(missing_items)}")
    print(f"Unwatched Local Gaps:  {len(unwatched_local_gaps)}")
    print(f"Tracked Movie Sagas:   {len(sagas_progress)}")
    print("="*60)

    # 12. Generate and open HTML Dashboard
    html_path = generate_html_report(missing_items, unwatched_local_gaps, continue_watching, sagas_progress, ignored_shows, server_resource.name)
    
    # Auto-open HTML page if not in Docker
    if not os.path.exists('/.dockerenv'):
        try:
            print("\nOpening dashboard in web browser...")
            webbrowser.open(f"file://{html_path}")
        except Exception as e:
            print(f"Could not open web browser automatically: {e}")
            print(f"Please open the report manually: file://{html_path}")
    else:
        print("\nRunning inside Docker container.")
        print("Please open the generated 'missing_watchlist.html' file from your workspace directory in your browser.")

    print("\nDone!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
