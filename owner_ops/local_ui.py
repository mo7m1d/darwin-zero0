from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .model import ControlRequest

MAX_BODY = 16 * 1024
DEFAULT_HOST = "127.0.0.1"

DASHBOARD_HTML = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DARWIN ZERO-0 Owner Ops</title></head><body><main><h1>DARWIN ZERO-0</h1><pre id="status">Loading...</pre></main><script>async function refresh(){const r=await fetch("/api/status",{cache:"no-store"});const x=await r.json();document.getElementById("status").textContent=JSON.stringify(x,null,2);}refresh();setInterval(refresh,60000);</script></body></html>'

class LocalAPI:
    def __init__(self, read_model, dispatcher, trusted_local_authorizer=None):
        self.read_model = read_model
        self.dispatcher = dispatcher
        self.trusted_local_authorizer = trusted_local_authorizer
    def status(self):
        return self.read_model.snapshot()
    def control(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("invalid request")
        if self.trusted_local_authorizer is None:
            raise PermissionError("local controls disabled until trusted runtime binding")
        request = self.trusted_local_authorizer(payload)
        if not isinstance(request, ControlRequest):
            raise PermissionError("invalid trusted local authorization result")
        return self.dispatcher.dispatch(request.validate())

def build_local_server(api, host=DEFAULT_HOST, port=8765):
    if host != DEFAULT_HOST:
        raise ValueError("Owner Ops may bind only to 127.0.0.1 by default")
    if isinstance(port, bool) or not isinstance(port, int) or not (port == 0 or 1024 <= port <= 65535):
        raise ValueError("invalid local port")

    class Handler(BaseHTTPRequestHandler):
        server_version = "DARWINOwnerOps/1"
        def _json(self, status, payload):
            blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)
        def do_GET(self):
            if self.path == "/":
                blob = DASHBOARD_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
            elif self.path == "/api/status":
                self._json(200, api.status())
            else:
                self._json(404, {"error":"not found"})
        def do_POST(self):
            if self.path != "/api/control":
                self._json(404, {"error":"not found"}); return
            try:
                length = int(self.headers.get("Content-Length","0"))
            except ValueError:
                self._json(400, {"error":"invalid content length"}); return
            if length <= 0 or length > MAX_BODY:
                self._json(413, {"error":"request too large"}); return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self._json(200, api.control(payload))
            except Exception as exc:
                self._json(403, {"error": type(exc).__name__})
        def log_message(self, *_):
            return
    return ThreadingHTTPServer((host, port), Handler)
