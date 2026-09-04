import json
import pytest
from owner_ops.discord_webhook import DiscordBindingError, DiscordWebhookTransport, validate_webhook_url
from owner_ops.runtime import snapshot
from owner_ops.runtime_sources import RuntimeSources

class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def read(self,_limit): return self.payload

class Opener:
    def __init__(self): self.calls=[]
    def open(self, request, timeout=0):
        self.calls.append((request.full_url, request.method, timeout, request.data))
        return Response({"id":"1234567890"})

def test_runtime_sources_bounded():
    readers=RuntimeSources().readers()
    assert set(readers)=={"system","task","control","budget","model","recovery","context","git","security"}
    assert all(isinstance(fn(),dict) for fn in readers.values())

def test_snapshot_not_canonical_truth():
    assert snapshot()["canonical_truth"] is False

@pytest.mark.parametrize("url",[
    "http://discord.com/api/webhooks/a/b",
    "https://evil.example/api/webhooks/a/b",
    "https://discord.com/not-webhooks/a/b",
])
def test_webhook_validation(url):
    with pytest.raises(DiscordBindingError): validate_webhook_url(url)

def test_mock_transport_only():
    opener=Opener()
    t=DiscordWebhookTransport("https://discord.com/api/webhooks/123/secret",opener=opener)
    mid=t.create_panel("hello")
    t.edit_panel("",mid,"updated")
    assert mid=="1234567890" and [c[1] for c in opener.calls]==["POST","PATCH"]

def test_secret_not_echoed():
    class Bad:
        def open(self,*_a,**_k): raise RuntimeError("network failed")
    secret="SUPER_SECRET_TOKEN_VALUE"
    t=DiscordWebhookTransport("https://discord.com/api/webhooks/123/"+secret,opener=Bad())
    with pytest.raises(DiscordBindingError) as exc: t.create_panel("x")
    assert secret not in str(exc.value)
