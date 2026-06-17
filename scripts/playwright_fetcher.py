#!/usr/bin/env python3
"""
to-study — Playwright Dynamic Page Fetcher
Uses Playwright (Chromium) via CDP to render and extract content from SPA / JS-heavy pages.

Dependencies: playwright (pip install playwright && playwright install chromium)
"""

import os
import re
import json
import asyncio
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass, field, asdict

try:
    from playwright.async_api import async_playwright, TimeoutError as PwTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False


@dataclass
class DynamicPage:
    """Result from Playwright dynamic page fetch."""
    url: str
    title: str = ""
    content: str = ""
    html: str = ""
    screenshot_path: Optional[str] = None
    word_count: int = 0
    wait_strategy: str = "networkidle"
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class PlaywrightFetcher:
    """
    Fetch and extract content from dynamic / JS-rendered web pages.
    
    Wait strategies:
      - "networkidle": Wait until no network requests for 500ms
      - "load": Wait for 'load' event only
      - "domcontentloaded": Wait for DOMContentLoaded
      - "selector:<css>": Wait for a specific element to appear
      - "timeout:<ms>": Fixed wait after load
    """

    CONTENT_SELECTORS = [
        "article",
        "main",
        '[role="main"]',
        ".content",
        ".post-body",
        ".article-content",
        ".markdown-body",
        "#content",
        "#article",
        ".post-content",
        ".entry-content",
        ".blog-post",
    ]

    def __init__(self, headless: bool = True, timeout: int = 30000):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
        self.headless = headless
        self.timeout = timeout

    def fetch(self, url: str, wait_strategy: str = "networkidle",
              screenshot: bool = True, output_dir: Optional[str] = None) -> DynamicPage:
        """Synchronous wrapper for async fetch."""
        return asyncio.run(self._fetch_async(url, wait_strategy, screenshot, output_dir))

    async def _fetch_async(self, url: str, wait_strategy: str,
                           screenshot: bool, output_dir: Optional[str]) -> DynamicPage:
        """Async core: render page, extract content, optionally screenshot."""
        result = DynamicPage(url=url, wait_strategy=wait_strategy)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(self.timeout)

            try:
                # Navigate
                await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)

                # Apply wait strategy
                await self._apply_wait(page, wait_strategy)

                # Extract
                result.title = await page.title()
                result.content = await self._extract_content(page)
                result.word_count = len(result.content)
                result.html = await page.content()

                # Screenshot
                if screenshot:
                    result.screenshot_path = await self._take_screenshot(
                        page, url, output_dir
                    )

                result.error = None

            except PwTimeout:
                result.error = f"Timeout after {self.timeout}ms with strategy '{wait_strategy}'"
            except Exception as e:
                result.error = f"{type(e).__name__}: {e}"
            finally:
                await browser.close()

        return result

    async def _apply_wait(self, page, strategy: str):
        """Apply the specified wait strategy."""
        if strategy == "networkidle":
            await page.wait_for_load_state("networkidle", timeout=self.timeout)
        elif strategy == "load":
            await page.wait_for_load_state("load", timeout=self.timeout)
        elif strategy == "domcontentloaded":
            pass  # Already waited during goto
        elif strategy.startswith("selector:"):
            selector = strategy[len("selector:"):]
            await page.wait_for_selector(selector, timeout=self.timeout)
        elif strategy.startswith("timeout:"):
            ms = int(strategy[len("timeout:"):])
            await page.wait_for_timeout(ms)
        else:
            # Default: networkidle
            try:
                await page.wait_for_load_state("networkidle", timeout=self.timeout)
            except PwTimeout:
                pass  # Best effort

    async def _extract_content(self, page) -> str:
        """Extract readable content using progressive selectors."""
        # Try each content selector
        for selector in self.CONTENT_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    if text and len(text.strip()) > 200:
                        return self._clean_text(text)
            except Exception:
                continue

        # Fallback: full body text
        try:
            body = await page.query_selector("body")
            if body:
                text = await body.inner_text()
                return self._clean_text(text)
        except Exception:
            pass

        # Last resort: evaluate JS
        try:
            text = await page.evaluate("() => document.body?.innerText || ''")
            return self._clean_text(text)
        except Exception:
            return ""

    async def _take_screenshot(self, page, url: str,
                                output_dir: Optional[str]) -> Optional[str]:
        """Take a full-page screenshot and save to disk."""
        if output_dir:
            out = Path(output_dir)
        else:
            out = Path(tempfile.gettempdir()) / "to-study-screenshots"

        out.mkdir(parents=True, exist_ok=True)

        # Safe filename from URL
        safe = re.sub(r'[<>:"/\\|?*#]', "_", url)[:80]
        filename = f"{safe}.png"
        filepath = out / filename

        await page.screenshot(path=str(filepath), full_page=True)
        return str(filepath)

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalize whitespace in extracted text."""
        lines = []
        prev_empty = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if not prev_empty:
                    lines.append("")
                    prev_empty = True
            else:
                lines.append(stripped)
                prev_empty = False
        return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description="to-study Playwright Dynamic Page Fetcher")
    parser.add_argument("url", help="URL of the dynamic page to fetch")
    parser.add_argument("-w", "--wait", default="networkidle",
                        help="Wait strategy: networkidle|load|domcontentloaded|selector:<css>|timeout:<ms>")
    parser.add_argument("-s", "--screenshot", action="store_true",
                        help="Take full-page screenshot")
    parser.add_argument("-o", "--output", default=None,
                        help="Screenshot output directory")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show browser window (not headless)")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    parser.add_argument("--timeout", type=int, default=30000,
                        help="Page timeout in ms (default: 30000)")
    args = parser.parse_args()

    try:
        fetcher = PlaywrightFetcher(
            headless=not args.no_headless,
            timeout=args.timeout
        )
        result = fetcher.fetch(
            url=args.url,
            wait_strategy=args.wait,
            screenshot=args.screenshot,
            output_dir=args.output,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}")
        exit(1)

    if args.json:
        print(result.to_json())
    else:
        if result.error:
            print(f"ERROR: {result.error}")
        else:
            print(f"Title: {result.title}")
            print(f"URL: {result.url}")
            print(f"Wait: {result.wait_strategy}")
            print(f"Words: {result.word_count}")
            if result.screenshot_path:
                print(f"Screenshot: {result.screenshot_path}")
            print(f"\n--- Content Preview (first 800 chars) ---")
            print(result.content[:800])