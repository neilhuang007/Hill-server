(() => {
    "use strict";
    const serverDialog = document.querySelector("#server-dialog");
    const serverOpener = document.querySelector("[data-open-server]");
    if (serverDialog && serverOpener) {
        const feedback = serverDialog.querySelector("#server-copy-status");
        serverOpener.addEventListener("click", () => {
            feedback.textContent = "";
            serverDialog.showModal();
            document.documentElement.classList.add("download-open");
        });
        serverDialog.querySelector("[data-close-server]").addEventListener("click", () => serverDialog.close());
        serverDialog.addEventListener("close", () => {
            document.documentElement.classList.remove("download-open");
            serverOpener.focus({ preventScroll: true });
        });
        serverDialog.addEventListener("click", (event) => {
            if (event.target !== serverDialog) return;
            const bounds = serverDialog.getBoundingClientRect();
            if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) serverDialog.close();
        });
        serverDialog.querySelectorAll("[data-copy-address]").forEach((button) => {
            const input = document.getElementById(button.dataset.copyAddress);
            input.addEventListener("click", () => input.select());
            button.addEventListener("click", async () => {
                try {
                    await navigator.clipboard.writeText(input.value);
                    feedback.textContent = `Copied ${input.value}`;
                } catch {
                    input.focus();
                    input.select();
                    feedback.textContent = "Select and copy the address.";
                }
            });
        });
    }
    const photo = document.querySelector("#campus-photo");
    const choices = [...document.querySelectorAll("[data-photo]")];
    const status = document.querySelector("#photo-status");
    if (!photo || !status) return;
    let selection = 0;

    choices.forEach((choice, index) => {
        choice.addEventListener("click", async (event) => {
            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            const request = ++selection;
            try {
                const next = new Image();
                next.src = choice.href;
                await next.decode();
                if (request !== selection) return;
                photo.src = next.src;
                photo.alt = choice.dataset.description;
                choices.forEach((item) => item.removeAttribute("aria-current"));
                choice.setAttribute("aria-current", "true");
                status.textContent = `Photo ${index + 1} of ${choices.length}: ${photo.alt}.`;
            } catch {
                if (request === selection) status.textContent = "That photo could not load. Please try again.";
            }
        });
        choice.addEventListener("keydown", (event) => {
            const next = event.key === "ArrowRight" ? (index + 1) % choices.length
                : event.key === "ArrowLeft" ? (index + choices.length - 1) % choices.length
                : event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1 : null;
            if (next === null) return;
            event.preventDefault();
            choices[next].focus();
            choices[next].click();
        });
    });
})();
