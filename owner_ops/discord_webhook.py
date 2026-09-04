from __future__ import annotations
import json
import urllib.parse
import urllib.request

_ALLOWED_HOSTS = frozenset({"discord.com", "www.discord.com", "discordapp.com", "www.discordapp.com"})

class DiscordBindingError(RuntimeError):
    pass

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DiscordBindingError("Discord webhook redirect blocked")

def validate_webhook_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise DiscordBindingError("invalid webhook URL")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise DiscordBindingError("untrusted Discord webhook host")
    if not parsed.path.startswith("/api/webhooks/"):
        raise DiscordBindingError("invalid Discord webhook path")
    if parsed.username or parsed.password or parsed.fragment:
        raise DiscordBindingError("invalid webhook URL components")
    return url

class DiscordWebhookTransport:
    def __init__(self, webhook_url, opener=None, timeout=10):
        self._url = validate_webhook_url(webhook_url)
        self._opener = opener or urllib.request.build_opener(_NoRedirect)
        self._timeout = max(2, min(int(timeout), 30))

    def _request(self, method, url, payload):
        validate_webhook_url(url.split("/messages/", 1)[0])
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method=method,
            headers={"Content-Type":"application/json","User-Agent":"DARWIN-ZERO0-OwnerOps/1"},
        )
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                raw = resp.read(64 * 1024)
                if not raw:
                    return {}
                result = json.loads(raw.decode("utf-8"))
                return result if isinstance(result, dict) else {}
        except DiscordBindingError:
            raise
        except Exception as exc:
            raise DiscordBindingError(type(exc).__name__) from exc

    def create_panel(self, content):
        result = self._request("POST", self._url + "?wait=true", {"content": str(content)[:1900]})
        message_id = str(result.get("id", ""))
        if not message_id.isdigit():
            raise DiscordBindingError("Discord did not return a valid message id")
        return message_id

    def edit_panel(self, channel_id, message_id, content):
        if not str(message_id).isdigit():
            raise DiscordBindingError("invalid panel message id")
        self._request("PATCH", self._url + "/messages/" + str(message_id), {"content": str(content)[:1900]})
