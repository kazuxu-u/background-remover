document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.querySelector("#fileInput");
    const dropZone = document.querySelector("#dropZone");
    const sourcePreview = document.querySelector("#sourcePreview");
    const resultPreview = document.querySelector("#resultPreview");
    const saveButton = document.querySelector("#saveButton");
    const saveNotice = document.querySelector("#saveNotice");
    const statusBox = document.querySelector("#status");
    const clearButton = document.querySelector("#clearButton");
    const toast = document.querySelector("#toast");
    const progressText = document.querySelector("#progressText");
    const erosionSlider = document.querySelector("#erosionSlider");
    const erosionValueDisplay = document.querySelector("#erosionValue");
    const regenerateButton = document.querySelector("#regenerateButton");

    let currentFile = null;
    let progressTimer = null;
    let latestFilename = null;
    let saveNoticeTimer = null;
    let toastTimer = null;

    function setStatus(message, isError = false) {
        if (!statusBox) return;
        statusBox.textContent = message;
        statusBox.classList.toggle("error", isError);
        console.log(`[Status] ${message}`);
    }

    // グローバルエラーハンドラー
    window.onerror = function(msg, url, line) {
        setStatus(`Error: ${msg} (Line: ${line})`, true);
        return false;
    };

    if (erosionSlider) {
        erosionSlider.addEventListener('input', () => {
            if (erosionValueDisplay) erosionValueDisplay.textContent = erosionSlider.value;
        });
    }

    function setProgress(value) {
        const percent = Math.max(0, Math.min(100, Math.round(value)));
        if (progressText) {
            progressText.hidden = false;
            progressText.textContent = `${percent}%`;
        }
    }

    function stopProgress() {
        if (progressTimer) {
            clearInterval(progressTimer);
            progressTimer = null;
        }
    }

    function startProcessingProgress(from = 15) {
        stopProgress();
        let current = Math.max(from, 15);
        setProgress(current);
        progressTimer = setInterval(() => {
            const remaining = 96 - current;
            const step = Math.max(0.2, remaining * 0.045);
            current = Math.min(96, current + step);
            setProgress(current);
        }, 700);
    }

    function clear() {
        stopProgress();
        if (saveNoticeTimer) clearTimeout(saveNoticeTimer);
        if (toastTimer) clearTimeout(toastTimer);
        if (toast) toast.hidden = true;
        fileInput.value = "";
        currentFile = null;
        if (regenerateButton) regenerateButton.disabled = true;
        sourcePreview.src = "";
        sourcePreview.style.display = "none";
        if(document.getElementById("dropZoneContent")) document.getElementById("dropZoneContent").style.display = "block";
        resultPreview.src = "";
        saveButton.hidden = true;
        saveNotice.hidden = true;
        latestFilename = null;
        if (progressText) progressText.hidden = true;
        setStatus("");
    }

    async function processFile(file) {
        if (!file) return;
        if (!file.type.startsWith("image/")) {
            setStatus("画像ファイルを選んでください。", true);
            return;
        }

        try {
            currentFile = file;
            if (regenerateButton) regenerateButton.disabled = false;

            sourcePreview.src = URL.createObjectURL(file);
            sourcePreview.style.display = "block";
            if(document.getElementById("dropZoneContent")) document.getElementById("dropZoneContent").style.display = "none";
            
            resultPreview.src = "";
            saveButton.hidden = true;
            saveNotice.hidden = true;
            latestFilename = null;
            setProgress(0);
            setStatus("背景を切り抜いています...");

            const erosion = erosionSlider ? erosionSlider.value : -3;
            const form = new FormData();
            form.append("highQuality", "true");
            form.append("erosion", erosion);
            form.append("image", file);

            const data = await new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.open("POST", "/api/remove");
                xhr.responseType = "json";

                xhr.upload.addEventListener("progress", (event) => {
                    if (event.lengthComputable) {
                        setProgress((event.loaded / event.total) * 12);
                    }
                });

                xhr.addEventListener("load", () => {
                    const payload = xhr.response || {};
                    if (xhr.status >= 200 && xhr.status < 300) resolve(payload);
                    else reject(new Error(payload.error || "処理に失敗しました。"));
                });

                xhr.addEventListener("error", () => reject(new Error("通信に失敗しました。")));
                xhr.timeout = 120000;
                xhr.send(form);
                startProcessingProgress(12);
            });

            stopProgress();
            if (progressText) progressText.hidden = true;
            resultPreview.src = `${data.url}?t=${Date.now()}`;
            latestFilename = data.filename;
            saveButton.hidden = false;
            setStatus(`完了: ${data.width}x${data.height}px`);
        } catch (error) {
            stopProgress();
            setStatus(error.message, true);
        }
    }

    // 事件监听
    if (dropZone && fileInput) {
        dropZone.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", () => {
            if (fileInput.files.length > 0) processFile(fileInput.files[0]);
        });

        for (const eventName of ["dragenter", "dragover"]) {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.add("dragging");
            });
        }
        for (const eventName of ["dragleave", "drop"]) {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.remove("dragging");
            });
        }
        dropZone.addEventListener("drop", (e) => {
            const [file] = e.dataTransfer.files;
            processFile(file);
        });
    }

    if (clearButton) clearButton.addEventListener("click", clear);
    if (saveButton) {
        saveButton.addEventListener("click", () => {
            if (!latestFilename) return;
            const link = document.createElement("a");
            link.href = resultPreview.src;
            link.download = latestFilename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            setStatus("ダウンロードを開始しました");
        });
    }
    if (regenerateButton) {
        regenerateButton.addEventListener("click", () => {
            if (currentFile) processFile(currentFile);
        });
    }
});
