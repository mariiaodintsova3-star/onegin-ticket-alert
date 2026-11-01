import asyncio
import re
from urllib.parse import urljoin

from playwright.async_api import async_playwright

SHOW_URL = "https://vakhtangov.ru/show/onegin/"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(locale="ru-RU")
        print(f"OPEN SHOW PAGE: {SHOW_URL}")
        response = await page.goto(SHOW_URL, wait_until="domcontentloaded", timeout=60000)
        print(f"SHOW STATUS: {response.status if response else 'no response'}")
        await page.wait_for_timeout(5000)

        links = await page.locator('a[href*="/tickets/buy/"]').evaluate_all(
            "(els) => els.map(a => ({text: (a.innerText || a.textContent || '').trim(), href: a.href}))"
        )
        unique = []
        seen = set()
        for item in links:
            if item["href"] not in seen:
                seen.add(item["href"])
                unique.append(item)

        print(f"PURCHASE LINKS FOUND: {len(unique)}")
        for item in unique:
            print(f"LINK: {item['text']} | {item['href']}")

        if not unique:
            print("No purchase links found. Current page text:")
            print((await page.locator("body").inner_text())[:5000])
            await browser.close()
            return

        for item in unique:
            ticket_page = await browser.new_page(locale="ru-RU")
            try:
                print("\n" + "=" * 70)
                print(f"INSPECT: {item['href']}")
                result = await ticket_page.goto(item["href"], wait_until="domcontentloaded", timeout=60000)
                print(f"STATUS: {result.status if result else 'no response'}")
                await ticket_page.wait_for_timeout(10000)
                print(f"TITLE: {await ticket_page.title()}")
                frames = ticket_page.frames
                print(f"FRAMES: {len(frames)}")
                for index, frame in enumerate(frames):
                    try:
                        frame_url = frame.url
                        text = (await frame.locator("body").inner_text(timeout=5000)).strip()
                        print(f"FRAME {index} URL: {frame_url}")
                        print(f"FRAME {index} TEXT: {re.sub(r'\\s+', ' ', text)[:2500]}")
                    except Exception as exc:
                        print(f"FRAME {index} READ ERROR: {type(exc).__name__}: {exc}")
                print("IFRAMES:")
                for frame in await ticket_page.locator("iframe").evaluate_all(
                    "(els) => els.map(e => e.src)"
                ):
                    print(frame)
            except Exception as exc:
                print(f"PAGE ERROR: {type(exc).__name__}: {exc}")
            finally:
                await ticket_page.close()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
