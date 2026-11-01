import asyncio
import re
from playwright.async_api import async_playwright

SHOW_URL = "https://vakhtangov.ru/show/onegin/"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(locale="ru-RU")
        interesting_responses = []

        def track_response(response):
            url = response.url
            if re.search(r"ticket|buy|order|event|afisha|widget|iframe|kassir|qtickets", url, re.I):
                interesting_responses.append((response.status, url))

        page.on("response", track_response)
        print(f"OPEN SHOW PAGE: {SHOW_URL}")
        response = await page.goto(SHOW_URL, wait_until="networkidle", timeout=60000)
        print(f"SHOW STATUS: {response.status if response else 'no response'}")
        await page.wait_for_timeout(3000)

        print("\nALL LINKS WITH TICKET/BUY/EVENT WORDS:")
        links = await page.locator("a[href]").evaluate_all(
            """els => els.map(a => ({
                text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' '),
                href: a.href
            })).filter(x => /ticket|buy|билет|купить|касс|event/i.test(x.text + ' ' + x.href))"""
        )
        for item in links[:100]:
            print(f"LINK: {item['text'][:160]} | {item['href']}")
        print(f"FILTERED LINKS COUNT: {len(links)}")

        print("\nBUTTONS:")
        buttons = await page.locator("button").evaluate_all(
            "els => els.map(b => (b.innerText || b.textContent || '').trim().replace(/\\s+/g, ' ')).filter(Boolean)"
        )
        for item in buttons[:80]:
            print(f"BUTTON: {item[:200]}")

        print("\nIFRAMES:")
        frames = await page.locator("iframe").evaluate_all("(els) => els.map(e => e.src)")
        for src in frames:
            print(src)

        print("\nRELEVANT NETWORK RESPONSES:")
        for status, url in interesting_responses[:100]:
            print(f"RESPONSE {status}: {url}")

        print("\nDATES AND AVAILABILITY TEXT:")
        body = re.sub(r"\\s+", " ", await page.locator("body").inner_text())
        for match in re.finditer(r".{0,100}(?:ноябр|декабр|январ|билет|19:00).{0,180}", body, re.I):
            print(match.group(0)[:300])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
