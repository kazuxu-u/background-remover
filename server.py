from __future__ import annotations

import cgi
import io
import json
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests
import threading
from pathlib import Path
from urllib import request
from urllib.parse import unquote
import timeit
import inspect


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR

STATIC_DIR = RESOURCE_DIR / "static"
OUTPUT_DIR = APP_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
SAVE_DIR = Path(os.environ.get("CUTOUT_SAVE_DIR", r"C:\Users\momop\OneDrive\画像\切り抜き"))

VENDOR_DIR = RESOURCE_DIR / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

EXTRA_DEPS = os.environ.get("REMBG_DEPS", r"C:\tmp\rembg_deps")
if EXTRA_DEPS and Path(EXTRA_DEPS).exists():
    sys.path.append(EXTRA_DEPS)

# Portable環境 (_internal) を検索パスに追加
INTERNAL_DIR = RESOURCE_DIR / "_internal"
if INTERNAL_DIR.exists():
    sys.path.insert(0, str(INTERNAL_DIR))

# requestsの自動インポート & フォールバックインストール
try:
    import requests
except ImportError:
    try:
        print("[*] requests not found. Attempting to install...", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "--target", str(INTERNAL_DIR) if INTERNAL_DIR.exists() else "."], timeout=60)
        import requests
    except Exception as e:
        print(f"[!] Failed to auto-install requests: {e}", flush=True)
        requests = None



class Handler(BaseHTTPRequestHandler):
    server_version = "BackgroundRemover/1.0"

    def log_message(self, fmt: str, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path == "/":
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if path.startswith("/static/"):
            target = STATIC_DIR / path.removeprefix("/static/")
            self.serve_static(target)
            return
        if path.startswith("/outputs/"):
            target = OUTPUT_DIR / path.removeprefix("/outputs/")
            self.serve_static(target)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        if self.path == "/api/save":
            self.handle_save()
            return

        if self.path != "/api/remove":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                },
            )
            field = form["image"] if "image" in form else None
            if field is None or not getattr(field, "file", None):
                self.write_json({"error": "画像ファイルを選択してください。"}, HTTPStatus.BAD_REQUEST)
                return

            image_bytes = field.file.read()
            if not image_bytes:
                self.write_json({"error": "画像ファイルが空です。"}, HTTPStatus.BAD_REQUEST)
                return

            high_quality_raw = form.getfirst("highQuality", "false")
            high_quality = high_quality_raw == "true"
            erosion = int(form.getfirst("erosion", "-3"))
            print(f"[*] Request received: high_quality={high_quality}, erosion={erosion}", flush=True)
            from PIL import Image

            source = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

            safe_stem = Path(getattr(field, "filename", "") or "image").stem[:40] or "image"
            filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}_{safe_stem}_transparent.png"
            out_path = OUTPUT_DIR / filename
            input_path = OUTPUT_DIR / f"{int(time.time())}_{uuid.uuid4().hex[:8]}_comfy_input.png"
            source.save(input_path)

            provider_name = "unknown"
            comfy_filename = None

            # Process locally via worker_remove.py
            # Render（メモリ512MB）対策：高精度でもbirefnetは重すぎるのでisnet-general-useにフォールバック
            is_render = os.environ.get("RENDER") == "true"
            selected_model = "isnet-general-use"
            if high_quality and not is_render:
                selected_model = "birefnet-general"
            elif not high_quality:
                selected_model = "u2netp"

            worker_script = RESOURCE_DIR / "worker_remove.py"
            cmd = [
                sys.executable,
                str(worker_script),
                "--input", str(input_path),
                "--output", str(out_path),
                "--provider", os.environ.get("REMBG_PROVIDER", "cpu"),
                "--model", selected_model,
                "--max-edge", os.environ.get("REMBG_MAX_EDGE", "1024"),
            ]
            if high_quality:
                cmd.append("--high-quality")

            print(f"Running local worker: {' '.join(cmd)}")
            result_proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result_proc.returncode != 0:
                raise RuntimeError(f"Local processing failed: {result_proc.stderr}")
            provider_name = f"local-rembg ({os.environ.get('REMBG_MODEL', 'isnet-general-use')})"

            result = Image.open(out_path).convert("RGBA")
            
            # --- Local Mask Refinement (Erosion/Dilation) ---

            if erosion != 0:
                print(f"[*] Applying local refinement: erosion={erosion}", flush=True)
                from PIL import ImageFilter
                alpha = result.getchannel('A')
                
                # Erosion (shrink) - using a slightly more aggressive filter if needed
                if erosion < 0:
                    for _ in range(abs(erosion)):
                        alpha = alpha.filter(ImageFilter.MinFilter(3))
                # Dilation (expand)
                else:
                    for _ in range(erosion):
                        alpha = alpha.filter(ImageFilter.MaxFilter(3))
                
                # Soften the edges (Feathering) - Proportional to erosion for smoother results
                blur_radius = max(0.5, min(2.0, abs(erosion) / 10.0))
                alpha = alpha.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                
                result.putalpha(alpha)
                result.save(out_path, "PNG")
                print(f"[*] Saved refined image to {out_path}", flush=True)
            # ------------------------------------------------

            # アップロードされた元画像も残すように変更（削除処理を削除）

            alpha_extrema = result.getchannel("A").getextrema()
            
            cleanup_old_files()
            # Discordへ送信
            send_to_discord_async(input_path, out_path)
            self.write_json(
                {
                    "url": f"/outputs/{filename}",
                    "filename": filename,
                    "width": result.width,
                    "height": result.height,
                    "alpha": alpha_extrema,
                    "provider": provider_name,
                    "comfyFilename": comfy_filename,
                    "erosion_applied": erosion
                }
            )
        except subprocess.TimeoutExpired:
            self.write_json(
                {
                    "error": "処理が45秒でタイムアウトしました。高精度やGPUをオフにして、もう一度試してください。"
                },
                HTTPStatus.REQUEST_TIMEOUT,
            )
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_save(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            filename = Path(str(payload.get("filename", ""))).name
            if not filename:
                self.write_json({"error": "保存するファイルがありません。"}, HTTPStatus.BAD_REQUEST)
                return

            source = (OUTPUT_DIR / filename).resolve()
            if not str(source).startswith(str(OUTPUT_DIR.resolve())) or not source.exists():
                self.write_json({"error": "保存対象のPNGが見つかりません。"}, HTTPStatus.NOT_FOUND)
                return

            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            destination = SAVE_DIR / filename
            if destination.exists():
                stem = destination.stem
                suffix = destination.suffix
                index = 2
                while destination.exists():
                    destination = SAVE_DIR / f"{stem}-{index}{suffix}"
                    index += 1

            destination.write_bytes(source.read_bytes())
            self.write_json(
                {
                    "message": "保存しました",
                    "path": str(destination),
                    "filename": destination.name,
                }
            )
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, target: Path):
        try:
            resolved = target.resolve()
            allowed_roots = (STATIC_DIR.resolve(), OUTPUT_DIR.resolve())
            if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            content_types = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }
            self.serve_file(resolved, content_types.get(resolved.suffix.lower(), "application/octet-stream"))
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def serve_file(self, path: Path, content_type: str):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

