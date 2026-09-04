from __future__ import annotations
import hashlib
import json
import time
from collections import OrderedDict
from .model import OwnerEvent

def fingerprint(event: OwnerEvent) -> str:
    body = json.dumps(
        {"kind": event.kind, "payload": event.payload, "severity": event.severity},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

class EventCoalescer:
    def __init__(self, min_interval_seconds=5, heartbeat_seconds=60, max_queue=256, clock=None):
        if min_interval_seconds < 3 or heartbeat_seconds < 60 or max_queue < 8 or max_queue > 4096:
            raise ValueError("unsafe event coalescer configuration")
        self.min_interval = int(min_interval_seconds)
        self.heartbeat = int(heartbeat_seconds)
        self.max_queue = int(max_queue)
        self.clock = clock or time.time
        self._events = OrderedDict()
        self._seen = OrderedDict()
        self.last_render_at = 0

    def push(self, event: OwnerEvent) -> bool:
        event.validate()
        digest = fingerprint(event)
        if event.event_id in self._seen or digest in self._seen:
            return False
        self._seen[event.event_id] = None
        self._seen[digest] = None
        while len(self._seen) > self.max_queue * 4:
            self._seen.popitem(last=False)
        self._events[event.kind] = event
        self._events.move_to_end(event.kind)
        while len(self._events) > self.max_queue:
            self._events.popitem(last=False)
        return True

    @property
    def queued(self):
        return len(self._events)

    def ready(self) -> bool:
        return bool(self._events) and int(self.clock()) - self.last_render_at >= self.min_interval

    def drain(self):
        if not self.ready():
            return []
        out = list(self._events.values())
        self._events.clear()
        self.last_render_at = int(self.clock())
        return out

    def heartbeat_due(self) -> bool:
        return int(self.clock()) - self.last_render_at >= self.heartbeat

class AlertDeduplicator:
    def __init__(self, ttl_seconds=300, max_entries=1024, clock=None):
        if ttl_seconds < 30 or max_entries < 32:
            raise ValueError("unsafe alert deduplicator configuration")
        self.ttl = int(ttl_seconds)
        self.max_entries = int(max_entries)
        self.clock = clock or time.time
        self._seen = OrderedDict()

    def allow(self, event: OwnerEvent) -> bool:
        digest = fingerprint(event)
        now = int(self.clock())
        for key, seen in list(self._seen.items()):
            if now - seen >= self.ttl:
                self._seen.pop(key, None)
        if digest in self._seen:
            return False
        self._seen[digest] = now
        while len(self._seen) > self.max_entries:
            self._seen.popitem(last=False)
        return True
