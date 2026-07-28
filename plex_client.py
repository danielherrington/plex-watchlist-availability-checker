import sys
import time
import webbrowser
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from config_manager import load_config, save_config

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