# Discord Webhook設定
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1500426166715285674/4uWSNONpWQVo7DUYGO_N_ehlq-gVPEOBUj9J3efNCI5U1154DFX2vW8fYOpSsEk5ATLj"

def send_to_discord_async(input_path, output_path, message="背景透過が完了しました！"):
    if not requests or not DISCORD_WEBHOOK_URL:
        return
    
    def _send():
        try:
            print(f"[*] Sending to Discord: {input_path.name if hasattr(input_path, 'name') else 'Test'}", flush=True)
            files = {}
            if input_path and Path(input_path).exists():
                files["original"] = (Path(input_path).name, open(input_path, "rb"), "image/png")
            if output_path and Path(output_path).exists():
                files["transparent"] = (Path(output_path).name, open(output_path, "rb"), "image/png")
            
            payload = {
                "content": f"✨ **{message}**" + (f"\n📄 ファイル名: `{Path(input_path).name}`" if input_path else "")
            }
            res = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files if files else None, timeout=30)
            print(f"[*] Discord Response: {res.status_code}", flush=True)
            
            # Close files
            for f_info in files.values():
                f_info[1].close()
        except Exception as e:
            print(f"Discord upload error: {e}", flush=True)

    # 処理を止めないようにバックグラウンドで送信
    threading.Thread(target=_send, daemon=True).start()

def cleanup_old_files():
    try:
        files = [f for f in OUTPUT_DIR.iterdir() if f.is_file()]
        if len(files) > 100:
            files.sort(key=lambda x: x.stat().st_mtime)
            for f in files[:-100]:
                try:
                    f.unlink()
                except OSError:
                    pass
    except Exception as e:
        print(f"Cleanup error: {e}", flush=True)


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print("Background Remover App: http://127.0.0.1:8787/", flush=True)
    print(f"Outputs: {OUTPUT_DIR}")
    print("Model processing runs in a timeout-safe worker process.")
    
    # 起動テスト送信
    send_to_discord_async(None, None, message="背景透過アプリ（v2.0）が起動しました！🚀")

    if os.environ.get("DISABLE_OPEN_BROWSER", "").lower() not in {"1", "true", "yes"}:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1].endswith("worker_remove.py"):
        script_path = sys.argv[1]
        sys.argv = [script_path] + sys.argv[2:]
        with open(script_path, "r", encoding="utf-8") as f:
            code = f.read()
        exec(compile(code, script_path, 'exec'), {"__name__": "__main__", "__file__": script_path})
        sys.exit(0)
    main()
