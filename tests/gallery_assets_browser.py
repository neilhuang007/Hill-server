#!/usr/bin/env python3
"""Review actual gallery entries, original sprite fills, divider pixels and the local Minecraft font."""

import argparse
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def overrideSource(page, assets):
    resources = {"/gallery.css": (Path("src/main/resources/gallery/gallery.css"), "text/css"),
                 "/gallery.js": (Path("src/main/resources/gallery/gallery.js"), "text/javascript")}

    def respond(route):
        path = urlsplit(route.request.url).path
        if path in resources:
            source, contentType = resources[path]
            return route.fulfill(status=200, content_type=contentType, body=source.read_bytes())
        if path.startswith("/assets/") and path.count("/") == 2:
            source = assets / path.rsplit("/", 1)[1]
            if source.is_file():
                contentType = "font/woff2" if source.suffix == ".woff2" else "image/png"
                return route.fulfill(status=200, content_type=contentType, body=source.read_bytes())
        route.continue_()

    page.route("**/*", respond)


def inspectFont(page):
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.fonts.check('16px MinecraftBitmap')"), "Minecraft font is unavailable"
    assert page.evaluate("[...document.fonts].some(font => font.family === 'MinecraftBitmap' && font.status === 'loaded')"), "Actual Minecraft font did not load"
    widths = page.evaluate("""() => {
      const context = document.createElement('canvas').getContext('2d');
      context.font = '16px MinecraftBitmap';
      return {narrow: context.measureText('iiii').width, wide: context.measureText('WWWW').width};
    }""")
    assert widths["wide"] > widths["narrow"] * 1.5, "Minecraft's original variable glyph advances are missing"


def inspectButton(page, button, output, name, expectedCenter):
    expect(button).to_be_visible()
    slices = button.evaluate("element => getComputedStyle(element, '::before').borderImageSlice")
    assert "fill" in slices, f"{name}: missing original center fill"
    pixels = Image.open(BytesIO(button.screenshot(path=str(output / f"button-{name}.png")))).convert("RGB")
    actual = pixels.getpixel((pixels.width // 2, 14))
    assert actual == expectedCenter, f"{name}: original center {expectedCenter}, rendered {actual}"


def inspectButtonStates(page, output):
    button = page.get_by_role("button", name="Journey", exact=True)
    page.mouse.move(1400, 20)
    page.evaluate("document.activeElement.blur()")
    inspectButton(page, button, output, "normal", (55, 50, 42))
    button.hover()
    inspectButton(page, button, output, "hover", (55, 50, 42))
    page.mouse.down()
    inspectButton(page, button, output, "pressed", (55, 50, 42))
    page.mouse.up()
    button.evaluate("element => element.disabled = true")
    inspectButton(page, button, output, "disabled", (21, 19, 16))
    button.evaluate("element => element.disabled = false")
    page.get_by_role("button", name="All builds", exact=True).click()
    page.mouse.move(1400, 20)


def expectedDivider(assets, width, isFooter):
    result = Image.new("RGBA", (width, 16))
    prefix = "footer-divider" if isFooter else "divider"
    fillHeight = 8 if isFooter else 12
    fillTop = 16 - fillHeight if isFooter else 0
    layers = [("fill", (width - 48, fillHeight), (24, fillTop)),
              ("left", (24, 16), (0, 0)), ("right", (24, 16), (width - 24, 0)),
              ("center", (64, fillHeight), ((width - 64) // 2, fillTop))]
    for part, size, position in layers:
        source = Image.open(assets / f"{prefix}-{part}.png").convert("RGBA")
        result.alpha_composite(source.resize(size, Image.Resampling.NEAREST), position)
    return result


def inspectDivider(page, assets, selector, isFooter):
    box = page.locator(selector).bounding_box()
    top = box["y"] if isFooter else box["y"] + box["height"] - 16
    width = round(box["width"])
    pixels = Image.open(BytesIO(page.screenshot(full_page=True))).convert("RGB")
    actual = pixels.crop((round(box["x"]), round(top), round(box["x"]) + width, round(top) + 16))
    expected = expectedDivider(assets, width, isFooter)
    sourcePixels, targetPixels = expected.convert("RGB").tobytes(), actual.tobytes()
    alpha = expected.getchannel("A").tobytes()
    mismatches = sum(1 for index, opacity in enumerate(alpha) if opacity == 255
                     and sourcePixels[index * 3:index * 3 + 3] != targetPixels[index * 3:index * 3 + 3])
    assert mismatches == 0, f"{selector}: {mismatches} original border pixels differ"


def inspectLayout(page, assets, output, label):
    page.evaluate("window.scrollTo({top:0,left:0,behavior:'instant'})")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Horizontal overflow"
    inspectDivider(page, assets, ".site-header", False)
    inspectDivider(page, assets, ".site-footer", True)
    page.screenshot(path=str(output / f"index-{label}.png"), full_page=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8788")
    parser.add_argument("--assets", type=Path, default=Path("runtime/gallery-assets"))
    parser.add_argument("--source-overrides", action="store_true", help="Preview local CSS/JS/assets against the real entry API before packaging")
    parser.add_argument("--output", type=Path, default=Path("runtime/gallery-minecraft-assets-review"))
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        if arguments.source_overrides:
            overrideSource(page, arguments.assets)
        response = page.goto(arguments.base_url, wait_until="networkidle")
        assert "font-src 'self'" in response.headers.get("content-security-policy", ""), "Font CSP must remain restricted to this origin"
        inspectFont(page)
        expect(page.locator(".build-card")).not_to_have_count(0)
        inspectButtonStates(page, arguments.output)
        inspectLayout(page, arguments.assets, arguments.output, "desktop")
        page.set_viewport_size({"width": 390, "height": 844})
        inspectLayout(page, arguments.assets, arguments.output, "mobile")
        page.locator(".build-card").first.click()
        page.wait_for_function("() => document.querySelector('.detail-image-frame img')?.naturalWidth > 0")
        page.screenshot(path=str(arguments.output / "entry-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1050})
        page.screenshot(path=str(arguments.output / "entry-desktop.png"), full_page=True)
        browser.close()
    print(f"Minecraft font, original button centers/states and exact divider pixels passed on actual entries. Screenshots: {arguments.output}")


if __name__ == "__main__":
    main()
