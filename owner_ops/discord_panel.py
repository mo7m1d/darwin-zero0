from __future__ import annotations
import re
from .events import EventCoalescer

MENTION = re.compile(r"@(?:everyone|here)|<@!?\d+>|<@&\d+>", re.I)

def safe_text(value, limit=500):
    text = str(value if value is not None else "")
    text = "".join(ch if ch >= " " or ch in "\n\t" else " " for ch in text)
    text = MENTION.sub("[mention]", text).replace("```", "[fence]")
    return text[:limit]

def render_panel(snapshot):
    sections = snapshot.get("sections", {})
    def val(section, key, default="UNKNOWN"):
        raw = sections.get(section, {})
        if isinstance(raw, dict):
            return safe_text(raw.get(key, raw.get("status", default)), 180)
        return default
    lines = [
        "**DARWIN ZERO-0 - Owner Ops**",
        f"System: `{val('system','state')}` | Safety: `{val('system','safety_version')}`",
        f"Task: `{val('task','name')}` | Progress: `{val('task','progress')}`",
        f"Control: `{val('control','state')}` | Approvals: `{val('control','approvals_mode')}`",
        f"Spend: `{val('budget','spend')}` | Budget: `{val('budget','status')}`",
        f"Model: `{val('model','model')}` | Router: `{val('model','router')}`",
        f"Recovery: `{val('recovery','status')}` | Context: `{val('context','status')}`",
        f"Git: `{val('git','commit')}` | CI: `{val('git','ci')}`",
        f"Alert: `{val('security','last_alert')}`",
        f"Updated: {int(snapshot.get('generated_at',0))}",
    ]
    return "\n".join(lines)[:1900]

class FakeDiscordTransport:
    def __init__(self):
        self.edits = []
    def edit_panel(self, channel_id, message_id, content):
        if not channel_id or not message_id:
            raise ValueError("panel routing identity required")
        self.edits.append((channel_id, message_id, content))

class DiscordPanelController:
    def __init__(self, read_model, transport, channel_id, message_id, coalescer: EventCoalescer, clock=None):
        self.read_model = read_model
        self.transport = transport
        self.channel_id = channel_id
        self.message_id = message_id
        self.coalescer = coalescer
        self.clock = clock or coalescer.clock
        self.failures = 0
        self.next_retry_at = 0

    def on_event(self, event):
        return self.coalescer.push(event)

    def tick(self):
        now = int(self.clock())
        if now < self.next_retry_at:
            return False
        if self.coalescer.ready():
            self.coalescer.drain()
        elif not self.coalescer.heartbeat_due():
            return False
        snapshot = self.read_model.snapshot()
        try:
            self.transport.edit_panel(self.channel_id, self.message_id, render_panel(snapshot))
        except Exception:
            self.failures = min(self.failures + 1, 6)
            self.next_retry_at = now + min(60, 2 ** self.failures)
            return False
        self.failures = 0
        self.next_retry_at = 0
        self.coalescer.last_render_at = now
        return True
