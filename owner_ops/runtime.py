from __future__ import annotations
import argparse
import json
import os

from .core import ControlDispatcher, OwnerOpsReadModel
from .discord_panel import render_panel
from .discord_webhook import DiscordBindingError, DiscordWebhookTransport
from .local_ui import LocalAPI, build_local_server
from .runtime_sources import HERMES_HOME, RuntimeSources

RUNTIME_ROOT = HERMES_HOME / "darwin" / "owner-ops"
PANEL_STATE = RUNTIME_ROOT / "panel-state.json"

def build_read_model():
    return OwnerOpsReadModel(RuntimeSources().readers())

def snapshot():
    return build_read_model().snapshot()

def _panel_message_id():
    try:
        data = json.loads(PANEL_STATE.read_text(encoding="utf-8"))
        value = str(data.get("message_id", ""))
        return value if value.isdigit() else ""
    except Exception:
        return ""

def _write_panel_message_id(message_id):
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = PANEL_STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"message_id": message_id}, sort_keys=True), encoding="utf-8")
    os.replace(tmp, PANEL_STATE)

class _DisabledAuth:
    def authorize(self, _request):
        raise PermissionError("local control actions are disabled until trusted binding exists")

def discord_once():
    webhook = os.environ.get("DARWIN_DISCORD_WEBHOOK_URL", "")
    if not webhook:
        raise DiscordBindingError("DARWIN_DISCORD_WEBHOOK_URL is not configured")
    transport = DiscordWebhookTransport(webhook)
    content = render_panel(snapshot())
    message_id = _panel_message_id()
    if message_id:
        transport.edit_panel("", message_id, content)
        return {"status":"EDITED","message_id":message_id}
    message_id = transport.create_panel(content)
    _write_panel_message_id(message_id)
    return {"status":"CREATED","message_id":message_id}

def serve(host="127.0.0.1", port=8765):
    api = LocalAPI(build_read_model(), _DisabledAuth(), ControlDispatcher({}))
    server = build_local_server(api, host=host, port=port)
    server.serve_forever(poll_interval=1.0)

def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m owner_ops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    serve_p = sub.add_parser("serve")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)
    sub.add_parser("discord-once")
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(snapshot(), indent=2, sort_keys=True)); return 0
    if args.command == "serve":
        serve(args.host, args.port); return 0
    if args.command == "discord-once":
        print(json.dumps(discord_once(), sort_keys=True)); return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
