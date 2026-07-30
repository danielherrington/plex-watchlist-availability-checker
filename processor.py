import re
import datetime
import unicodedata
from plex_client import fetch_watchlist
from tvmaze_client import query_tvmaze, fetch_tvmaze_batch
from config_manager import load_sagas

def normalize_title(title):
    """Normalizes title for fallback fuzzy matching (accents, cases, punctuation)."""
    if not title:
        return ""
    title = title.lower()
    title = unicodedata.normalize('NFKD', title).encode('ASCII', 'ignore').decode('utf-8')
    title = re.sub(r'[^a-z0-9\s]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

def build_local_library_index(plex_server, watch_next_titles, ignored_shows_norm, watchlist_shows_norm=None, watchlist_progress=None):
    """Fetches local server library, indexes items, and gathers TV show/unwatched history."""
    try:
        plex = plex_server.connect()
    except Exception as e:
        raise RuntimeError(f"Failed to connect to server: {e}")

    machine_id = plex.machineIdentifier
    local_guids = set()
    local_titles = {}
    unwatched_local_items = []
    in_progress_shows = []
    local_episodes_inventory = {}
    
    wn_norm = set()
    for t in watch_next_titles:
        t_str = str(t).strip()
        wn_norm.add(t_str.lower())
        wn_norm.add(normalize_title(t_str))

    for section in plex.library.sections():
        if section.type == 'movie':
            try:
                items = section.all(includeGuids=1)
                for item in items:
                    if item.guid:
                        local_guids.add(item.guid.lower())
                    if hasattr(item, 'guids') and item.guids:
                        for g in item.guids:
                            if g.id:
                                local_guids.add(g.id.lower())
                    
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
                    
                    if not is_watched:
                        unwatched_local_items.append({
                            'title': item.title,
                            'year': item.year if hasattr(item, 'year') else None,
                            'type': 'movie',
                            'ratingKey': item.ratingKey,
                            'guid': item.guid,
                            'viewed_episodes': 0,
                            'total_episodes': 0,
                            'watch_next': (norm_title in wn_norm) or (item.ratingKey and str(item.ratingKey).lower() in wn_norm),
                            'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                        })
            except Exception as e:
                print(f"    Warning: Failed to scan section '{section.title}': {e}")
                
        elif section.type == 'show':
            try:
                items = section.all(includeGuids=1)
                for item in items:
                    norm_title = normalize_title(item.title)
                    
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
                    local_viewed = getattr(item, 'viewedLeafCount', 0)
                    global_viewed = watchlist_progress.get(norm_title, 0) if watchlist_progress else 0
                    viewed_episodes = max(local_viewed, global_viewed)
                    unwatched_count = getattr(item, 'unwatchedLeafCount', 0)

                    # Fetch local episodes inventory ONLY if the show is in progress and has unwatched episodes
                    episodes = []
                    if viewed_episodes > 0 and unwatched_count > 0:
                        try:
                            episodes = item.episodes()
                            episodes = sorted(episodes, key=lambda x: (x.parentIndex or 0, x.index or 0))
                            local_episodes_inventory[norm_title] = [
                                {
                                    'season': ep.parentIndex if ep.parentIndex is not None else 0,
                                    'episode': ep.index if ep.index is not None else 0,
                                    'ratingKey': ep.ratingKey,
                                    'air_date': ep.originallyAvailableAt.strftime('%Y-%m-%d') if ep.originallyAvailableAt else None,
                                    'title': ep.title,
                                    'watched': getattr(ep, 'isPlayed', False) or getattr(ep, 'viewCount', 0) > 0
                                }
                                for ep in episodes
                            ]
                        except Exception as e:
                            print(f"    Warning: Failed to fetch episodes for {item.title}: {e}")

                    if unwatched_count > 0 and viewed_episodes == 0:
                        unwatched_local_items.append({
                            'title': item.title,
                            'year': item.year if hasattr(item, 'year') else None,
                            'type': 'show',
                            'ratingKey': item.ratingKey,
                            'guid': item.guid,
                            'viewed_episodes': viewed_episodes,
                            'total_episodes': total_episodes,
                            'watch_next': (norm_title in wn_norm) or (item.ratingKey and str(item.ratingKey).lower() in wn_norm),
                            'poster_url': item.thumbUrl if hasattr(item, 'thumbUrl') else ""
                        })

                    if viewed_episodes > 0:
                        try:
                            last_watched = None
                            if episodes:
                                for ep in episodes:
                                    if getattr(ep, 'isPlayed', False) or getattr(ep, 'viewCount', 0) > 0:
                                        last_watched = ep
                                        
                            next_ep_local = None
                            if last_watched and episodes:
                                try:
                                    last_idx = episodes.index(last_watched)
                                    if last_idx + 1 < len(episodes):
                                        next_ep_local = episodes[last_idx + 1]
                                except ValueError:
                                    pass
                                        
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
                
    return local_guids, local_titles, unwatched_local_items, in_progress_shows, local_episodes_inventory, machine_id

def check_watchlist(watchlist, local_guids, local_titles, watch_next_titles):
    """Compares watchlist items against local server library to find missing files."""
    missing_items = []
    total_checked = 0
    
    wn_norm = set()
    for t in watch_next_titles:
        t_str = str(t).strip()
        wn_norm.add(t_str.lower())
        wn_norm.add(normalize_title(t_str))

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
                            
        if not is_matched:
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
                'watch_next': (normalize_title(item.title) in wn_norm) or (rating_key and str(rating_key).lower() in wn_norm),
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
    """Identifies unwatched local server items, mapping whether they are in the user's watchlist."""
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
            'in_watchlist': is_in_watchlist,
            'plex_link': local_link
        })
            
    return unwatched_not_watchlist

def calculate_tv_show_schedules(in_progress_shows, machine_id, tvmaze_map=None, local_episodes_inventory=None, watch_next_titles=None):
    """Integrates TVmaze API to trace next available/missing/upcoming episodes of TV shows."""
    tv_schedule_list = []
    today = datetime.date.today()
    
    wn_norm = set()
    if watch_next_titles:
        for t in watch_next_titles:
            t_str = str(t).strip()
            wn_norm.add(t_str.lower())
            wn_norm.add(normalize_title(t_str))

    for show in in_progress_shows:
        title = show['title']
        last_watched = show['last_watched']
        next_ep_local = show['next_ep_local']
        
        # Determine watched count
        v_count = show.get('viewed_episodes', 0)
        t_eps = show.get('total_episodes', 0)
        
        next_ep_metadata = None
        status = "completed"
        status_label = "Show fully watched"
        plex_link = ""
        
        # Look up pre-fetched batch or fallback synchronously
        tvmaze_data = None
        if tvmaze_map and title in tvmaze_map:
            tvmaze_data = tvmaze_map[title]
        else:
            tvmaze_data = query_tvmaze(title)
        
        if tvmaze_data and '_embedded' in tvmaze_data and 'episodes' in tvmaze_data['_embedded']:
            # Filter out specials (Season 0)
            episodes = [ep for ep in tvmaze_data['_embedded']['episodes'] if ep.get('season', 0) > 0]
            episodes = sorted(episodes, key=lambda x: (x.get('season', 0), x.get('number', 0)))
            t_eps = len(episodes)
            
            # Determine next episode using local watched history if available
            norm_title = normalize_title(title)
            found_next_locally = False
            last_watched_season = 1
            next_tvmaze_ep = None
            
            if local_episodes_inventory and norm_title in local_episodes_inventory:
                local_eps = [le for le in local_episodes_inventory[norm_title] if le.get('season', 0) > 0]
                local_eps = sorted(local_eps, key=lambda x: (x['season'], x['episode']))
                
                # Find first unwatched local episode
                first_unwatched = None
                for le in local_eps:
                    if not le.get('watched', False):
                        first_unwatched = le
                        break
                
                if first_unwatched:
                    # Find this episode in TVmaze
                    for idx, ep in enumerate(episodes):
                        if ep.get('season') == first_unwatched['season'] and ep.get('number') == first_unwatched['episode']:
                            next_tvmaze_ep = ep
                            v_count = idx
                            last_watched_season = episodes[idx - 1].get('season', 1) if idx > 0 else 1
                            found_next_locally = True
                            break
                            
            if not found_next_locally:
                last_watched_season = episodes[v_count - 1].get('season', 1) if (v_count > 0 and v_count - 1 < len(episodes)) else 1
                if v_count < len(episodes):
                    next_tvmaze_ep = episodes[v_count]
                
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
                
                # Check if next TVmaze episode exists in our local inventory
                next_ep_local_resolved = None
                norm_title = normalize_title(title)
                if local_episodes_inventory and norm_title in local_episodes_inventory:
                    for ep in local_episodes_inventory[norm_title]:
                        if ep['season'] == ep_season and ep['episode'] == ep_number:
                            next_ep_local_resolved = ep
                            break
                else:
                    # Fallback to the next_ep_local pre-calculated on the show object (backward compatible for tests!)
                    if next_ep_local and next_ep_local['season'] == ep_season and next_ep_local['episode'] == ep_number:
                        next_ep_local_resolved = next_ep_local
                
                if next_ep_local_resolved:
                    status = "available"
                    status_label = f"Episode S{ep_season:02d}E{ep_number:02d} available on server"
                    plex_link = f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{next_ep_local_resolved['ratingKey']}"
                else:
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
                    
                    discover_key = show['ratingKey']
                    plex_link = f"https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F{discover_key}"
            else:
                status = "caught_up"
                status_label = "All Caught Up (No upcoming episodes)"
                discover_key = show['ratingKey']
                plex_link = f"https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F{discover_key}"
        else:
            # Fallback when TVmaze data is unavailable
            next_ep_local_resolved = next_ep_local
            if next_ep_local_resolved:
                status = "available"
                status_label = f"Episode S{next_ep_local_resolved['season']:02d}E{next_ep_local_resolved['episode']:02d} available"
                plex_link = f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{next_ep_local_resolved['ratingKey']}"
                next_ep_metadata = {
                    'season': next_ep_local_resolved['season'],
                    'episode': next_ep_local_resolved['episode'],
                    'title': next_ep_local_resolved.get('title', 'TBA'),
                    'air_date': next_ep_local_resolved.get('air_date')
                }
            else:
                status = "caught_up"
                status_label = "All Caught Up (Schedules offline)"
                discover_key = show['ratingKey']
                plex_link = f"https://app.plex.tv/desktop/#!/provider/tv.plex.provider.discover/details?key=%2Flibrary%2Fmetadata%2F{discover_key}"
                
        if status != "caught_up":
            tv_schedule_list.append({
                'title': title,
                'type': 'show',
                'ratingKey': show['ratingKey'],
                'viewed_episodes': v_count,
                'total_episodes': t_eps,
                'poster_url': show['poster_url'],
                'status': status,
                'status_label': status_label,
                'plex_link': plex_link,
                'next_episode': next_ep_metadata,
                'watch_next': (normalize_title(title) in wn_norm) or (show['ratingKey'] and str(show['ratingKey']).lower() in wn_norm)
            })
            
    return tv_schedule_list

def calculate_movie_sagas(local_titles, machine_id, watchlist_movies_norm=None, watch_next_titles=None, ignored_shows_norm=None):
    """Loads sagas.json and determines completion stats and next available/missing movies."""
    sagas_data = load_sagas()
    active_sagas = []
    all_sagas_progress = []
    
    wn_norm = set()
    if watch_next_titles:
        for t in watch_next_titles:
            t_str = str(t).strip()
            wn_norm.add(t_str.lower())
            wn_norm.add(normalize_title(t_str))

    for saga_name, movie_list in sagas_data.items():
        if ignored_shows_norm and normalize_title(saga_name) in ignored_shows_norm:
            continue
            
        total_movies = len(movie_list)
        watched_count = 0
        present_count = 0
        next_movie = None
        
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
            
            if movie_watched:
                watched_count += 1
            elif not next_movie:
                next_movie = {
                    'title': movie_title,
                    'index': idx + 1,
                    'status': 'available' if movie_in_library else 'missing',
                    'ratingKey': lib_item['ratingKey'] if lib_item else "",
                    'poster_url': lib_item['poster_url'] if lib_item else "",
                    'plex_link': f"https://app.plex.tv/desktop/#!/server/{machine_id}/details?key=%2Flibrary%2Fmetadata%2F{lib_item['ratingKey']}" if lib_item else ""
                }
                
        percentage = int((watched_count / total_movies) * 100) if total_movies > 0 else 0
        
        all_sagas_progress.append({
            'title': saga_name,
            'type': 'saga',
            'ratingKey': '',
            'watched_movies': watched_count,
            'total_movies': total_movies,
            'percentage': percentage,
            'next_movie': next_movie['title'] if next_movie else "Saga Completed",
            'next_movie_status': next_movie['status'] if next_movie else "completed"
        })
        
        if watched_count > 0 and watched_count < total_movies and next_movie:
            if watchlist_movies_norm is None or normalize_title(next_movie['title']) in watchlist_movies_norm:
                status_label = f"Next up: {next_movie['title']} - " + ("Available to watch" if next_movie['status'] == 'available' else "Missing from server")
                active_sagas.append({
                    'title': saga_name,
                    'type': 'saga',
                    'viewed_episodes': watched_count,
                    'total_episodes': total_movies,
                    'poster_url': next_movie['poster_url'],
                    'status': next_movie['status'],
                    'status_label': status_label,
                    'plex_link': next_movie['plex_link'],
                    'next_movie': {
                        'title': next_movie['title'],
                        'index': next_movie['index']
                    },
                    'watch_next': normalize_title(saga_name) in wn_norm
                })
            
    return active_sagas, all_sagas_progress

async def async_get_accurate_viewed_count(client, rating_key, token, fallback_viewed):
    """Queries Plex metadata server children API to calculate true viewed leaf count from season user states (asynchronously)."""
    import xml.etree.ElementTree as ET
    if not rating_key or rating_key == "nan":
        return fallback_viewed
        
    try:
        url = f"https://metadata.provider.plex.tv/library/metadata/{rating_key}/children?X-Plex-Token={token}&includeUserState=1"
        response = await client.get(url, timeout=5.0)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            total_viewed = 0
            for directory in root.findall(".//Directory"):
                total_viewed += int(directory.attrib.get('viewedLeafCount', 0))
            return total_viewed
    except Exception as e:
        print(f"Warning: Failed to fetch accurate viewed count for show {rating_key} (async): {e}")
    return fallback_viewed

async def get_dashboard_data(account, server_resource, watch_next_titles, ignored_shows_norm, libtype=None):
    """Executes the complete core analytical flow and returns the compiled dashboard payload."""
    import asyncio
    from config_manager import global_plex_cache
    
    cache_key = f"dashboard_{server_resource.name}_{libtype}"
    cached_data = global_plex_cache.get(cache_key)
    if cached_data is not None:
        return cached_data

    # 1. Fetch watchlist (utilizing cache to prevent Plex network hits)
    watchlist_cache_key = f"watchlist_{account.username}_{libtype}"
    watchlist = global_plex_cache.get(watchlist_cache_key)
    if watchlist is None:
        watchlist = await asyncio.to_thread(fetch_watchlist, account, libtype=libtype)
        global_plex_cache.set(watchlist_cache_key, watchlist)

    watchlist_shows_norm = {normalize_title(item.title) for item in watchlist if item.type == 'show'}
    watchlist_movies_norm = {normalize_title(item.title) for item in watchlist if item.type == 'movie'}

    # Track global progress from watchlist for local shows, query accurate count from season levels concurrently
    watchlist_progress = {}
    import httpx
    async with httpx.AsyncClient() as client:
        tasks = []
        item_keys = []
        for item in watchlist:
            if item.type == 'show':
                norm_title = normalize_title(item.title)
                global_viewed = getattr(item, 'viewedLeafCount', 0)
                if global_viewed > 0:
                    rating_key = item.guid.rsplit('/', 1)[-1] if item.guid else ""
                    tasks.append(async_get_accurate_viewed_count(client, rating_key, account.authToken, global_viewed))
                    item_keys.append((norm_title, global_viewed))
                else:
                    watchlist_progress[norm_title] = 0

        if tasks:
            results = await asyncio.gather(*tasks)
            for (norm_title, _), val in zip(item_keys, results):
                watchlist_progress[norm_title] = val

    # 2. Build local index (only scanning shows that are in the watchlist) in a separate worker thread
    local_index_cache_key = f"local_index_{server_resource.name}"
    local_index = global_plex_cache.get(local_index_cache_key)
    if local_index is None:
        local_index = await asyncio.to_thread(
            build_local_library_index, server_resource, watch_next_titles, ignored_shows_norm, watchlist_shows_norm, watchlist_progress
        )
        global_plex_cache.set(local_index_cache_key, local_index)

    local_guids, local_titles, unwatched_local_items, in_progress_shows, local_episodes_inventory, machine_id = local_index
    
    # 3. Inject watchlist-only shows
    local_in_progress_titles = {normalize_title(s['title']) for s in in_progress_shows}
    for item in watchlist:
        if item.type == 'show':
            norm_title = normalize_title(item.title)
            viewed_episodes = watchlist_progress.get(norm_title, getattr(item, 'viewedLeafCount', 0))
            total_episodes = getattr(item, 'leafCount', 0)
            if viewed_episodes > 0:
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

    # 4. Pre-fetch TVmaze guides concurrently
    show_titles = [show['title'] for show in in_progress_shows]
    from tvmaze_client import async_fetch_tvmaze_batch
    tvmaze_map = await async_fetch_tvmaze_batch(show_titles)
    
    # 5. Find missing items (run calculations in thread pool to prevent blocking)
    missing_items, total_watchlist = await asyncio.to_thread(
        check_watchlist, watchlist, local_guids, local_titles, watch_next_titles
    )
    
    # 6. Find unwatched gaps
    wl_guids, wl_titles = index_watchlist(watchlist)
    unwatched_local_gaps = await asyncio.to_thread(
        check_unwatched_not_watchlist, unwatched_local_items, wl_guids, wl_titles, machine_id
    )
    
    # 7. Trace TV Show next schedules
    tv_schedules = await asyncio.to_thread(
        calculate_tv_show_schedules, in_progress_shows, machine_id, tvmaze_map, local_episodes_inventory, watch_next_titles
    )
    
    # 8. Calculate Movie Sagas progress (filtered to watchlist movies)
    active_sagas, sagas_progress = await asyncio.to_thread(
        calculate_movie_sagas, local_titles, machine_id, watchlist_movies_norm, watch_next_titles, ignored_shows_norm
    )
    
    # 9. Combine continue watching queues
    continue_watching = tv_schedules + active_sagas
    
    result = {
        'server_name': server_resource.name,
        'total_watchlist': total_watchlist,
        'continue_watching': continue_watching,
        'missing_items': missing_items,
        'unwatched_local_gaps': unwatched_local_gaps,
        'sagas_progress': sagas_progress
    }
    
    global_plex_cache.set(cache_key, result)
    return result

def sync_watch_next_to_plex(server_resource, watch_next_titles):
    """Syncs watch_next queue items to a Plex playlist in the correct order."""
    playlist_title = "Hub - Watch Next"
    try:
        print("Syncing Watch Next queue to Plex Server Playlist...")
        plex = server_resource.connect()
        
        items = []
        for key in watch_next_titles:
            try:
                # ratingKey can be integer or string representing integer
                item = plex.fetchItem(int(key))
                items.append(item)
            except Exception:
                # If ratingKey is a show title (fallback), we can search for the show
                try:
                    search_results = plex.search(key)
                    if search_results:
                        items.append(search_results[0])
                except Exception:
                    pass
                    
        # Find and delete existing playlist if it exists
        try:
            playlists = plex.playlists()
            for p in playlists:
                if p.title == playlist_title:
                    p.delete()
                    break
        except Exception as e:
            print(f"Warning: Failed to scan or delete existing playlist: {e}")
            
        if items:
            plex.createPlaylist(playlist_title, items=items)
            print(f"Successfully synced {len(items)} items to Playlist '{playlist_title}'.")
        else:
            print("No items in Watch Next queue; playlist cleared.")
    except Exception as e:
        print(f"Error syncing Watch Next queue to Plex: {e}")
