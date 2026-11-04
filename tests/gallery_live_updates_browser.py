#!/usr/bin/env python3
"""Check automatic gallery updates using browser-only fixtures, without writing server entries."""

import argparse
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from gallery_browser_smoke import fixtureEntry, fixtureIds, fixtureToken, screenshot


def installLiveFixture(page, imagePath):
    draft = fixtureEntry(2, "people", False)
    draft["images"] = []
    fixture = {"draft": draft, "public": [], "isRevoked": False, "requests": {}}
    image = imagePath.read_bytes()

    def respond(route):
        path = urlsplit(route.request.url).path
        fixture["requests"][path] = fixture["requests"].get(path, 0) + 1
        if "/images/" in path:
            return route.fulfill(status=200, content_type="image/png", body=image)
        if path == "/api/entries":
            return route.fulfill(status=200, json={"entries": fixture["public"]})
        if path == f"/api/preview/{fixtureToken}":
            return route.fulfill(status=200, json=fixture["draft"])
        if path == f"/api/entries/{fixtureIds[2]}" and not fixture["isRevoked"]:
            return route.fulfill(status=200, json=fixtureEntry(2, "people"))
        return route.fulfill(status=404, json={"error": "Not found."})

    page.route("**/api/**", respond)
    return fixture


def advancePoll(page):
    page.clock.fast_forward(4100)


def inspectDraftUpdates(page, fixture, baseUrl, output):
    page.goto(f"{baseUrl}/preview/{fixtureToken}", wait_until="networkidle")
    expect(page.get_by_text("Views are being prepared.")).to_be_visible()
    images = fixtureEntry(2, "people", False)["images"]
    for image in images:
        image["revision"] = "a" * 64
    fixture["draft"]["images"] = images
    advancePoll(page)
    expect(page.locator(".detail-image-frame img")).to_have_attribute("src", f"{images[0]['url']}&version={'a' * 64}")
    camera = page.get_by_role("button", name="Show camera 3")
    camera.click()
    camera.focus()
    page.evaluate("window.reviewImage = document.querySelector('.detail-image-frame img'); window.reviewFocus = document.activeElement")
    advancePoll(page)
    expect(camera).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("window.reviewImage === document.querySelector('.detail-image-frame img')"), "Unchanged poll replaced the image"
    assert page.evaluate("window.reviewFocus === document.activeElement"), "Unchanged poll reset focus"
    images[2]["revision"] = "b" * 64
    advancePoll(page)
    expect(page.locator(".detail-image-frame img")).to_have_attribute("src", f"{images[2]['url']}&version={'b' * 64}")
    expect(camera).to_have_attribute("aria-pressed", "true")
    expect(camera).to_be_focused()
    expect(page.get_by_text("Opening the gallery…")).to_have_count(0)
    screenshot(page, output, "draft-updated-automatically.png")


def inspectVisibilityAndNavigation(page, fixture, baseUrl):
    draftPath = f"/api/preview/{fixtureToken}"
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => true}); document.dispatchEvent(new Event('visibilitychange'))")
    beforeCount = fixture["requests"][draftPath]
    page.clock.fast_forward(12000)
    assert fixture["requests"][draftPath] == beforeCount, "Hidden tab continued polling"
    fixture["draft"]["images"][2]["revision"] = "c" * 64
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, get: () => false}); document.dispatchEvent(new Event('visibilitychange'))")
    expect(page.locator(".detail-image-frame img")).to_have_attribute("src", f"{fixture['draft']['images'][2]['url']}&version={'c' * 64}")
    page.get_by_role("link", name="All builds").click()
    expect(page.get_by_text("No submitted builds yet.")).to_be_visible()
    beforeCount = fixture["requests"][draftPath]
    fixture["public"] = [fixtureEntry(2, "people")]
    advancePoll(page)
    expect(page.locator(".build-card")).to_have_count(1)
    expect(page.locator(".entry-count")).to_have_text("1 BUILD")
    assert fixture["requests"][draftPath] == beforeCount, "Route change kept polling the private draft"


def inspectRevocation(page, fixture, output):
    page.locator(".build-card").click()
    expect(page.get_by_role("button", name="Show camera 1")).to_be_visible()
    fixture["isRevoked"] = True
    advancePoll(page)
    expect(page.get_by_text("This build is unavailable.")).to_be_visible()
    entryPath = f"/api/entries/{fixtureIds[2]}"
    requestCount = fixture["requests"][entryPath]
    page.clock.fast_forward(12000)
    assert fixture["requests"][entryPath] == requestCount, "Revoked entry continued polling"
    screenshot(page, output, "entry-withdrawn-automatically.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8788")
    parser.add_argument("--fixture-image", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("runtime/gallery-live-updates-review"))
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.clock.install()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        fixture = installLiveFixture(page, arguments.fixture_image)
        inspectDraftUpdates(page, fixture, arguments.base_url.rstrip("/"), arguments.output)
        inspectVisibilityAndNavigation(page, fixture, arguments.base_url.rstrip("/"))
        inspectRevocation(page, fixture, arguments.output)
        assert not errors, errors
        browser.close()
    print(f"Gallery automatic-update browser checks passed. Screenshots: {arguments.output}")


if __name__ == "__main__":
    main()
