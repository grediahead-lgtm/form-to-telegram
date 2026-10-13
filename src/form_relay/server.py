import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 20_000


def make_handler(relay, cfg):
    origins = set(cfg.get("allowed_origins", []))
    trust_proxy = bool(cfg.get("trust_proxy_header"))

    class H(BaseHTTPRequestHandler):
        def _cors(self):
            o = self.headers.get("Origin", "")
            if o in origins:
                self.send_header("Access-Control-Allow-Origin", o)
                self.send_header("Vary", "Origin")

        def _reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            if self.path != "/submit":
                return self._reply(404, {"ok": False, "error": "not found"})
            o = self.headers.get("Origin", "")
            if origins and o not in origins:  # browsers send Origin; plain scripts are not blocked by this (see README)
                return self._reply(403, {"ok": False, "error": "origin not allowed"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if not 0 < n <= MAX_BODY:
                return self._reply(413, {"ok": False, "error": "bad size"})
            raw = self.rfile.read(n)
            ctype = self.headers.get("Content-Type", "")
            try:
                if "json" in ctype:
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError
                else:
                    data = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8")).items()}
            except (ValueError, UnicodeDecodeError):
                return self._reply(400, {"ok": False, "error": "bad body"})
            ip = self.client_address[0]
            if trust_proxy:
                ip = self.headers.get(cfg["trust_proxy_header"], ip).split(",")[0].strip() or ip
            code, body = relay.accept(data, ip)
            self._reply(code, body)

        def log_message(self, *a):
            pass  # no names, phones or messages in logs

    return H


def serve(relay, cfg):
    srv = ThreadingHTTPServer((cfg.get("host", "127.0.0.1"), cfg.get("port", 8787)), make_handler(relay, cfg))
    srv.serve_forever()
