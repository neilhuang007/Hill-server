#!/usr/bin/env python3
"""Exercise the local gallery in Chromium. --fixtures only intercepts this browser's API requests."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


fixtureIds = ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333"]
fixtureToken = "browser_fixture_private_token_123456"


def fixtureEntry(index, category, isSubmitted=True):
    entryId = fixtureIds[index]
    tokenQuery = "" if isSubmitted else f"?token={fixtureToken}"
    return {
        "id": entryId, "title": f"Browser test fixture {index + 1}", "category": category,
        "submitted": isSubmitted,
        "images": [{"slot": slot, "url": f"/api/entries/{entryId}/images/{slot}{tokenQuery}"} for slot in range(1, 4)],
    }


def installFixtures(page, imagePath):
    entries = [fixtureEntry(0, "journey"), fixtureEntry(1, "place")]
    privateEntry = fixtureEntry(2, "people", False)
    image = imagePath.read_bytes()

    def respond(route):
        path = route.request.url.split("/api/", 1)[1].split("?", 1)[0]
        if "/images/" in path:
            return route.fulfill(status=200, content_type="image/png", body=image)
        if path == "entries":
            return route.fulfill(status=200, json={"entries": entries})
        if path == f"preview/{fixtureToken}":
            return route.fulfill(status=200, json=privateEntry)
        for entry in entries:
            if path == f"entries/{entry['id']}":
                return route.fulfill(status=200, json=entry)
        route.fulfill(status=404, json={"error": "Not found."})

    page.route("**/api/**", respond)


def screenshot(page, output, name):
    page.evaluate("window.scrollTo({top: 0, left: 0, behavior: 'instant'})")
    page.screenshot(path=str(output / name), full_page=True)


def assertLayout(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal page overflow"


def inspectActualEntry(page, output, isMobile=False):
    if not page.locator(".build-card").count():
        return
    page.locator(".build-card").first.click()
    expect(page.locator("main")).to_have_attribute("aria-busy", "false")
    buttons = page.locator(".camera-button")
    cameraCount = buttons.count()
    assert 1 <= cameraCount <= 3, "Submitted entry must have one to three camera views"
    for index in range(cameraCount):
        buttons.nth(index).click()
        expect(buttons.nth(index)).to_have_attribute("aria-pressed", "true")
        page.locator(".detail-image-frame img").wait_for(state="visible")
        page.wait_for_function("() => document.querySelector('.detail-image-frame img')?.naturalWidth > 0")
    assertLayout(page)
    screenshot(page, output, "gallery-entry-mobile.png" if isMobile else "gallery-entry-desktop.png")
    page.reload(wait_until="networkidle")
    expect(page.locator(".camera-button")).to_have_count(cameraCount)


def inspectGallery(page, baseUrl, output, hasFixtures):
    page.goto(f"{baseUrl}/gallery", wait_until="networkidle")
    expect(page.locator("main")).to_have_attribute("aria-busy", "false")
    expect(page.get_by_role("heading", name="Build gallery.")).to_be_visible()
    assertLayout(page)
    screenshot(page, output, "gallery-desktop.png")
    if not hasFixtures:
        inspectActualEntry(page, output)
        return
    expect(page.locator(".build-card")).to_have_count(2)
    assert fixtureToken not in page.content(), "Private draft leaked into public gallery"
    page.get_by_role("button", name="Journey", exact=True).click()
    expect(page.locator(".build-card")).to_have_count(1)
    page.get_by_role("button", name="People", exact=True).click()
    expect(page.get_by_text("No submitted builds yet.")).to_be_visible()
    page.get_by_role("button", name="All builds", exact=True).click()
    page.locator(".build-card").first.focus()
    page.keyboard.press("Enter")
    expect(page).to_have_url(f"{baseUrl}/entries/{fixtureIds[0]}")
    expect(page.get_by_role("button", name="Show camera 1")).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="Show camera 3").focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("button", name="Show camera 3")).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".detail-caption")).to_contain_text("3 / 3")
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("heading", name="Browser test fixture 1")).to_be_visible()
    screenshot(page, output, "gallery-entry-desktop.png")
    page.goto(f"{baseUrl}/preview/{fixtureToken}", wait_until="networkidle")
    expect(page.get_by_text("PRIVATE DRAFT", exact=True)).to_be_visible()
    expect(page.locator(".detail-image-frame img")).to_have_attribute("src", f"/api/entries/{fixtureIds[2]}/images/1?token={fixtureToken}")
    screenshot(page, output, "gallery-private-desktop.png")
    page.goto(f"{baseUrl}/entries/{fixtureIds[2]}", wait_until="networkidle")
    expect(page.get_by_text("This build is unavailable.", exact=True)).to_be_visible()
    page.goto(f"{baseUrl}/gallery", wait_until="networkidle")
    page.get_by_role("button", name="All builds", exact=True).click()
    expect(page.locator(".build-card")).to_have_count(2)
    page.route("**/api/entries", lambda route: route.fulfill(status=200, json={"entries": []}))
    page.reload(wait_until="networkidle")
    expect(page.locator(".build-card")).to_have_count(0)
    page.unroute("**/api/entries")
    page.reload(wait_until="networkidle")
    expect(page.locator(".build-card")).to_have_count(2)


def inspectFailureStates(page, baseUrl, output):
    page.unroute("**/api/**")
    page.route("**/api/entries", lambda route: route.fulfill(status=503, json={"error": "Fixture unavailable"}))
    page.goto(f"{baseUrl}/gallery", wait_until="networkidle")
    expect(page.get_by_role("alert")).to_contain_text("The gallery is resting.")
    page.unroute("**/api/entries")
    page.route("**/api/entries", lambda route: route.fulfill(status=200, json={"entries": []}))
    page.get_by_role("button", name="Try again").click()
    expect(page.get_by_text("No submitted builds yet.")).to_be_visible()
    screenshot(page, output, "gallery-empty.png")
    page.unroute("**/api/entries")
    unsafeEntry = fixtureEntry(0, "journey")
    unsafeEntry["title"] = "<img src=x onerror=alert(1)>"
    unsafeEntry["images"] = [{"slot": 1, "url": "https://example.invalid/leak"}]
    page.route("**/api/entries", lambda route: route.fulfill(status=200, json={"entries": [unsafeEntry]}))
    page.reload(wait_until="networkidle")
    expect(page.get_by_role("heading", name=unsafeEntry["title"], exact=True)).to_be_visible()
    expect(page.locator(".build-card img")).to_have_count(0)
    page.unroute("**/api/entries")


def inspectLoadingAndMissingImage(page, baseUrl, output, imagePath):
    page.unroute("**/api/**")
    pendingRoutes = []
    page.route("**/api/entries", lambda route: pendingRoutes.append(route))
    page.goto(f"{baseUrl}/gallery", wait_until="domcontentloaded")
    expect(page.get_by_role("status")).to_contain_text("Opening the gallery…")
    screenshot(page, output, "gallery-loading.png")
    assert len(pendingRoutes) == 1
    pendingRoutes[0].fulfill(status=200, json={"entries": []})
    expect(page.get_by_text("No submitted builds yet.")).to_be_visible()
    page.unroute("**/api/entries")
    installFixtures(page, imagePath)
    page.route("**/api/entries/*/images/*", lambda route: route.fulfill(status=404, body="Not found."))
    page.goto(f"{baseUrl}/entries/{fixtureIds[0]}", wait_until="networkidle")
    expect(page.locator(".detail-image-frame")).to_contain_text("This view is unavailable.")
    screenshot(page, output, "gallery-missing-image.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8788")
    parser.add_argument("--output", type=Path, default=Path("runtime/gallery-browser-review"))
    parser.add_argument("--fixture-image", type=Path, help="Enables explicitly labeled browser-only fixtures using this test image")
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    baseUrl = arguments.base_url.rstrip("/")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        if arguments.fixture_image:
            installFixtures(page, arguments.fixture_image)
        inspectGallery(page, baseUrl, arguments.output, bool(arguments.fixture_image))
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{baseUrl}/gallery", wait_until="networkidle")
        assertLayout(page)
        screenshot(page, arguments.output, "gallery-mobile.png")
        if not arguments.fixture_image:
            inspectActualEntry(page, arguments.output, True)
        if arguments.fixture_image:
            page.locator(".build-card").first.click()
            expect(page.get_by_role("button", name="Show camera 2")).to_be_visible()
            page.get_by_role("button", name="Show camera 2").click()
            expect(page.locator(".detail-caption")).to_contain_text("2 / 3")
            assertLayout(page)
            screenshot(page, arguments.output, "gallery-entry-mobile.png")
            inspectFailureStates(page, baseUrl, arguments.output)
            inspectLoadingAndMissingImage(page, baseUrl, arguments.output, arguments.fixture_image)
        assert not errors, json.dumps(errors)
        browser.close()
    print(f"Gallery browser smoke passed ({'browser-only fixtures' if arguments.fixture_image else 'actual backend'}). Screenshots: {arguments.output}")


if __name__ == "__main__":
    main()
