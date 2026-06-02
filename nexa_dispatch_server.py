"""NEXA Dispatch Server v2.0
Receives JSON commands from the browser UI and routes them to the local
dispatcher.  Also exposes a /search endpoint for the app finder.

Run alongside your browser interface:
    python nexa_dispatch_server.py
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from nexa_dispatcher import dispatch
from nexa_app_finder import app_index
from nexa_assets import get_html

HOST = "127.0.0.1"
PORT = 11435


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
        if self.path != "/dispatch":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode("utf-8"))
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            command = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid JSON", "message": str(e)}).encode("utf-8"))
            return

        try:
            result = dispatch(command)
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok", "result": result}).encode("utf-8"))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": "dispatch_failed", "message": str(e)}).encode("utf-8"))

    def log_message(self, format, *args):
        # Quieter logging
        pass


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
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dispatch server...")
        server.server_close()


if __name__ == "__main__":
    run_server()
