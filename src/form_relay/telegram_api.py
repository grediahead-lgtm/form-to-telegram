"""Minimal Telegram Bot API client over urllib (long polling)."""
import json
import os
import ssl
import urllib.parse
import urllib.request


def _ssl_context():
    for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(p):
            return ssl.create_default_context(cafile=p)
    return ssl.create_default_context()


class TelegramClient:
    def __init__(self, token, opener=None, base="https://api.telegram.org"):
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set")
        self.url = "%s/bot%s/" % (base, token)
        self.opener = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()))

    def call(self, method, params=None, timeout=40):
        data = urllib.parse.urlencode(params or {}).encode("utf-8")
        with self.opener.open(urllib.request.Request(self.url + method, data=data), timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
        if not res.get("ok"):
            raise RuntimeError("telegram error: %s" % res.get("description", "unknown"))
        return res["result"]

    def updates(self, offset):
        return self.call("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": '["message"]'}, timeout=45)

    def send(self, chat_id, text):
        self.call("sendMessage", {"chat_id": chat_id, "text": text})
