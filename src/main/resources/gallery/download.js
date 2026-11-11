(() => {
    "use strict";
    let loading = false;
    document.querySelectorAll("[data-download]").forEach((opener) => {
        opener.setAttribute("aria-haspopup", "dialog");
        opener.addEventListener("click", async (event) => {
            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            if (loading || document.querySelector("dialog[open]")) return;
            loading = true;
            try {
                const response = await fetch("/download/", { credentials: "omit" });
                const page = new DOMParser().parseFromString(await response.text(), "text/html");
                const card = page.querySelector(".download-card");
                if (!card) throw new Error("Download form unavailable");
                const dialog = document.createElement("dialog");
                dialog.className = "download-dialog";
                dialog.setAttribute("aria-labelledby", "download-title");
                dialog.setAttribute("aria-describedby", "download-message");
                const close = document.createElement("button");
                close.className = "welcome-close";
                close.type = "button";
                close.setAttribute("aria-label", "Close download");
                close.textContent = "×";
                close.addEventListener("click", () => dialog.close());
                card.prepend(close);
                dialog.append(card);
                document.body.append(dialog);
                dialog.addEventListener("close", () => {
                    dialog.remove();
                    document.documentElement.classList.remove("download-open");
                    opener.focus({ preventScroll: true });
                });
                dialog.addEventListener("click", (click) => {
                    if (click.target !== dialog) return;
                    const box = dialog.getBoundingClientRect();
                    if (click.clientX < box.left || click.clientX > box.right || click.clientY < box.top || click.clientY > box.bottom) dialog.close();
                });
                const form = dialog.querySelector("form");
                const input = form.querySelector("input");
                const button = form.querySelector("button");
                const message = dialog.querySelector("#download-message");
                let busy = false;
                form.addEventListener("submit", async (submit) => {
                    submit.preventDefault();
                    if (busy) return;
                    busy = true;
                    button.disabled = true;
                    input.setAttribute("aria-invalid", "false");
                    message.textContent = "Preparing your download…";
                    try {
                        const result = await fetch(form.action, {
                            method: "POST",
                            credentials: "omit",
                            body: new URLSearchParams({ password: input.value }),
                        });
                        input.value = "";
                        if (!result.ok || !result.headers.get("Content-Type")?.startsWith("application/zip")) {
                            const error = new DOMParser().parseFromString(await result.text(), "text/html");
                            message.textContent = error.querySelector("#download-message")?.textContent || "The download could not start. Please try again.";
                            if (result.status === 403) input.setAttribute("aria-invalid", "true");
                            input.focus();
                            return;
                        }
                        const url = URL.createObjectURL(await result.blob());
                        const link = document.createElement("a");
                        link.href = url;
                        link.download = "Hill-175-Campus-Java.zip";
                        document.body.append(link);
                        link.click();
                        link.remove();
                        setTimeout(() => URL.revokeObjectURL(url), 60000);
                        message.textContent = "Your download has started.";
                    } catch {
                        input.value = "";
                        message.textContent = "The download could not start. Please try again.";
                    } finally {
                        busy = false;
                        button.disabled = false;
                    }
                });
                dialog.showModal();
                document.documentElement.classList.add("download-open");
                if (!input.disabled) input.focus();
                else close.focus();
            } catch {
                window.location.assign(opener.href);
            } finally {
                loading = false;
            }
        });
    });
})();
