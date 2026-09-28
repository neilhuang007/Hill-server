#!/usr/bin/env python3
"""Capture a deterministic BlueMap browser view for reconstruction QA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--view", default="", help="BlueMap hash, with or without leading #")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1000)
    parser.add_argument("--settle-ms", type=int, default=12_000)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    view = args.view
    if view and not view.startswith("#"):
        view = f"#{view}"
    target_url = f"{args.url.rstrip('/')}/{view}"
    console_messages: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=1,
        )
        page.on(
            "console",
            lambda message: console_messages.append(f"{message.type}: {message.text}"),
        )
        page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeoutError:
            # BlueMap's live EventSource keeps some otherwise-complete views active.
            pass
        page.wait_for_timeout(args.settle_ms)
        canvas_count = page.locator("canvas").count()
        if canvas_count == 0:
            raise RuntimeError("BlueMap did not render a canvas")
        page.screenshot(path=str(output), full_page=True)
        payload = {
            "url": page.url,
            "title": page.title(),
            "canvas_count": canvas_count,
            "output": str(output),
            "console_errors": [
                message for message in console_messages if message.startswith("error:")
            ],
        }
        browser.close()

    print(json.dumps(payload, indent=2))
    return 0 if not payload["console_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
