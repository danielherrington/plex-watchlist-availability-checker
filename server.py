import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from config_manager import (
    load_watch_next, save_watch_next,
    load_ignored_shows, save_ignored_shows
)
from plex_client import authenticate_plex, select_server
from processor import get_dashboard_data, normalize_title, sync_watch_next_to_plex

app = FastAPI(title="Plex Media Hub API Server")

class ItemPayload(BaseModel):
    ratingKey: Optional[str] = None
    title: Optional[str] = None

@app.get("/api/dashboard")
def api_dashboard():
    try:
        # Load active queues and ignore lists
        watch_next_titles = load_watch_next()
        ignored_shows = load_ignored_shows()
        ignored_shows_norm = {normalize_title(t) for t in ignored_shows}
        
        # Authenticate & select active server
        account = authenticate_plex()
        server_resource = select_server(account)
        
        # Process and generate the analytics dashboard payload
        data = get_dashboard_data(account, server_resource, watch_next_titles, ignored_shows_norm)
        
        # Append ignored shows config list
        data['ignored_shows'] = ignored_shows
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ignore")
def api_ignore(payload: ItemPayload):
    ignored = load_ignored_shows()
    key = payload.title or payload.ratingKey
    if key:
        key_lower = key.lower()
        if key_lower not in [x.lower() for x in ignored]:
            ignored.append(key)
            save_ignored_shows(ignored)
    return {"status": "ok"}

@app.post("/api/unignore_all")
def api_unignore_all():
    save_ignored_shows([])
    return {"status": "ok"}

def run_background_sync(queue):
    """Asynchronous background wrapper for Plex playlist sync."""
    try:
        account = authenticate_plex()
        server_resource = select_server(account)
        sync_watch_next_to_plex(server_resource, queue)
    except Exception as e:
        print(f"Background sync error: {e}")

@app.post("/api/queue")
def api_queue(payload: ItemPayload, background_tasks: BackgroundTasks):
    queue = load_watch_next()
    key = payload.ratingKey or payload.title
    if key:
        if key not in queue:
            queue.append(key)
            save_watch_next(queue)
            # Run Plex sync in the background
            background_tasks.add_task(run_background_sync, queue)
    return {"status": "ok"}

@app.post("/api/unqueue")
def api_unqueue(payload: ItemPayload, background_tasks: BackgroundTasks):
    queue = load_watch_next()
    key = payload.ratingKey or payload.title
    if key and key in queue:
        queue.remove(key)
        save_watch_next(queue)
        # Run Plex sync in the background
        background_tasks.add_task(run_background_sync, queue)
    return {"status": "ok"}

# Mount frontend directory to serve HTML, CSS, and JS static assets
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
