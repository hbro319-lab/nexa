"""NEXA Dispatch Server v2.1
Receives JSON commands from the browser UI and routes them to the local
dispatcher.  Also exposes a /search endpoint for the app finder.

New in v2.1:
  - /chat endpoint  -- send natural language to Ollama, auto-dispatch JSON
  - --daemon flag    -- run as a background process
  - --stop flag      -- stop a running daemon
  - --status flag    -- check if daemon is running

Run alongside your browser interface:
    python nexa_dispatch_server.py             # foreground
    python nexa_dispatch_server.py --daemon    # background
    python nexa_dispatch_server.py --stop      # stop daemon
    python nexa_dispatch_server.py --status    # check status
"""

import argparse
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from nexa_dispatcher import dispatch
from nexa_app_finder import app_index
from nexa_assets import get_html

HOST = "127.0.0.1"
PORT = 11435
PID_FILE = Path.home() / ".nexa" / "daemon.pid"
LOG_FILE = Path.home() / ".nexa" / "daemon.log"


class DispatchHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/ui":
            self._set_headers(200, "text/html; charset=utf-8")
            self.wfile.write(get_html().encode("utf-8"))

        elif path == "/health":
            self._set_headers(200)
            count = app_index.count
            self.wfile.write(json.dumps({
                "status": "ok",
                "service": "nexa_dispatch_server",
                "version": "2.0",
                "indexed_apps": count,
            }).encode("utf-8"))

        elif path == "/search":
            query = qs.get("q", [""])[0]
            limit = int(qs.get("limit", ["10"])[0])
            results = app_index.search(query, limit=limit)
            data = [
                {
                    "name": entry.name,
                    "exec": entry.exec_cmd,
                    "icon": entry.icon,
                    "comment": entry.comment,
                    "source": entry.source,
                    "score": round(score, 1),
                }
                for entry, score in results
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"query": query, "results": data}).encode("utf-8"))

        elif path == "/apps":
            category = qs.get("category", [""])[0]
            limit = int(qs.get("limit", ["50"])[0])
            if category:
                apps = app_index.by_category(category, limit=limit)
            else:
                apps = app_index.list_all()[:limit]
            data = [{"name": a.name, "exec": a.exec_cmd, "source": a.source, "icon": a.icon}
                    for a in apps]
            self._set_headers(200)
            self.wfile.write(json.dumps({"count": len(data), "apps": data}).encode("utf-8"))

        elif path == "/categories":
            cats = app_index.list_categories()
            self._set_headers(200)
            self.wfile.write(json.dumps({"categories": cats}).encode("utf-8"))

        elif path == "/refresh":
            count = app_index.refresh(force=True)
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "refreshed", "count": count}).encode("utf-8"))

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/dispatch":
            self._handle_dispatch()
        elif path == "/chat":
            self._handle_chat()
        elif path == "/reset":
            self._handle_reset()
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))

    def _handle_dispatch(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            command = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._set_headers(400)
            self.wfile.write(
                json.dumps({"error": "Invalid JSON", "message": str(e)}).encode("utf-8")
            )
            return
        try:
            result = dispatch(command)
            self._set_headers(200)
            self.wfile.write(
                json.dumps({"status": "ok", "result": result}).encode("utf-8")
            )
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(
                json.dumps({"error": "dispatch_failed", "message": str(e)}).encode("utf-8")
            )

    def _handle_chat(self):
        """Send a natural language message to Ollama and auto-dispatch any JSON commands."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode("utf-8"))
            message = data.get("message", "")
            if not message:
                self._set_headers(400)
                self.wfile.write(
                    json.dumps({"error": "No message provided"}).encode("utf-8")
                )
                return

            from nexa_api_bridge import NexaSession
            if not hasattr(self.server, "_chat_session"):
                self.server._chat_session = NexaSession()

            reply = self.server._chat_session.send(message)
            self._set_headers(200)
            self.wfile.write(json.dumps({"response": reply}).encode("utf-8"))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(
                json.dumps({"error": "chat_failed", "message": str(e)}).encode("utf-8")
            )

    def _handle_reset(self):
        """Reset the chat session history."""
        if hasattr(self.server, "_chat_session"):
            self.server._chat_session.reset()
        self._set_headers(200)
        self.wfile.write(json.dumps({"status": "Chat history cleared"}).encode("utf-8"))

    def log_message(self, format, *args):
        # Quieter logging
        pass


# ======================================================================
# SERVER LIFECYCLE
# ======================================================================

def run_server():
    # Pre-index apps at startup
    count = app_index.refresh(force=True)
    print(f"[NEXA] Indexed {count} applications")

    server = HTTPServer((HOST, PORT), DispatchHandler)
    print(f"[NEXA] Dispatch server listening on http://{HOST}:{PORT}")
    print(f"  Endpoints:")
    print(f"    GET  /           — Web UI (embedded)")
    print(f"    GET  /health     — server status")
    print(f"    GET  /search?q=  — search installed apps")
    print(f"    GET  /apps       — list all apps")
    print(f"    GET  /categories — list app categories")
    print(f"    GET  /refresh    — re-scan apps")
    print(f"    POST /dispatch   — execute a NEXA command")
    print(f"    POST /chat       — send natural language (Ollama)")
    print(f"    POST /reset      — clear chat history")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dispatch server...")
        server.server_close()


def daemon_start():
    """Start the server as a background daemon (Linux/macOS)."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        print("[NEXA] Daemon mode not supported on Windows. Use 'start /b python nexa_dispatch_server.py'")
        return

    pid = os.fork()
    if pid > 0:
        # Parent
        PID_FILE.write_text(str(pid))
        print(f"[NEXA] Daemon started (PID: {pid}, Port: {PORT})")
        return

    # Child — detach
    os.setsid()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    sys.stdin = open(os.devnull, "r")
    sys.stdout = open(str(LOG_FILE), "a")
    sys.stderr = sys.stdout

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    run_server()


def daemon_stop():
    """Stop the running daemon."""
    if not PID_FILE.exists():
        print("[NEXA] No daemon running")
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        print(f"[NEXA] Daemon stopped (PID: {pid})")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("[NEXA] Daemon was not running (stale PID). Cleaned up.")
    except Exception as e:
        print(f"[NEXA] Error stopping daemon: {e}")


def daemon_status():
    """Check if the daemon is running."""
    if not PID_FILE.exists():
        print("[NEXA] Daemon is not running")
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # Check if process exists
        print(f"[NEXA] Daemon is running (PID: {pid}, Port: {PORT})")
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        print("[NEXA] Daemon is not running (stale PID, cleaned up)")
    except Exception as e:
        print(f"[NEXA] Error checking status: {e}")


def _handle_signal(signum, frame):
    PID_FILE.unlink(missing_ok=True)
    sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXA Dispatch Server")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--stop", action="store_true", help="Stop running daemon")
    parser.add_argument("--status", action="store_true", help="Check daemon status")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port (default: {PORT})")
    args = parser.parse_args()

    PORT = args.port

    if args.stop:
        daemon_stop()
    elif args.status:
        daemon_status()
    elif args.daemon:
        daemon_start()
    else:
        run_server()
