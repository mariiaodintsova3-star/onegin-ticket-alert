import asyncio
import json
import re
from playwright.async_api import async_playwright

SHOW_URL = "https://vakhtangov.ru/show/onegin/"
DATA_URL = "https://vakhtangov.ru/ticketland_afisha/data.json"


def find_onegin_records(value, path="root"):
    """Walk nested JSON and JSON-encoded strings; return records mentioning Onegin."""
    found = []
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                found.extend(find_onegin_records(json.loads(stripped), path + ".<json>"))
            except Exception:
                pass
        return found
    if isinstance(value, dict):
        searchable = " ".join(str(v) for k, v in value.items() if k.lower() in {"title", "name", "event", "performance"})
        if re.search(r"онегин|onegin", searchable, re.I):
            found.append((path, value))
        for key, child in value.items():
            found.extend(find_onegin_records(child, path + "." + str(key)))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            found.extend(find_onegin_records(child, f"{path}[{i}]"))
    return found


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(locale="ru-RU")
        interesting_responses = []

        def track_response(response):
            if re.search(r"ticket|buy|order|event|afisha|widget|iframe|kassir|qtickets", response.url, re.I):
                interesting_responses.append((response.status, response.url))

        page.on("response", track_response)
        print(f"OPEN SHOW PAGE: {SHOW_URL}")
        response = await page.goto(SHOW_URL, wait_until="domcontentloaded", timeout=60000)
        print(f"SHOW STATUS: {response.status if response else 'no response'}")
        await page.wait_for_timeout(3000)

        print("\\nALL LINKS WITH TICKET/BUY/EVENT WORDS:")
        links = await page.locator("a[href]").evaluate_all(
            """els => els.map(a => ({
                text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' '),
                href: a.href
            })).filter(x => /ticket|buy|билет|купить|касс|event/i.test(x.text + ' ' + x.href))"""
        )
        for item in links[:100]:
            print(f"LINK: {item['text'][:160]} | {item['href']}")
        print(f"FILTERED LINKS COUNT: {len(links)}")

        print("\\nTICKET LINK MARKUP:")
        sold_out_links = page.locator("a").filter(has_text="Билеты закончились")
        for idx in range(await sold_out_links.count()):
            link = sold_out_links.nth(idx)
            print(f"SOLD OUT LINK {idx}: {await link.evaluate('(el) => el.outerHTML')}")
            parent_html = await link.evaluate('(el) => el.parentElement?.parentElement?.outerHTML || el.parentElement?.outerHTML || ""')
            print(f"SOLD OUT PARENT {idx}: {parent_html[:4000]}")

        print("\\nIFRAMES:")
        for src in await page.locator("iframe").evaluate_all("(els) => els.map(e => e.src)"):
            print(src)

        print("\\nTICKETLAND DATA JSON:")
        data_response = await page.request.get(DATA_URL)
        print(f"DATA STATUS: {data_response.status}")
        data_json = await data_response.json()
        matches = find_onegin_records(data_json)
        print(f"ONEGIN MATCH COUNT: {len(matches)}")
        for path, record in matches[:100]:
            compact = {k: record.get(k) for k in ("title", "start_date", "has_tickets", "sales_on", "reveal_dt", "hall_id") if k in record}
            print("ONEGIN RECORD:", json.dumps({"path": path, **compact}, ensure_ascii=False))

        print("\\nRELEVANT NETWORK RESPONSES:")
        for status, url in interesting_responses[:100]:
            print(f"RESPONSE {status}: {url}")

        print("\\nDATES AND AVAILABILITY TEXT:")
        body = re.sub(r"\\s+", " ", await page.locator("body").inner_text())
        for match in re.finditer(r".{0,100}(?:ноябр|декабр|январ|билет|19:00).{0,180}", body, re.I):
            print(match.group(0)[:300])
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
