"""Form validation, spam filtering and storage. Pure logic, no network."""
import csv
import os
import re
import time
import datetime as dt

FIELDS = ["received_at", "name", "phone", "email", "message", "page"]
EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}")
LINKS = re.compile(r"https?://|www\.", re.I)


def clean(v, n):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v or "")).strip()[:n]


class Relay:
    def __init__(self, cfg, csv_path, send=None, now=time.monotonic, clock=dt.datetime.now):
        self.cfg, self.csv_path, self.send, self.now, self.clock = cfg, csv_path, send, now, clock
        self.hits = {}

    def limited(self, ip):
        t = self.now()
        h = [x for x in self.hits.get(ip, []) if t - x < 3600] + [t]
        self.hits[ip] = h
        if len(self.hits) > 5000:  # do not let the table grow forever
            self.hits = {k: v for k, v in self.hits.items() if v and t - v[-1] < 3600}
        return len(h) > self.cfg.get("per_ip_per_hour", 5)

    def validate(self, data):
        """Returns (record, error). A filled honeypot field returns (None, 'spam') and is dropped silently by the caller."""
        if clean(data.get(self.cfg.get("honeypot", "website")), 200):
            return None, "spam"
        rec = {"name": clean(data.get("name"), 80), "phone": clean(data.get("phone"), 30), "email": clean(data.get("email"), 120),
               "message": clean(data.get("message"), 2000), "page": clean(data.get("page"), 200)}
        if len(rec["name"]) < 2:
            return None, "name is required"
        digits = re.sub(r"\D", "", rec["phone"])
        if not rec["email"] and not digits:
            return None, "phone or email is required"
        if rec["phone"] and not 9 <= len(digits) <= 15:
            return None, "phone looks wrong"
        if rec["email"] and not EMAIL.fullmatch(rec["email"]):
            return None, "email looks wrong"
        if len(LINKS.findall(rec["message"])) > self.cfg.get("max_links", 1):
            return None, "spam"
        return rec, None

    def accept(self, data, ip):
        """Returns (status_code, body_dict)."""
        if self.limited(ip):
            return 429, {"ok": False, "error": "too many requests"}
        rec, err = self.validate(data)
        if err == "spam":
            return 200, {"ok": True}  # look successful to bots, store nothing
        if err:
            return 400, {"ok": False, "error": err}
        rec["received_at"] = self.clock().isoformat(timespec="seconds")
        self.store(rec)
        if self.send:
            try:
                self.send("New request\n%s\n%s\n%s\n\n%s" % (rec["name"], rec["phone"], rec["email"], rec["message"]))
            except Exception:  # the lead is already saved; a Telegram failure must not lose it
                pass
        return 200, {"ok": True}

    def store(self, rec):
        new = not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: ("'" + v if v.startswith(("=", "+", "-", "@")) else v) for k, v in rec.items()})
