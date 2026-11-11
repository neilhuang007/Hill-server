(() => {
    "use strict";

    // Change this version when the event instructions materially change.
    const seenKey = "hill175.welcome.v1";
    const openers = document.querySelectorAll("[data-open-event-guide]");
    let dialog;
    let loading;
    let returnFocus;

    function rememberVisit() {
        try {
            localStorage.setItem(seenKey, "seen");
        } catch {
            // The guide still works when browser storage is unavailable.
        }
    }

    async function loadGuide() {
        if (dialog) return dialog;
        if (!loading) {
            loading = fetch("/welcome.html", { credentials: "omit" })
                .then((response) => {
                    if (!response.ok)
                        throw new Error("Event guide unavailable");
                    return response.text();
                })
                .then((html) => {
                    const template = document.createElement("template");
                    template.innerHTML = html;
                    dialog = template.content.querySelector("dialog");
                    if (!dialog) throw new Error("Event guide unavailable");
                    document.body.append(dialog);
                    dialog.addEventListener("keydown", (event) => {
                        if (event.key !== "Tab") return;
                        const controls = [
                            ...dialog.querySelectorAll(
                                'a[href], button:not([disabled]), summary, [tabindex="0"]',
                            ),
                        ].filter((element) => element.getClientRects().length);
                        const first = controls[0];
                        const last = controls.at(-1);
                        if (
                            event.shiftKey &&
                            document.activeElement === first
                        ) {
                            event.preventDefault();
                            last.focus();
                        } else if (
                            !event.shiftKey &&
                            document.activeElement === last
                        ) {
                            event.preventDefault();
                            first.focus();
                        }
                    });
                    dialog
                        .querySelectorAll("[data-close-event-guide]")
                        .forEach((button) => {
                            button.addEventListener("click", () =>
                                dialog.close(),
                            );
                        });
                    dialog
                        .querySelector("[data-start-campus-tour]")
                        .addEventListener("click", (event) => {
                            if (location.pathname === "/visit/")
                                event.preventDefault();
                            rememberVisit();
                            dialog.close();
                        });
                    dialog.addEventListener("close", () => {
                        rememberVisit();
                        document.documentElement.classList.remove(
                            "welcome-open",
                        );
                        if (returnFocus?.isConnected)
                            returnFocus.focus({ preventScroll: true });
                    });
                    dialog.addEventListener("click", (event) => {
                        if (event.target !== dialog) return;
                        const bounds = dialog.getBoundingClientRect();
                        if (
                            event.clientX < bounds.left ||
                            event.clientX > bounds.right ||
                            event.clientY < bounds.top ||
                            event.clientY > bounds.bottom
                        )
                            dialog.close();
                    });
                    return dialog;
                })
                .catch((error) => {
                    loading = undefined;
                    throw error;
                });
        }
        return loading;
    }

    async function showGuide(opener) {
        try {
            const guide = await loadGuide();
            if (guide.open) return;
            returnFocus =
                opener || document.querySelector(".hero-actions a, .brand");
            guide.showModal();
            document.documentElement.classList.add("welcome-open");
            guide
                .querySelector("#welcome-title")
                .focus({ preventScroll: true });
            document.querySelector(".event-guide-status").textContent = "";
        } catch {
            // A missing guide must never prevent access to the campus or download.
            if (opener) {
                const status = document.querySelector(".event-guide-status");
                status.classList.remove("sr-only");
                status.textContent =
                    "The event guide could not load. Please try again.";
            }
        }
    }

    openers.forEach((opener) => {
        opener.hidden = false;
        opener.addEventListener("click", () => showGuide(opener));
    });

    let seen = false;
    try {
        seen = localStorage.getItem(seenKey) === "seen";
    } catch {
        // Private or restricted storage falls back to showing the welcome guide.
    }
    if (!seen) showGuide();
})();
