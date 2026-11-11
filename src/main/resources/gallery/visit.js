// BlueMap 5.23 exposes its tile managers on window.bluemap.mapViewer.
// Only meshes present in the server's rendered inventory are required.
export function mapReadiness(inventory, manager, visible = null) {
    if (manager.unloaded || manager.viewDistanceX <= 0 || manager.viewDistanceZ <= 0) {
        return { total: 0, loaded: 0, failed: 0 };
    }
    const required = (visible || inventory.tiles).filter(([x, z]) =>
        Math.abs(x - manager.centerTile.x) <= manager.viewDistanceX
        && Math.abs(z - manager.centerTile.y) <= manager.viewDistanceZ);
    const loaded = new Set();
    const failed = new Set();
    for (const tile of manager.tiles.values()) {
        const key = `${tile.x},${tile.z}`;
        if (tile.model && !tile.loading && !tile.unloaded) loaded.add(key);
        else if (!tile.loading && tile.unloaded) failed.add(key);
    }
    return {
        total: required.length,
        loaded: required.filter(([x, z]) => loaded.has(`${x},${z}`)).length,
        failed: required.filter(([x, z]) => failed.has(`${x},${z}`)).length,
    };
}

export function visibleMapTiles(inventory, manager, camera, Three, margin = 1) {
    if (manager.unloaded || manager.viewDistanceX <= 0 || manager.viewDistanceZ <= 0) return [];
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    const projection = new Three.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    const frustum = new Three.Frustum().setFromProjectionMatrix(projection);
    const box = new Three.Box3();
    return inventory.tiles.filter(([x, z, bounds]) => {
        if (Math.abs(x - manager.centerTile.x) > manager.viewDistanceX
            || Math.abs(z - manager.centerTile.y) > manager.viewDistanceZ) return false;
        if (!bounds) return true;
        box.min.set(...bounds.slice(0, 3));
        box.max.set(...bounds.slice(3));
        box.expandByScalar(margin);
        return frustum.intersectsBox(box);
    });
}

export function prioritizeVisibleTiles(inventory, viewer, Three) {
    const manager = viewer.map.hiresTileManager;
    const original = manager.loadNextTile;
    let queue = [], cursor = 0;
    const plan = { required: [] };
    // BlueMap otherwise requests the whole surrounding square, even behind the camera.
    manager.loadNextTile = () => {
        if (manager.unloaded || manager.currentlyLoading >= 8) return false;
        while (cursor < queue.length) {
            const [x, z] = queue[cursor++];
            if (manager.tryLoadTile(x, z)) return true;
        }
        return false;
    };
    plan.refresh = () => {
        plan.required = visibleMapTiles(inventory, manager, viewer.camera, Three);
        const nearby = visibleMapTiles(inventory, manager, viewer.camera, Three, 33);
        const visible = new Set(plan.required.map(([x, z]) => `${x},${z}`));
        const distance = ([x, z]) => (x - manager.centerTile.x) ** 2 + (z - manager.centerTile.y) ** 2;
        queue = [...plan.required].sort((a, b) => distance(a) - distance(b));
        queue.push(...nearby.filter(([x, z]) => !visible.has(`${x},${z}`))
            .sort((a, b) => distance(a) - distance(b)));
        cursor = 0;
        if (manager.currentlyLoading < 8) manager.loadCloseTiles();
    };
    plan.dispose = () => { manager.loadNextTile = original; };
    return plan;
}

