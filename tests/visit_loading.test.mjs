import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = (await readFile(new URL("../src/main/resources/gallery/visit.js", import.meta.url), "utf8"))
    .replace(/^export /gm, "");
const flush = () => new Promise(resolve => setImmediate(resolve));

async function setup({ networkFails = false } = {}) {
    const element = () => ({
        hidden: false, textContent: "", attributes: new Map(),
        setAttribute(key, value) { this.attributes.set(key, value); },
        removeAttribute(key) { this.attributes.delete(key); },
        addEventListener() {},
    });
    const elements = Object.fromEntries([
        ".map-frame iframe", ".map-frame", "#map-loading", "#map-loading-title",
        "#map-loading-status", "#map-loading-progress", "#map-retry",
    ].map(selector => [selector, element()]));
    const frame = elements[".map-frame iframe"];
    frame.inert = true;
    frame.classList = new Set(["map-pending"]);
    frame.classList.remove = frame.classList.delete.bind(frame.classList);
    frame.contentDocument = { querySelector: () => null };
    elements["#map-retry"].hidden = true;
    const manager = {
        centerTile: { x: 0, y: 0 }, viewDistanceX: 16, viewDistanceZ: 16,
        sceneParent: {}, tiles: new Map([
            ["0,0", { x: 0, z: 0, model: {}, loading: false, unloaded: false }],
            ["1,0", { x: 1, z: 0, model: null, loading: true, unloaded: false }],
            // Missing terrain outside the rendered inventory is normal.
            ["2,0", { x: 2, z: 0, model: null, loading: false, unloaded: true }],
        ]),
    };
    const draws = [];
    let finishCompile;
    const viewer = {
        map: { isLoaded: true, data: { id: "campus" }, hiresTileManager: manager,
            lowresTileManager: [{ scene: { visible: true } }] },
        data: { mapState: "loaded", loadedHiresViewDistance: 256, loadedLowresViewDistance: 2000 },
        controlsManager: { distance: 120, position: { x: 150, z: 30 } },
        loadMapArea(...area) { this.lastArea = area; }, camera: {},
        renderer: {
            domElement: element(),
            compileAsync() { draws.push("compile"); return new Promise(resolve => { finishCompile = resolve; }); },
        },
        render() { draws.push("draw"); },
    };
    const events = new Map();
    frame.contentWindow = { bluemap: { mapViewer: viewer, appState: { controls: { state: "perspective" } },
        events: { addEventListener(name, callback) { events.set(name, callback); } } } };
    let interval, deadline;
    const context = {
        document: { querySelector: selector => elements[selector] },
        window: { location: { reload() {} }, addEventListener() {} },
        AbortSignal: { timeout() {} },
        async fetch(url) {
            if (networkFails) throw new Error("Offline");
            return { ok: true, json: async () => url === "/campus.json" ? { mapReady: true }
                : { map: "campus", center: [150, 30], detailDistance: 256, tiles: [[0, 0], [1, 0], [100, 100]] } };
        },
        setTimeout(callback) { deadline = callback; return 1; }, clearTimeout() {},
        setInterval(callback) { interval = callback; return 2; }, clearInterval() {},
        requestAnimationFrame(callback) { draws.push("frame"); queueMicrotask(callback); },
    };
    runInNewContext(source, context);
    await flush();
    return { elements, frame, manager, viewer, draws, events,
        check: () => interval(), timeout: () => deadline(), finishCompile: () => finishCompile() };
}

test("the opening view stays covered until all required meshes are drawn", async () => {
    const app = await setup();
    assert.equal(app.elements["#map-loading-progress"].value, 50);
    assert.equal(app.frame.inert, true);
    assert.equal(app.viewer.map.lowresTileManager[0].scene.visible, false);
    Object.assign(app.manager.tiles.get("1,0"), { model: {}, loading: false });
    const reveal = app.check();
    assert.deepEqual(app.draws, ["compile"]);
    assert.equal(app.elements["#map-loading"].hidden, false);
    app.finishCompile();
    await reveal;
    assert.deepEqual(app.draws, ["compile", "draw", "frame", "frame"]);
    assert.equal(app.elements["#map-loading"].hidden, true);
    assert.equal(app.frame.classList.has("map-pending"), false);
    assert.equal(app.frame.inert, false);
    assert.equal(app.viewer.lastArea[2], 256);
    app.viewer.controlsManager.distance = 200;
    app.events.get("bluemapCameraMoved")();
    assert.equal(app.viewer.lastArea[2], 512);
    app.viewer.controlsManager.distance = 1500;
    app.events.get("bluemapRenderFrame")();
    assert.equal(app.viewer.map.lowresTileManager[0].scene.visible, true);
});

