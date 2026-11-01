import asyncio
import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from playwright.async_api import async_playwright

SHOW_URL = "https://vakhtangov.ru/show/onegin/"
STATE_PATH = "monitor_state.json"
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "5007541897")


def api_request(url, method="GET", payload=None, token=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else {}


def load_state(repo, token):
    url = f"https://api.github.com/repos/{repo}/contents/{STATE_PATH}"
    try:
        item = api_request(url, token=token)
        content = base64.b64decode(item["content"]).decode("utf-8")
        return json.loads(content), item["sha"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"notified": False}, None
        raise


def save_state(repo, token, state, sha):
    url = f"https://api.github.com/repos/{repo}/contents/{STATE_PATH}"
    encoded = base64.b64encode((json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii")
    payload = {"message": "Record Onegin ticket alert state", "content": encoded}
    if sha:
        payload["sha"] = sha
    api_request(url, method="PUT", payload=payload, token=token)


def send_telegram(token, chat_id, dates):
    date_lines = "\n".join(f"• {d['date']} — {d['time']}" for d in dates)
    message = (
        "🎭 Похоже, появились билеты на «Евгения Онегина»!\n\n"
        f"{date_lines}\n\n"
        "Проверь наличие и покупай на официальной странице театра:\n"
        f"{SHOW_URL}"
    )
    payload = json.dumps({"chat_id": chat_id, "text": message, "disable_web_page_preview": False}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API returned an unsuccessful response: {result}")
    print("TELEGRAM NOTIFICATION SENT")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(locale="ru-RU")
        response = await page.goto(SHOW_URL, wait_until="domcontentloaded", timeout=60000)
        if not response or response.status != 200:
            raise RuntimeError(f"Official show page returned HTTP {response.status if response else 'no response'}")
        await page.wait_for_timeout(2500)

        buttons = await page.locator("a.js-buy-tickets-btn").evaluate_all("""els => els.map(a => ({
            datetime: a.getAttribute('data-datetime') || '',
            text: (a.innerText || a.textContent || '').trim(),
            href: a.getAttribute('href') || '',
            className: a.className || ''
        }))""")
        await browser.close()

    if not buttons:
        raise RuntimeError("No ticket buttons found; refusing to assume tickets are available.")

    dates = []
    available = []
    for button in buttons:
        raw = button["datetime"]
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})", raw)
        if not match:
            continue
        year, month, day, hour, minute = map(int, match.groups())
        date_label = f"{day:02d}.{month:02d}.{year}"
        time_label = f"{hour:02d}:{minute:02d}"
        is_available = (
            "disabled" not in button["className"].lower()
            and "закончились" not in button["text"].lower()
            and button["href"] not in ("", "#")
        )
        item = {"date": date_label, "time": time_label, "available": is_available}
        dates.append(item)
        if is_available:
            available.append(item)

    if not dates:
        raise RuntimeError("Ticket buttons were found, but their date identifiers could not be parsed.")

    print(f"CHECKED AT UTC: {datetime.utcnow().isoformat(timespec='seconds')}")
    print(f"SHOW STATUS: {response.status}")
    for item in dates:
        print(f"DATE {item['date']} {item['time']}: {'AVAILABLE' if item['available'] else 'SOLD OUT'}")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    github_token = os.getenv("GH_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")

    if not available:
        print("NO TICKETS AVAILABLE")
        return

    print(f"AVAILABLE DATES COUNT: {len(available)}")
    if not token:
        print("TELEGRAM_BOT_TOKEN is not configured; no message sent.")
        return
    if not github_token or not repo:
        raise RuntimeError("GH_TOKEN or GITHUB_REPOSITORY is missing; cannot safely prevent duplicate alerts.")

    state, sha = load_state(repo, github_token)
    if state.get("notified"):
        print("An alert was already sent earlier; skipping duplicate notification.")
        return

    send_telegram(token, CHAT_ID, available)
    state = {
        "notified": True,
        "notified_at_utc": datetime.utcnow().isoformat(timespec="seconds"),
        "dates": available,
    }
    save_state(repo, github_token, state, sha)
    print("ALERT STATE SAVED")


if __name__ == "__main__":
    asyncio.run(main())