async function openCampus() {
    const frame = document.querySelector(".map-frame iframe");
    const main = document.querySelector(".map-frame");
    const cover = document.querySelector("#map-loading");
    const title = document.querySelector("#map-loading-title");
    const status = document.querySelector("#map-loading-status");
    const progress = document.querySelector("#map-loading-progress");
    const retry = document.querySelector("#map-retry");
    retry.addEventListener("click", () => window.location.reload());
    let poll;
    let app;
    let viewPlan;
    let phase = "loading";
    let deadline;
    const fail = (message) => {
        if (phase === "failed" || phase === "ready") return;
        phase = "failed";
        clearInterval(poll);
        clearTimeout(deadline);
        title.textContent = "The tour could not open.";
        status.textContent = message;
        progress.hidden = true;
        retry.hidden = false;
        main.setAttribute("aria-busy", "false");
    };
    deadline = setTimeout(() => fail("Loading is taking longer than expected. Please try again."), 180000);
    try {
        const [campus, inventory] = await Promise.all(["/campus.json", "/map/ready.json"].map(async (url) => {
            const response = await fetch(url, { cache: "no-cache", signal: AbortSignal.timeout(20000) });
            if (!response.ok) throw new Error("Map preparation unavailable.");
            return response.json();
        }));
        if (!campus.mapReady || !Array.isArray(inventory.tiles) || !inventory.tiles.length
            || !Number.isFinite(inventory.detailDistance) || !Array.isArray(inventory.center)) {
            throw new Error("Map preparation unavailable.");
        }

        const check = async () => {
            if (phase !== "loading") return;
            try {
                const nextApp = frame.contentWindow?.bluemap;
                const viewer = nextApp?.mapViewer;
                const map = viewer?.map;
                if (frame.contentDocument?.querySelector("#bm-app-err") || viewer?.data.mapState === "errored") {
                    fail("The 3D view could not load. Please try again with WebGL enabled.");
                    return;
                }
                if (!map?.isLoaded || viewer.data.mapState !== "loaded"
                    || map.data.id !== inventory.map || !map.hiresTileManager) return;
                // Map materials become ready before BlueMap has applied the opening camera.
                const controls = viewer.controlsManager;
                if (controls.distance >= 1000
                    || Math.abs(controls.position.x - inventory.center[0]) > 1
                    || Math.abs(controls.position.z - inventory.center[1]) > 1) return;
                if (app !== nextApp) {
                    app = nextApp;
                    const openingDistance = controls.distance;
                    let expanded = false;
                    app.events.addEventListener("bluemapCameraMoved", () => {
                        if (expanded || controls.distance <= openingDistance * 1.5) return;
                        expanded = true;
                        viewer.loadMapArea(controls.position.x, controls.position.z,
                            Math.max(viewer.data.loadedHiresViewDistance, inventory.detailDistance * 2),
                            viewer.data.loadedLowresViewDistance);
                        viewPlan?.refresh();
                    });
                    const Three = frame.contentWindow.BlueMap?.Three;
                    if (Three && inventory.tiles.every(tile => Array.isArray(tile[2]))) {
                        viewPlan = prioritizeVisibleTiles(inventory, viewer, Three);
                        let scheduled = false;
                        const refresh = () => {
                            if (scheduled) return;
                            scheduled = true;
                            requestAnimationFrame(() => {
                                scheduled = false;
                                viewPlan.refresh();
                            });
                        };
                        app.events.addEventListener("bluemapCameraMoved", refresh);
                        frame.contentWindow.addEventListener("resize", refresh);
                    }
                    // Hide the coarse heightmap in close views. It turns buildings into cliffs.
                    // Preserve the overview when the visitor zooms out or selects flat view.
                    const updateOverview = () => {
                        const show = viewer.controlsManager.distance >= 1000
                            || app.appState.controls.state === "flat";
                        for (const layer of viewer.map?.lowresTileManager || []) layer.scene.visible = show;
                    };
                    app.events.addEventListener("bluemapRenderFrame", updateOverview);
                    updateOverview();
                    viewer.loadMapArea(...inventory.center, inventory.detailDistance, viewer.data.loadedLowresViewDistance);
                    viewPlan?.refresh();
                    viewer.renderer.domElement.addEventListener("webglcontextlost", () => {
                        if (phase !== "ready") fail("The 3D view ran out of graphics resources. Please try again.");
                    });
                }
                const state = mapReadiness(inventory, map.hiresTileManager, viewPlan?.required);
                if (state.failed) {
                    fail("Some map details could not load. Please try again.");
                    return;
                }
                if (!state.total) return;
                const percent = Math.floor(state.loaded / state.total * 100);
                progress.value = percent;
                status.textContent = state.loaded === state.total ? "Finishing the view." : `Loading campus details. ${percent}%`;
                if (state.loaded !== state.total) return;
                phase = "drawing";
                // Compile the real scene and draw behind the cover before revealing it.
                if (viewer.renderer.compileAsync) {
                    await viewer.renderer.compileAsync(map.hiresTileManager.sceneParent, viewer.camera);
                }
                if (phase !== "drawing") return;
                viewer.render(0);
                await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                if (phase !== "drawing") return;
                const current = mapReadiness(inventory, map.hiresTileManager, viewPlan?.required);
                if (!current.total || current.loaded !== current.total) {
                    phase = "loading";
                    return;
                }
                phase = "ready";
                clearInterval(poll);
                clearTimeout(deadline);
                frame.classList.remove("map-pending");
                frame.removeAttribute("aria-hidden");
                frame.inert = false;
                cover.hidden = true;
                main.setAttribute("aria-busy", "false");
            } catch {
                fail("Some map details could not load. Please try again.");
            }
        };
        poll = setInterval(check, 200);
        check();
    } catch {
        fail("The campus tour is unavailable right now. Please try again shortly.");
    }
    window.addEventListener("pagehide", () => {
        clearInterval(poll);
        clearTimeout(deadline);
    }, { once: true });
}

if (typeof document !== "undefined") openCampus();
