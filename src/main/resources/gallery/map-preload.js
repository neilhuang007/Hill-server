(() => {
    "use strict";
    const link = document.querySelector('a[href="/visit/"]');
    if (!link) return;
    const connection = navigator.connection;
    if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || "")) return;
    const controller = new AbortController();
    const idleBudget = 8 * 1024 * 1024;
    const intentBudget = 32 * 1024 * 1024;
    let budget = idleBudget;
    let running = false;
    let assets;
    let next = 0;
    let reserved = 0;
    const warm = async (intent = false) => {
        if (intent) budget = intentBudget;
        if (running || document.hidden || controller.signal.aborted) return;
        running = true;
        try {
            if (!assets) {
                const response = await fetch("/map/preload.json", { signal: controller.signal });
                if (!response.ok) return;
                const manifest = await response.json();
                if (!Array.isArray(manifest.paths) || !Array.isArray(manifest.sizes) || manifest.bytes > intentBudget) return;
                assets = manifest.paths.map((path, index) => ({ path, bytes: manifest.sizes[index] }))
                    .filter(({ path, bytes }) => typeof path === "string"
                        && /^\/map\/[A-Za-z0-9_./-]+$/.test(path) && !path.includes("..")
                        && !path.includes("/live/") && Number.isFinite(bytes) && bytes > 0).slice(0, 512);
            }
            const worker = async () => {
                while (next < assets.length && !controller.signal.aborted) {
                    if (reserved + assets[next].bytes > budget) return;
                    const { path, bytes } = assets[next++];
                    reserved += bytes;
                    try {
                        const asset = await fetch(path, {
                            cache: "force-cache", priority: "low", signal: controller.signal,
                        });
                        if (asset.ok) await asset.arrayBuffer();
                    } catch {
                        // Optional warming must never interrupt navigation.
                    }
                }
            };
            await Promise.all([worker(), worker(), worker()]);
        } catch {
            // The viewer can still request its prepared map normally.
        } finally {
            running = false;
        }
    };
    link.addEventListener("pointerenter", () => warm(true), { once: true });
    link.addEventListener("focus", () => warm(true), { once: true });
    window.addEventListener("load", () => {
        if ("requestIdleCallback" in window) window.requestIdleCallback(() => warm(), { timeout: 3000 });
        else setTimeout(() => warm(), 1500);
    }, { once: true });
    window.addEventListener("pagehide", () => controller.abort(), { once: true });
})();
