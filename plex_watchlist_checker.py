#!/usr/bin/env python3
"""
Plex Watchlist Checker
Identifies items on your Plex Watchlist that are missing from your Plex Server.
Also identifies unwatched items on your server that are not on your watchlist.
Generates an interactive, modern HTML dashboard.
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
from urllib.parse import quote

try:
    from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
except ImportError:
    print("Error: The 'plexapi' package is not installed.")
    print("Please install it using: pip install plexapi")
    sys.exit(1)

# Configuration File Path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".plex_config.json")

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

    # Automatically try to open the browser for the user
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
            # Ignore transient API errors before linking
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

    # Determine server to use
    selected = None

    if target_server_name:
        # User specified a server on the command line
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
        # Check if saved server is still in the list
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

    # Save choice
    config["server_name"] = selected.name
    save_config(config)
    return selected

def normalize_title(title):
    """Normalizes title for fallback fuzzy matching (accents, cases, punctuation)."""
    if not title:
        return ""
    # Lowercase
    title = title.lower()
    # Normalize unicode (accents)
    title = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('utf-8')
    # Keep only alphanumeric characters and spaces
    title = re.sub(r'[^a-z0-9\s]', '', title)
    # Remove extra whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def build_local_library_index(plex_server):
    """Fetches local server library, indexes items by GUID and title/year, and finds unwatched items."""
    print(f"\nConnecting to Plex Server: {plex_server.name}...")
    try:
        plex = plex_server.connect()
        print(f"Connected to: {plex.friendlyName}")
    except Exception as e:
        print(f"Error: Failed to connect to server: {e}")
        sys.exit(1)

    machine_id = plex.machineIdentifier
    local_guids = set()
    local_titles = {} # Maps normalized_title -> list of (item_type, year)
    unwatched_local_items = []
    
    print("Scanning server library sections (Movies & TV Shows)...")
    for section in plex.library.sections():
        if section.type in ['movie', 'show']:
            print(f"  Scanning section: '{section.title}' ({section.type})...")
            try:
                # includeGuids=1 is passed through to get alternate IDs (IMDb, TMDB, TVDB)
                items = section.all(includeGuids=1)
                print(f"    Indexed {len(items)} items.")
                for item in items:
                    # 1. Primary GUID
                    if item.guid:
                        local_guids.add(item.guid.lower())
                    
                    # 2. Alternate GUIDs (IMDb, TMDB, TVDB)
                    if hasattr(item, 'guids') and item.guids:
                        for g in item.guids:
                            if g.id:
                                local_guids.add(g.id.lower())
                    
                    # 3. Add to title index for fuzzy fallback
                    norm_title = normalize_title(item.title)
                    if norm_title:
                        if norm_title not in local_titles:
                            local_titles[norm_title] = []
                        local_titles[norm_title].append({
                            'type': item.type,
                            'year': item.year if hasattr(item, 'year') else None
                        })
                    
                    # 4. Check if unwatched
                    is_unwatched = False
                    viewed_episodes = 0
                    total_episodes = 0
                    
                    if item.type == 'movie':
                        is_unwatched = not getattr(item, 'isPlayed', False) and getattr(item, 'viewCount', 0) == 0
                    elif item.type == 'show':
                        unwatched_count = getattr(item, 'unwatchedLeafCount', 0)
                        total_episodes = getattr(item, 'leafCount', 0)
                        viewed_episodes = getattr(item, 'viewedLeafCount', 0)
                        is_unwatched = unwatched_count > 0
                        
                    if is_unwatched:
                        poster_url = ""
                        try:
                            # Retrieves fully-authenticated URL for host machine display
                            poster_url = item.thumbUrl
                        except Exception:
                            pass
                            
                        unwatched_local_items.append({
                            'title': item.title,
                            'year': item.year if hasattr(item, 'year') else None,
                            'type': item.type,
                            'ratingKey': item.ratingKey,
                            'guid': item.guid,
                            'viewed_episodes': viewed_episodes,
                            'total_episodes': total_episodes,
                            'poster_url': poster_url
                        })
            except Exception as e:
                print(f"    Warning: Failed to scan section '{section.title}': {e}")
                
    return local_guids, local_titles, unwatched_local_items, machine_id

def fetch_watchlist(account, libtype=None):
    """Fetches items from the user's Plex Watchlist."""
    print("\nFetching your Plex Watchlist...")
    try:
        # Fetch up to 5000 items (the max results parameter)
        watchlist_items = account.watchlist(maxresults=5000)
        
        # Apply type filter if requested
        if libtype:
            watchlist_items = [i for i in watchlist_items if i.type == libtype]
            
        print(f"Retrieved {len(watchlist_items)} watchlist items.")
        return watchlist_items
    except Exception as e:
        print(f"Error fetching watchlist: {e}")
        sys.exit(1)

