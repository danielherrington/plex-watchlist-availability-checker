import threading
import time
import webbrowser
import uvicorn

def open_browser():
    """Waits for the web server to start up, then opens the dashboard in the default browser."""
    time.sleep(1.5)
    url = "http://127.0.0.1:8085"
    print(f"\nOpening dashboard: {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Failed to open browser automatically: {e}")
        print(f"Please open your browser manually and visit: {url}")

if __name__ == "__main__":
    print("="*60)
    print("                 PLEX MEDIA HUB HUB")
    print("="*60)
    print("Starting background web server...")
    
    # Start the browser-opener thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run the Uvicorn ASGI server
    uvicorn.run("server:app", host="127.0.0.1", port=8085, log_level="info")
