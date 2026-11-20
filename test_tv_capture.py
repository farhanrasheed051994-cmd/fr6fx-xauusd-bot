import os
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def capture_charts():
    os.makedirs("assets", exist_ok=True)
    html_uri = Path("tv_chart.html").resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 540x620 viewport at 2x Retina scale = ultra-sharp 1080x1240 chart card
        context = await browser.new_context(
            viewport={"width": 540, "height": 620},
            device_scale_factor=2
        )
        page = await context.new_page()

        # 1. Capture 15-Minute TradingView Chart
        await page.goto(f"{html_uri}?interval=15", wait_until="networkidle")
        await page.wait_for_timeout(5000)  # Wait for live WebSocket candles & countdown
        await page.screenshot(path="assets/tv_15m.png")
        print("✅ Captured assets/tv_15m.png")

        # 2. Capture 5-Minute TradingView Chart
        await page.goto(f"{html_uri}?interval=5", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="assets/tv_5m.png")
        print("✅ Captured assets/tv_5m.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_charts())
