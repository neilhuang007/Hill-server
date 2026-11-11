import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../src/main/resources/gallery/map-preload.js", import.meta.url), "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

test("idle preload stays small and visitor intent resumes without duplicate downloads", async () => {
    const callbacks = new Map();
    const paths = Array.from({ length: 6 }, (_, i) => `/map/tile-${i}.prbm.gz`);
    const fetched = [];
    const context = {
        navigator: {}, AbortController,
        document: { hidden: false, querySelector: () => ({ addEventListener: (name, action) => callbacks.set(name, action) }) },
        window: { addEventListener: (name, action) => callbacks.set(name, action), requestIdleCallback: action => action() },
        async fetch(path) {
            if (path.endsWith("preload.json")) return { ok: true, json: async () => ({ paths, sizes: paths.map(() => 3 * 1024 * 1024), bytes: 18 * 1024 * 1024 }) };
            fetched.push(path);
            return { ok: true, arrayBuffer: async () => new ArrayBuffer(0) };
        },
    };
    runInNewContext(source, context);
    callbacks.get("load")(); await flush();
    assert.equal(fetched.length, 2);
    callbacks.get("pointerenter")(); await flush();
    assert.deepEqual(fetched, paths);
    callbacks.get("focus")(); await flush();
    assert.equal(fetched.length, 6);
});

test("data saving disables optional preload", () => {
    let attached = false;
    runInNewContext(source, { navigator: { connection: { saveData: true } },
        document: { querySelector: () => ({ addEventListener() { attached = true; } }) } });
    assert.equal(attached, false);
});