def check_watchlist(watchlist, local_guids, local_titles):
    """Compares watchlist items against the indexed local server libraries (Finds Missing Items)."""
    print("\nComparing Watchlist against Plex Server...")
    missing_items = []
    total_checked = 0
    matched_count = 0

    for item in watchlist:
        total_checked += 1
        is_matched = False
        
        # Match Layer 1: Plex GUID check (case-insensitive)
        if item.guid and item.guid.lower() in local_guids:
            is_matched = True
            
        # Match Layer 2: Alternate GUID check
        if not is_matched and item.guid:
            guid_cleaned = item.guid.lower()
            if guid_cleaned in local_guids:
                is_matched = True
                
        # Match Layer 3: Fuzzy Fallback matching via Title + Year
        if not is_matched:
            norm_title = normalize_title(item.title)
            if norm_title in local_titles:
                for candidate in local_titles[norm_title]:
                    # Match type
                    candidate_type = candidate['type']
                    item_type = item.type
                    type_match = (
                        candidate_type == item_type or
                        (candidate_type in ['show', 'tv'] and item_type in ['show', 'tv'])
                    )
                    
                    if type_match:
                        if item_type == 'movie':
                            # Year check with 1-year tolerance
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
            
            # Retrieve date watchlisted
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

            # Try to build clean poster URL
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
                'poster_url': poster_url
            })

    return missing_items, total_checked

def index_watchlist(watchlist):
    """Indexes watchlist items by GUID and normalized Title + Year for reverse matching."""
    wl_guids = set()
    wl_titles = {} # Maps normalized_title -> list of (item_type, year)
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
    """Finds unwatched server items that are NOT present in the watchlist."""
    print("Finding unwatched server items not in watchlist...")
    unwatched_not_watchlist = []
    
    for item in unwatched_local_items:
        is_in_watchlist = False
        
        # Match Layer 1: GUID check (case-insensitive)
        if item['guid'] and item['guid'].lower() in wl_guids:
            is_in_watchlist = True
            
        # Match Layer 2: Fuzzy fallback matching via Title + Year
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
                            # Year check with 1-year tolerance
                            if candidate['year'] and item['year'] and abs(candidate['year'] - item['year']) <= 1:
                                is_in_watchlist = True
                                break
                        else:
                            is_in_watchlist = True
                            break
                            
        if not is_in_watchlist:
            # Build local server link to view/play item on Plex Web
            local_link = f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{item['ratingKey']}"
            
            unwatched_not_watchlist.append({
                'title': item['title'],
                'year': item['year'],
                'type': item['type'],
                'ratingKey': item['ratingKey'],
                'guid': item['guid'],
                'viewed_episodes': item['viewed_episodes'],
                'total_episodes': item['total_episodes'],
                'poster_url': item['poster_url'],
                'plex_link': local_link
            })
            
    print(f"Unwatched check completed: found {len(unwatched_not_watchlist)} unwatched items not in watchlist.")
    return unwatched_not_watchlist

