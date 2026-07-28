import asyncio
import time
import requests
import httpx
from config_manager import load_tvmaze_cache, save_tvmaze_cache

def query_tvmaze(show_title):
    """Synchronous single-show query for backward compatibility and tests."""
    cache = load_tvmaze_cache()
    now = time.time()
    if show_title in cache:
        cached_data = cache[show_title]
        if now - cached_data.get('timestamp', 0) < 86400:
            return cached_data.get('data')
            
    url = "https://api.tvmaze.com/singlesearch/shows"
    try:
        r = requests.get(url, params={"q": show_title, "embed": "episodes"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            cache[show_title] = {'timestamp': now, 'data': data}
            save_tvmaze_cache(cache)
            return data
    except Exception as e:
        print(f"Warning: Failed to fetch TVmaze details for '{show_title}': {e}")
        
    if show_title in cache:
        return cache[show_title].get('data')
    return None

async def async_query_tvmaze(client, show_title, cache, now):
    """Asynchronous fetch helper for TVmaze API."""
    if show_title in cache:
        cached_data = cache[show_title]
        if now - cached_data.get('timestamp', 0) < 86400:
            return show_title, cached_data.get('data')

    url = "https://api.tvmaze.com/singlesearch/shows"
    try:
        r = await client.get(url, params={"q": show_title, "embed": "episodes"}, timeout=10.0)
        if r.status_code == 200:
            data = r.json()
            cache[show_title] = {'timestamp': now, 'data': data}
            return show_title, data
    except Exception as e:
        print(f"Warning: Failed to fetch TVmaze details for '{show_title}' (async): {e}")

    if show_title in cache:
        return show_title, cache[show_title].get('data')
    return show_title, None

async def async_fetch_tvmaze_batch(show_titles):
    """Fetches TVmaze guide data for multiple show titles concurrently."""
    cache = load_tvmaze_cache()
    now = time.time()
    
    titles_to_fetch = []
    results = {}
    
    for title in show_titles:
        if title in cache and now - cache[title].get('timestamp', 0) < 86400:
            results[title] = cache[title].get('data')
        else:
            titles_to_fetch.append(title)
            
    if not titles_to_fetch:
        return results

    print(f"Fetching {len(titles_to_fetch)} TV show schedules concurrently from TVmaze...")
    async with httpx.AsyncClient() as client:
        tasks = [async_query_tvmaze(client, title, cache, now) for title in titles_to_fetch]
        fetched = await asyncio.gather(*tasks)
        
        for title, data in fetched:
            if data:
                results[title] = data
                
    save_tvmaze_cache(cache)
    return results

def fetch_tvmaze_batch(show_titles):
    """Synchronous entry point that runs the async batch fetcher safely, even if a loop is active."""
    try:
        return asyncio.run(async_fetch_tvmaze_batch(show_titles))
    except RuntimeError:
        # Safe fallback if run within an active event loop (e.g. inside uvicorn/FastAPI)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(async_fetch_tvmaze_batch(show_titles)))
            return future.result()
