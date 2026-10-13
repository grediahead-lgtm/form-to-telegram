import argparse
import json
import os
import sys

from .core import Relay
from .server import serve
from .telegram_api import TelegramClient


def main(argv=None):
    ap = argparse.ArgumentParser(prog="form_relay")
    ap.add_argument("--config", required=True)
    ap.add_argument("--csv", default="leads.csv")
    ap.add_argument("--no-telegram", action="store_true", help="only save to CSV")
    args = ap.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("allowed_origins"):
        raise ValueError("config.allowed_origins must list your site (for example https://your-site.example)")
    send = None
    if not args.no_telegram:
        client = TelegramClient(os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        chat = cfg["chat_id"]
        send = lambda text: client.send(chat, text)
    print("listening on %s:%s" % (cfg.get("host", "127.0.0.1"), cfg.get("port", 8787)))
    serve(Relay(cfg, args.csv, send), cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