test("a failed required tile offers retry without revealing the partial map", async () => {
    const app = await setup();
    Object.assign(app.manager.tiles.get("1,0"), { loading: false, unloaded: true });
    await app.check();
    assert.equal(app.elements["#map-retry"].hidden, false);
    assert.equal(app.elements["#map-loading"].hidden, false);
    assert.equal(app.frame.inert, true);
    assert.deepEqual(app.draws, []);
});

test("a timeout during shader preparation cannot reveal the map afterwards", async () => {
    const app = await setup();
    Object.assign(app.manager.tiles.get("1,0"), { model: {}, loading: false });
    const reveal = app.check();
    app.timeout();
    app.finishCompile();
    await reveal;
    assert.equal(app.elements["#map-loading"].hidden, false);
    assert.equal(app.elements["#map-retry"].hidden, false);
    assert.equal(app.frame.inert, true);
});

test("missing preparation data keeps a recoverable cover", async () => {
    const app = await setup({ networkFails: true });
    assert.equal(app.elements["#map-retry"].hidden, false);
    assert.equal(app.frame.classList.has("map-pending"), true);
    assert.equal(app.elements["#map-loading"].hidden, false);
});

test("visible tiles lead the queue and turning the camera requests new areas", () => {
    const helpers = {};
    runInNewContext(source, helpers);
    const point = () => ({ set(x, y, z) { Object.assign(this, { x, y, z }); } });
    const Three = {
        Matrix4: class { multiplyMatrices(projection) { this.range = projection.range; return this; } },
        Frustum: class {
            setFromProjectionMatrix(matrix) { this.range = matrix.range; return this; }
            intersectsBox(box) { return box.max.x >= this.range[0] && box.min.x <= this.range[1]; }
        },
        Box3: class {
            min = point(); max = point();
            expandByScalar(margin) { this.min.x -= margin; this.max.x += margin; }
        },
    };
    const camera = { projectionMatrix: { range: [-5, 5] }, matrixWorldInverse: {},
        updateProjectionMatrix() {}, updateMatrixWorld() {} };
    const requested = [], alreadyRequested = new Set();
    const manager = { centerTile: { x: 0, y: 0 }, viewDistanceX: 200, viewDistanceZ: 200,
        unloaded: false, currentlyLoading: 0, tiles: new Map(), loadNextTile() {},
        tryLoadTile(x, z) {
            if (alreadyRequested.has(`${x},${z}`)) return false;
            requested.push([x, z]); alreadyRequested.add(`${x},${z}`); return true;
        },
        loadCloseTiles() { while (this.loadNextTile()) {} },
    };
    const original = manager.loadNextTile;
    const inventory = { tiles: [
        [100, 0, [100, 0, 0, 101, 1, 1]],
        [10, 0, [10, 0, 0, 11, 1, 1]],
        [0, 0, [0, 0, 0, 1, 1, 1]],
    ] };
    const plan = helpers.prioritizeVisibleTiles(inventory, { camera, map: { hiresTileManager: manager } }, Three);
    plan.refresh();
    assert.equal(plan.required.length, 1);
    assert.deepEqual(requested, [[0, 0], [10, 0]]);
    manager.tiles.set("0,0", { x: 0, z: 0, model: {}, loading: false, unloaded: false });
    manager.tiles.set("100,0", { x: 100, z: 0, model: null, loading: false, unloaded: true });
    const ready = helpers.mapReadiness(inventory, manager, plan.required);
    assert.equal(ready.loaded, ready.total);
    assert.equal(ready.failed, 0);
    camera.projectionMatrix.range = [95, 105];
    plan.refresh();
    assert.deepEqual(requested.at(-1), [100, 0]);
    manager.currentlyLoading = 8;
    assert.equal(manager.loadNextTile(), false);
    plan.dispose();
    assert.equal(manager.loadNextTile, original);
});
