"""
NEXA v2.0 — Unified Launcher
This is the single entry point for the packaged executable.

Modes:
  nexa              → Interactive CLI (connects to Ollama)
  nexa --server     → Start dispatch server (HTTP API for the web UI)
  nexa --search <q> → Quick app search from command line
  nexa --gui        → Open the web UI in the default browser
  nexa --help       → Show help
"""

import argparse
import os
import sys
import json
import webbrowser
import threading

# Ensure the bundled directory is in the path (for PyInstaller)
if getattr(sys, 'frozen', False):
    # PyInstaller extracts bundled data files to sys._MEIPASS
    BUNDLE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BUNDLE_DIR

# Set BASE_DIR: prefer the exe directory (so user can put their own config
# next to the exe), fall back to the bundle dir for packaged defaults.
BASE_DIR = EXE_DIR

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

# Make BUNDLE_DIR available to other modules for finding packaged data files
os.environ['NEXA_BUNDLE_DIR'] = BUNDLE_DIR
os.environ['NEXA_EXE_DIR'] = EXE_DIR


def run_cli():
    """Launch the interactive CLI (nexa_api_bridge)."""
    from nexa_api_bridge import NexaSession, check_ollama, SYSTEM_PROMPT
    from nexa_app_finder import app_index
    import requests

    print("+" + "=" * 42 + "+")
    print("|   NEXA v2.0  --  Local Intelligence      |")
    print("|   Powered by Ollama                       |")
    print("|   Full system control (Win / Linux / Mac)  |")
    print("|                                            |")
    print("|   'reset'       = clear history            |")
    print("|   'model <name>' = switch model            |")
    print("|   'search <q>'  = search installed apps    |")
    print("|   'server'      = start dispatch server    |")
    print("|   'exit'        = quit                     |")
    print("+" + "=" * 42 + "+\n")

    check_ollama()

    count = app_index.refresh(force=True)
    print(f"[NEXA] Indexed {count} installed applications.\n")

    session = NexaSession()

    # Import MODEL at module level for mutation
    from nexa_api_bridge import MODEL, STREAM
    current_model = MODEL

    while True:
        try:
            user = input("YOU > ").strip()
            if not user:
                continue
            if user.lower() == "exit":
                print("NEXA offline.")
                break
            if user.lower() == "reset":
                session.reset()
                continue
            if user.lower().startswith("model "):
                import nexa_api_bridge
                nexa_api_bridge.MODEL = user.split(" ", 1)[1].strip()
                print(f"[NEXA] Model switched to: {nexa_api_bridge.MODEL}\n")
                continue
            if user.lower() == "server":
                print("[NEXA] Starting dispatch server...")
                run_server()
                break
            if user.lower().startswith("search "):
                query = user.split(" ", 1)[1].strip()
                results = app_index.search(query, limit=10)
                if results:
                    print(f"\n  Found {len(results)} apps for '{query}':")
                    for entry, score in results:
                        print(f"    {entry.name:<30} {entry.exec_cmd:<40} [score={score:.0f}]")
                else:
                    print(f"  No apps found for '{query}'")
                print()
                continue

            session.send(user)
            print()

        except KeyboardInterrupt:
            print("\nNEXA offline.")
            break
        except Exception as e:
            print(f"[ERROR] {e}\n")


def run_server():
    """Start the dispatch HTTP server."""
    from nexa_dispatch_server import run_server as _run
    _run()


def run_search(query):
    """Quick search from command line."""
    from nexa_app_finder import app_index
    count = app_index.refresh(force=True)
    results = app_index.search(query, limit=15)
    if results:
        print(f"Found {len(results)} apps for '{query}' (indexed {count} total):\n")
        print(f"  {'Name':<35} {'Executable':<45} {'Score':>5}  Source")
        print(f"  {'-'*35} {'-'*45} {'-'*5}  {'-'*10}")
        for entry, score in results:
            print(f"  {entry.name:<35} {entry.exec_cmd:<45} {score:>5.0f}  {entry.source}")
    else:
        print(f"No apps found matching '{query}' ({count} apps indexed)")


def run_gui():
    """Open the web UI in the default browser and start the server."""
    # Start server in a background thread, then open browser to localhost
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(0.5)  # Give the server a moment to start

    url = "http://127.0.0.1:11435/"
    print(f"[NEXA] Opening web UI: {url}")
    webbrowser.open(url)

    # Keep main thread alive
    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\nNEXA offline.")


def main():
    parser = argparse.ArgumentParser(
        prog="nexa",
        description="NEXA v2.0 — Local System Intelligence powered by Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nexa                     Interactive CLI session
  nexa --server            Start HTTP dispatch server (for web UI)
  nexa --gui               Open web UI + start server
  nexa --search "browser"  Search installed applications
  nexa --search "vscode"   Find Visual Studio Code
        """
    )
    parser.add_argument("--server", action="store_true",
                        help="Start the dispatch HTTP server (port 11435)")
    parser.add_argument("--gui", action="store_true",
                        help="Open the web UI in the browser and start the server")
    parser.add_argument("--search", type=str, metavar="QUERY",
                        help="Search for installed applications")
    parser.add_argument("--version", action="version", version="NEXA v2.0.0")

    args = parser.parse_args()

    if args.search:
        run_search(args.search)
    elif args.server:
        run_server()
    elif args.gui:
        run_gui()
    else:
        run_cli()


if __name__ == "__main__":
    main()
