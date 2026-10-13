# form-to-telegram

A small server that receives **contact-form submissions from your website**, filters spam, saves each request to a CSV file and sends it to your Telegram. For sites that have a form but no back end. Python standard library only.

## What it does
- `POST /submit` accepts JSON or a normal form post: `name`, `phone`, `email`, `message`, `page`. A name and a phone or email are required; the phone must have 9 to 15 digits, the email must look like an email. Texts are trimmed and control characters removed.
- **Spam filters:** a hidden **honeypot** field (default `website`) that humans never fill; more than one link in the message; at most 5 requests per IP per hour. Spam gets an "ok" reply (so bots do not adapt) and **nothing is stored or sent**.
- **No lost leads:** the request is written to `leads.csv` first; if Telegram fails, the lead is still saved.
- **Browser safety:** only origins from `allowed_origins` get CORS headers and are accepted; bodies above 20 KB are refused; CSV cells starting with `=`, `+`, `-`, `@` get a leading `'` (no spreadsheet formulas). Logs never contain names, phones or messages.
- Token from `TELEGRAM_BOT_TOKEN` only.

## Use
```bash
cp examples/config.example.json config.json       # your site origin, chat_id, port
TELEGRAM_BOT_TOKEN=123456:your-token PYTHONPATH=src python3 -m form_relay --config config.json
PYTHONPATH=src python3 -m form_relay --config config.json --no-telegram     # CSV only
```
`examples/form.html` is a minimal form with the honeypot field. Put the server behind HTTPS (a reverse proxy such as Caddy or nginx) and, if the proxy sets the real client address in a header, name it in `trust_proxy_header`. Tests: `python3 -m unittest discover -s tests`.

## Limits (read this)
- The origin check stops other **websites** from using your form in a visitor's browser. It does not stop a script that sends a fake `Origin` header: the honeypot, link limit and per-IP limit are the defence against that. It is not a replacement for a captcha on a high-traffic site.
- The per-IP counter is in memory (reset on restart) and trusts the proxy header only if you configure it.
- No HTTPS inside the program, no authentication for reading `leads.csv`, one process, one CSV file.
- Telegram sending is a plain Bot API call, covered by tests with a fake sender, not against Telegram itself.

MIT license.

---

# form-to-telegram (українською)

Невеликий сервер, що приймає **заявки з форми на вашому сайті**, відсіює спам, записує їх у CSV і надсилає в Telegram. Лише стандартна бібліотека Python.

**Запуск:** `cp examples/config.example.json config.json`, вкажіть адресу сайту й `chat_id`, запустіть із `TELEGRAM_BOT_TOKEN`. Спам-пастка (приховане поле), ліміт посилань і запитів з однієї IP-адреси; заявка спершу зберігається в CSV, потім іде в Telegram.

**Важливо:** перевірка `Origin` не зупиняє скрипт, який підробляє заголовок; для сайтів із великим трафіком потрібна капча. HTTPS потрібно ставити окремо (reverse proxy).
