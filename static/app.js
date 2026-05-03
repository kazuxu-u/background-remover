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
const hqSwitch = document.querySelector("#HQ_SWITCH_UNIQUE_ID");
const erosionSlider = document.querySelector("#erosionSlider");
const erosionValueDisplay = document.querySelector("#erosionValue");
const regenerateButton = document.querySelector("#regenerateButton");

let currentFile = null;

if (hqSwitch) {
  hqSwitch.addEventListener('change', () => {
    // Debug toggle state removed
  });
}

if (erosionSlider) {
  erosionSlider.addEventListener('input', () => {
    erosionValueDisplay.textContent = erosionSlider.value;
  });
}

let progressTimer = null;
let latestFilename = null;
let saveNoticeTimer = null;
let toastTimer = null;
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

function setStatus(message, isError = false) {
  statusBox.textContent = message;
  statusBox.classList.toggle("error", isError);
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 5000);
}

function clear() {
  stopProgress();
  if (saveNoticeTimer) clearTimeout(saveNoticeTimer);
  if (toastTimer) clearTimeout(toastTimer);
  toast.hidden = true;
  fileInput.value = "";
  currentFile = null;
  if (regenerateButton) regenerateButton.disabled = true;
  sourcePreview.removeAttribute("src");
  sourcePreview.style.display = "none";
  if(document.getElementById("dropZoneContent")) document.getElementById("dropZoneContent").style.display = "block";
  resultPreview.removeAttribute("src");
  saveButton.hidden = true;
  saveButton.textContent = "保存";
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

  currentFile = file;
  if (regenerateButton) regenerateButton.disabled = false;

  sourcePreview.src = URL.createObjectURL(file);
  sourcePreview.style.display = "block";
  if(document.getElementById("dropZoneContent")) document.getElementById("dropZoneContent").style.display = "none";
  
  resultPreview.removeAttribute("src");
  saveButton.hidden = true;
  saveButton.textContent = "保存";
  saveNotice.hidden = true;
  latestFilename = null;
  setProgress(0);
  setStatus("背景を切り抜いています...");

  const isHighQuality = hqSwitch ? hqSwitch.checked : true;
  const erosion = erosionSlider ? erosionSlider.value : -3;
  // Debug request info removed
  
  const form = new FormData();
  form.append("highQuality", isHighQuality ? "true" : "false");
  form.append("erosion", erosion);
  form.append("image", file);

  try {
    const data = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/remove");
      xhr.responseType = "json";

      xhr.upload.addEventListener("progress", (event) => {
        if (!event.lengthComputable) {
          setProgress(8);
          return;
        }
        const uploadPercent = (event.loaded / event.total) * 12;
        setProgress(uploadPercent);
      });

      xhr.addEventListener("load", () => {
        const payload = xhr.response || {};
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload);
        } else {
          reject(new Error(payload.error || "処理に失敗しました。"));
        }
      });

      xhr.addEventListener("error", () => reject(new Error("通信に失敗しました。")));
      xhr.addEventListener("timeout", () => reject(new Error("処理がタイムアウトしました。")));
      xhr.timeout = 20 * 60 * 1000;
      xhr.send(form);
      startProcessingProgress(12);
    });
    stopProgress();
    if (progressText) progressText.hidden = true;
    // Debug result removed
    resultPreview.src = `${data.url}?t=${Date.now()}`;
    latestFilename = data.filename;
    saveButton.hidden = false;
    setStatus(`完了: ${data.width} x ${data.height}px / PNG透過`);
  } catch (error) {
    stopProgress();
    setStatus(error.message, true);
  }
}

async function saveCurrentImage() {
  if (!latestFilename) {
    setStatus("保存する画像がありません。", true);
    return;
  }
  
  try {
    const link = document.createElement("a");
    link.href = `/outputs/${latestFilename}`;
    link.download = latestFilename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    saveButton.textContent = "保存しました";
    saveNotice.textContent = "保存しました";
    saveNotice.hidden = false;
    setStatus(`ダウンロードを開始しました`);
    showToast("ダウンロードを開始しました");
    if (saveNoticeTimer) clearTimeout(saveNoticeTimer);
    saveNoticeTimer = setTimeout(() => {
      saveButton.textContent = "保存";
      saveNotice.hidden = true;
    }, 5000);
  } catch (error) {
    setStatus(error.message, true);
  }
}

fileInput.addEventListener("change", () => processFile(fileInput.files[0]));
clearButton.addEventListener("click", clear);
saveButton.addEventListener("click", saveCurrentImage);

if (regenerateButton) {
  regenerateButton.addEventListener("click", () => {
    if (currentFile) processFile(currentFile);
  });
}

for (const eventName of ["dragenter", "dragover"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
  });
}

dropZone.addEventListener("drop", (event) => {
  const [file] = event.dataTransfer.files;
  processFile(file);
});
