#!/usr/bin/env bash
# Plex Watchlist Checker Auto-Runner
# Automatically sets up a virtual environment, installs dependencies, and runs the script.

set -e

# Get the directory of the runner script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is not installed or not in PATH."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Setting up local Python virtual environment (.venv)..."
    python3 -m venv .venv
    echo "Virtual environment created."
fi

# Activate virtual environment
source .venv/bin/activate

# Install / update dependencies silently
if [ -f "requirements.txt" ]; then
    echo "Ensuring dependencies are installed..."
    pip install -q --disable-pip-version-check -r requirements.txt
fi

# Run the checker script, passing through any arguments
python3 app.py "$@"