def generate_html_report(missing_items, unwatched_not_watchlist, total_watchlist_count, server_name):
    """Generates a premium glassmorphism dark-mode HTML report with tabbed views."""
    html_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "missing_watchlist.html")
    
    # Pre-sort lists for injection
    missing_items.sort(key=lambda x: x.get('added_at', '0000-00-00'), reverse=True)
    unwatched_not_watchlist.sort(key=lambda x: x.get('title', '').lower())

    # Build JSON items
    missing_json = json.dumps(missing_items)
    unwatched_json = json.dumps(unwatched_not_watchlist)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Plex Watchlist & Library GAP Analyzer</title>
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

        /* Tabs Navigation */
        .tabs-container {{
            display: flex;
            gap: 1rem;
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
            gap: 1.5rem;
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

        /* Progress Bar for TV Shows */
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

        .unwatched-label {{
            font-size: 0.8rem;
            color: var(--accent-color);
            background: rgba(229, 169, 59, 0.1);
            border: 1px solid rgba(229, 169, 59, 0.15);
            border-radius: 6px;
            padding: 0.2rem 0.5rem;
            align-self: flex-start;
            margin-bottom: 1.2rem;
            font-weight: 600;
        }}

        .actions {{
            display: flex;
            gap: 0.6rem;
            margin-top: auto;
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
                <h1>Plex GAP Analyzer</h1>
                <p>Verify watchlist availability and discover unwatched files missing from your tracker.</p>
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
            <button class="tab-btn active" id="tab-missing" onclick="switchTab('missing')">
                Missing from Server
                <span class="tab-count" id="badge-missing">{len(missing_items)}</span>
            </button>
            <button class="tab-btn" id="tab-unwatched" onclick="switchTab('unwatched')">
                Unwatched & Not Watchlisted
                <span class="tab-count" id="badge-unwatched">{len(unwatched_not_watchlist)}</span>
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
                <div class="filter-group">
                    <button class="filter-btn active" id="filter-all" onclick="setFilter('all')">All</button>
                    <button class="filter-btn" id="filter-movie" onclick="setFilter('movie')">Movies</button>
                    <button class="filter-btn" id="filter-show" onclick="setFilter('show')">TV Shows</button>
                </div>
                <select class="sort-select" id="sort-select" onchange="setSort(this.value)">
                    <!-- Options populated/toggled dynamically in JS based on active tab -->
                    <option id="opt-added-desc" value="added-desc">Date Added (Newest First)</option>
                    <option id="opt-added-asc" value="added-asc">Date Added (Oldest First)</option>
                    <option value="title-asc">Title (A - Z)</option>
                    <option value="title-desc">Title (Z - A)</option>
                    <option value="year-desc">Release Year (Newest)</option>
                    <option value="year-asc">Release Year (Oldest)</option>
                    <option id="opt-progress-desc" value="progress-desc" style="display: none;">Watch Progress (Highest)</option>
                    <option id="opt-progress-asc" value="progress-asc" style="display: none;">Watch Progress (Lowest)</option>
                </select>
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
            <p>No gap items found.</p>
        </div>
    </div>

    <!-- Data Injection -->
    <script>
        const missingItems = {missing_json};
        const unwatchedItems = {unwatched_json};
        
        let activeTab = 'missing';
        let currentFilter = 'all';
        let currentSort = 'added-desc';

        function switchTab(tab) {{
            activeTab = tab;
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.getElementById('tab-' + tab).classList.add('active');
            
            const sortSelect = document.getElementById('sort-select');
            
            // Adjust sorting filters based on active tab
            if (activeTab === 'unwatched') {{
                document.getElementById('opt-added-desc').style.display = 'none';
                document.getElementById('opt-added-asc').style.display = 'none';
                document.getElementById('opt-progress-desc').style.display = 'block';
                document.getElementById('opt-progress-asc').style.display = 'block';
                
                if (currentSort.startsWith('added')) {{
                    currentSort = 'title-asc';
                    sortSelect.value = 'title-asc';
                }}
            }} else {{
                document.getElementById('opt-added-desc').style.display = 'block';
                document.getElementById('opt-added-asc').style.display = 'block';
                document.getElementById('opt-progress-desc').style.display = 'none';
                document.getElementById('opt-progress-asc').style.display = 'none';
                
                if (currentSort.startsWith('progress')) {{
                    currentSort = 'title-asc';
                    sortSelect.value = 'title-asc';
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

            const sourceList = activeTab === 'missing' ? missingItems : unwatchedItems;

            // 1. Filter
            let filtered = sourceList.filter(item => {{
                // Type Filter
                if (currentFilter !== 'all' && item.type !== currentFilter) return false;
                
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
                    return (b.year || 0) - (a.year || 0);
                }} else if (currentSort === 'year-asc') {{
                    return (a.year || 0) - (b.year || 0);
                }} else if (currentSort === 'added-desc') {{
                    return b.added_at.localeCompare(a.added_at);
                }} else if (currentSort === 'added-asc') {{
                    return a.added_at.localeCompare(b.added_at);
                }} else if (currentSort === 'progress-desc') {{
                    const progA = a.total_episodes ? (a.viewed_episodes / a.total_episodes) : 0;
                    const progB = b.total_episodes ? (b.viewed_episodes / b.total_episodes) : 0;
                    return progB - progA;
                }} else if (currentSort === 'progress-asc') {{
                    const progA = a.total_episodes ? (a.viewed_episodes / a.total_episodes) : 0;
                    const progB = b.total_episodes ? (b.viewed_episodes / b.total_episodes) : 0;
                    return progA - progB;
                }}
                return 0;
            }});

            // 3. Render
            grid.innerHTML = '';
            
            if (filtered.length === 0) {{
                emptyState.style.display = 'flex';
                if (searchVal || currentFilter !== 'all') {{
                    emptyState.querySelector('h3').textContent = 'No Matches Found';
                    emptyState.querySelector('p').textContent = 'Try adjusting your search or filters.';
                }} else {{
                    if (activeTab === 'missing') {{
                        emptyState.querySelector('h3').textContent = 'All Caught Up!';
                        emptyState.querySelector('p').textContent = 'No missing items found. Everything in your watchlist is available on your Plex server.';
                    }} else {{
                        emptyState.querySelector('h3').textContent = 'No Local Gaps Found';
                        emptyState.querySelector('p').textContent = 'All unwatched media files on your local server are already tracked in your Plex Watchlist.';
                    }}
                }}
            }} else {{
                emptyState.style.display = 'none';
                filtered.forEach(item => {{
                    const card = document.createElement('div');
                    card.className = 'card';

                    const typeLabel = item.type === 'movie' ? 'Movie' : 'TV Show';
                    
                    // Links definition based on tab
                    let primaryLink = '';
                    let primaryBtnText = '';
                    let secondaryLink = '';
                    let secondaryBtnText = 'Search Info';
                    let metaInfoHTML = '';

                    if (activeTab === 'missing') {{
                        primaryLink = `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${{item.ratingKey}}`;
                        primaryBtnText = 'Plex Info';
                        const googleQuery = encodeURIComponent(`${{item.title}} ${{item.year || ''}} ${{typeLabel}}`);
                        secondaryLink = `https://www.google.com/search?q=${{googleQuery}}`;
                        
                        metaInfoHTML = `
                            <div class="card-meta">
                                <span class="year">${{item.year || 'N/A'}}</span>
                                <span class="dot">•</span>
                                <span class="added-date">Added ${{item.added_at}}</span>
                            </div>
                        `;
                    }} else {{
                        primaryLink = item.plex_link;
                        primaryBtnText = 'Watch Now';
                        secondaryLink = `https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F${{item.guid.split('/').pop()}}`;
                        secondaryBtnText = 'Discover';

                        if (item.type === 'movie') {{
                            metaInfoHTML = `
                                <div class="card-meta">
                                    <span class="year">${{item.year || 'N/A'}}</span>
                                </div>
                                <div class="unwatched-label">Unwatched Movie</div>
                            `;
                        }} else {{
                            const percentage = item.total_episodes ? Math.round((item.viewed_episodes / item.total_episodes) * 100) : 0;
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

                    // Generate a random gradient for fallback posters
                    const gradients = [
                        'linear-gradient(135deg, #2b3a4a 0%, #0f171e 100%)',
                        'linear-gradient(135deg, #3a2b4a 0%, #170f1e 100%)',
                        'linear-gradient(135deg, #2b4a3a 0%, #0f1e17 100%)',
                        'linear-gradient(135deg, #4a3e2b 0%, #1e170f 100%)'
                    ];
                    const grad = gradients[Math.abs(item.title.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % gradients.length];

                    card.innerHTML = `
                        <div class="poster-container">
                            ${{item.poster_url ? `
                                <img class="poster" src="${{item.poster_url}}" alt="${{item.title}}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                            ` : ''}}
                            <div class="poster-fallback" style="${{item.poster_url ? 'display: none;' : 'display: flex;'}} background: ${{grad}};">
                                <div class="fallback-icon">${{item.type === 'movie' ? '🎬' : '📺'}}</div>
                                <div class="fallback-text">${{item.title}}</div>
                            </div>
                            <div class="type-badge ${{item.type}}">${{typeLabel}}</div>
                        </div>
                        <div class="card-body">
                            <h3 class="card-title" title="${{item.title}}">${{item.title}}</h3>
                            ${{metaInfoHTML}}
                            <div class="actions">
                                <a href="${{primaryLink}}" target="_blank" class="btn btn-primary">${{primaryBtnText}}</a>
                                <a href="${{secondaryLink}}" target="_blank" class="btn btn-secondary">${{secondaryBtnText}}</a>
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                }});
            }}
        }}

        // Initial Render
        filterAndRender();
    </script>
</body>
</html>
"""

    with open(html_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nHTML GAP Dashboard generated successfully at: {html_file_path}")
    return html_file_path

def main():
    parser = argparse.ArgumentParser(description="Find gaps between your Plex Watchlist and local server libraries.")
    parser.add_argument("--reauth", action="store_true", help="Force re-authentication with Plex.")
    parser.add_argument("--server", type=str, help="Specific Plex server name to connect to.")
    parser.add_argument("--type", type=str, choices=['movie', 'show'], help="Filter checking to only 'movie' or 'show'.")
    args = parser.parse_args()

    print("="*60)
    print("                 PLEX GAP ANALYZER")
    print("="*60)

    # 1. Authenticate with Plex
    account = authenticate_plex(force_login=args.reauth)

    # 2. Select server
    server_resource = select_server(account, target_server_name=args.server)

    # 3. Fetch local libraries (GUIDs, Titles, and Unwatched items)
    local_guids, local_titles, unwatched_local_items, machine_id = build_local_library_index(server_resource)

    # 4. Fetch Watchlist
    watchlist = fetch_watchlist(account, libtype=args.type)

    # 5. Cross-reference Watchlist -> Local Library (Finds Missing items)
    missing_items, total_watchlist = check_watchlist(watchlist, local_guids, local_titles)

    # 6. Index Watchlist & Cross-reference Local -> Watchlist (Finds Unwatched not in Watchlist)
    wl_guids, wl_titles = index_watchlist(watchlist)
    unwatched_not_watchlist = check_unwatched_not_watchlist(unwatched_local_items, wl_guids, wl_titles, machine_id)

    # 7. Print Console Summary
    print("\n" + "="*60)
    print("                    ANALYSIS SUMMARY")
    print("="*60)
    print(f"Server Name:           {server_resource.name}")
    print(f"Total Watchlist Items: {total_watchlist}")
    print(f"Missing from Server:   {len(missing_items)}")
    print(f"Unwatched Local Gaps:  {len(unwatched_not_watchlist)}")
    print("="*60)

    if missing_items:
        print(f"\nMissing Items (Watchlisted but not on Server) [{len(missing_items)} items]:")
        for i, item in enumerate(missing_items[:10]):
            type_char = "🎬" if item['type'] == 'movie' else "📺"
            year_str = f"({item['year']})" if item['year'] else ""
            print(f"  {i+1}. {type_char} {item['title']} {year_str}")
        if len(missing_items) > 10:
            print(f"  ... and {len(missing_items) - 10} more.")

    if unwatched_not_watchlist:
        print(f"\nLocal Gaps (Unwatched on Server but not on Watchlist) [{len(unwatched_not_watchlist)} items]:")
        for i, item in enumerate(unwatched_not_watchlist[:10]):
            type_char = "🎬" if item['type'] == 'movie' else "📺"
            year_str = f"({item['year']})" if item['year'] else ""
            progress_str = ""
            if item['type'] == 'show':
                progress_str = f" ({item['viewed_episodes']}/{item['total_episodes']} ep watched)"
            print(f"  {i+1}. {type_char} {item['title']} {year_str}{progress_str}")
        if len(unwatched_not_watchlist) > 10:
            print(f"  ... and {len(unwatched_not_watchlist) - 10} more.")

    # 8. Generate and open HTML Dashboard
    html_path = generate_html_report(missing_items, unwatched_not_watchlist, total_watchlist, server_resource.name)
    
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
