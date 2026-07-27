# Plex Watchlist Availability Checker

A lightweight, local tool to identify which items in your **Plex Watchlist** are currently missing from your **Plex Server**. It generates a premium, interactive glassmorphism dark-mode HTML dashboard.

## Features

- 🔒 **Secure Authentication**: Uses Plex's modern OAuth flow. You sign in through the official Plex website, and your credentials are never shared or saved by this script.
- ⚡ **Auto-Bootstrapping**: Includes a runner script (`run_checker.sh`) that automatically creates an isolated Python virtual environment (`.venv`) and handles dependencies silently. No manual `pip install` commands needed.
- 🔍 **Multi-Layered Matching**: Matches items by direct Plex GUIDs, alternate external IDs (IMDb, TMDB, TVDB), and normalized Title + Year fallback matching for maximum accuracy.
- 🎨 **HTML Dashboard**: Generates a self-contained, fully responsive HTML dashboard (`missing_watchlist.html`) featuring search, type filtering, sorting, and direct links to view items on Plex Discover.

---

## How to Run (Mac / Linux)

Run the auto-runner script in your terminal:

```bash
./run_checker.sh
```

### What happens:
1. **Setup**: The script sets up a local virtual environment (`.venv`) and installs dependencies.
2. **Login**: A secure login URL is printed (and opened in your browser). Click **Authorize** to link your account. Your login token will be securely cached in `.plex_config.json` so you only have to do this once.
3. **Selection**: If you have multiple Plex servers, you'll be prompted to select one from the list.
4. **Dashboard**: The tool compares your watchlist with your library and automatically opens `missing_watchlist.html` in your default browser.

---

## Command-Line Options

You can pass arguments directly to the runner script to customize its behavior:

```bash
# Force re-authentication (use this to change Plex accounts)
./run_checker.sh --reauth

# Specify a server directly (bypasses the terminal prompt)
./run_checker.sh --server "My Home Server"

# Only check for Movies or TV Shows
./run_checker.sh --type movie
./run_checker.sh --type show
```

## Security & Privacy

This project is built with privacy in mind:
- **No Credentials Saved**: Plex API tokens are retrieved using the standard OAuth PIN flow and saved locally in a hidden `.plex_config.json` file.
- **Git Safety**: A `.gitignore` file is pre-configured to ensure your `.plex_config.json` token file and generated lists are never uploaded to GitHub.
