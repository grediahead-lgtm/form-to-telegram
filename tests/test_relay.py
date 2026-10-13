import csv
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from form_relay.core import Relay  # noqa: E402
from form_relay.server import make_handler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

CFG = {"allowed_origins": ["https://ok.example"], "per_ip_per_hour": 3, "max_links": 1, "honeypot": "website"}
GOOD = {"name": "Ira", "phone": "+380501112233", "email": "", "message": "Need a quote"}


def relay(d, send=None, cfg=CFG):
    return Relay(cfg, os.path.join(d, "l.csv"), send, clock=lambda: dt.datetime(2026, 10, 13, 10, 0))


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class ValidationTests(unittest.TestCase):
    def test_good_lead_saved_and_sent(self):
        with tempfile.TemporaryDirectory() as d:
            sent = []
            r = relay(d, sent.append)
            self.assertEqual(r.accept(GOOD, "1.1.1.1"), (200, {"ok": True}))
            self.assertEqual(read(os.path.join(d, "l.csv"))[0]["name"], "Ira")
            self.assertIn("Need a quote", sent[0])

    def test_errors(self):
        with tempfile.TemporaryDirectory() as d:
            r = relay(d)
            for bad, text in (({"name": "I", "phone": "+380501112233"}, "name"), ({"name": "Ira"}, "phone or email"),
                              ({"name": "Ira", "phone": "123"}, "phone looks"), ({"name": "Ira", "email": "x@y"}, "email looks")):
                code, body = r.accept(bad, "ip%s" % text)
                self.assertEqual(code, 400, text)
                self.assertIn(text, body["error"])
            self.assertFalse(os.path.exists(os.path.join(d, "l.csv")))

    def test_honeypot_and_links_look_ok_but_store_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            r = relay(d)
            self.assertEqual(r.accept(dict(GOOD, website="http://spam"), "a")[0], 200)
            self.assertEqual(r.accept(dict(GOOD, message="http://a.example http://b.example"), "b")[0], 200)
            self.assertFalse(os.path.exists(os.path.join(d, "l.csv")))

    def test_rate_limit_per_ip(self):
        with tempfile.TemporaryDirectory() as d:
            r = relay(d)
            codes = [r.accept(GOOD, "9.9.9.9")[0] for _ in range(5)]
            self.assertEqual(codes, [200, 200, 200, 429, 429])
            self.assertEqual(r.accept(GOOD, "8.8.8.8")[0], 200)

    def test_telegram_failure_does_not_lose_the_lead(self):
        with tempfile.TemporaryDirectory() as d:
            def boom(text):
                raise RuntimeError("telegram down")
            r = relay(d, boom)
            self.assertEqual(r.accept(GOOD, "1.1.1.1")[0], 200)
            self.assertEqual(len(read(os.path.join(d, "l.csv"))), 1)

    def test_formula_guard_and_control_chars(self):
        with tempfile.TemporaryDirectory() as d:
            r = relay(d)
            r.accept(dict(GOOD, name="=cmd|' /C calc'!A0", message="a\x00b"), "1.1.1.1")
            row = read(os.path.join(d, "l.csv"))[0]
            self.assertTrue(row["name"].startswith("'="))
            self.assertEqual(row["message"], "ab")


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.relay = relay(self.tmp.name)
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.relay, CFG))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.srv.server_port

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def post(self, path, body, origin="https://ok.example", ctype="application/json"):
        req = urllib.request.Request(self.url + path, data=body, headers={"Content-Type": ctype, "Origin": origin}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read()), r.headers
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read()), e.headers
            finally:
                e.close()

    def test_json_and_form_encoded(self):
        code, body, headers = self.post("/submit", json.dumps(GOOD).encode())
        self.assertEqual((code, body), (200, {"ok": True}))
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://ok.example")
        code, _, _ = self.post("/submit", b"name=Oleg&phone=%2B380501112233&message=hi", ctype="application/x-www-form-urlencoded")
        self.assertEqual(code, 200)
        self.assertEqual(len(read(os.path.join(self.tmp.name, "l.csv"))), 2)

    def test_wrong_origin_path_size_and_body(self):
        self.assertEqual(self.post("/submit", json.dumps(GOOD).encode(), origin="https://evil.example")[0], 403)
        self.assertEqual(self.post("/other", b"{}")[0], 404)
        self.assertEqual(self.post("/submit", b"x" * 30000)[0], 413)
        self.assertEqual(self.post("/submit", b"[1,2]")[0], 400)
        self.assertEqual(self.post("/submit", b"{not json")[0], 400)

    def test_idle_connection_is_dropped(self):
        import socket
        import time
        self.assertEqual(make_handler(self.relay, CFG).timeout, 10)
        s = socket.create_connection(("127.0.0.1", self.srv.server_port))
        s.sendall(b"POST /submit HTTP/1.1\r\nContent-Length: 10\r\n\r\n")  # promises a body and never sends it
        s.settimeout(1)
        time.sleep(0.1)
        s.close()  # the server thread must not hang the test teardown

    def test_empty_allowed_origins_is_refused_at_start(self):
        from form_relay.__main__ import main
        cfgfile = os.path.join(self.tmp.name, "c.json")
        with open(cfgfile, "w", encoding="utf-8") as f:
            json.dump({"allowed_origins": []}, f)
        with self.assertRaises(ValueError):
            main(["--config", cfgfile, "--no-telegram"])

    def test_no_cors_header_for_foreign_origin(self):
        _, _, headers = self.post("/submit", json.dumps(GOOD).encode(), origin="https://evil.example")
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))


if __name__ == "__main__":
    unittest.main()
