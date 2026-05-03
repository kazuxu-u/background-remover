from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from urllib import parse, request


class ComfyBridgeError(RuntimeError):
    pass


class ComfyBridge:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def remove_background(self, image_path: Path, output_prefix: str, high_quality: bool = False, erosion: int = -3) -> tuple[bytes, str]:
        comfy_name = self.upload_image(image_path)
        prompt = self.build_prompt(comfy_name, output_prefix, high_quality, erosion)
        prompt_id = self.queue_prompt(prompt)
        image_info = self.wait_for_image(prompt_id, "3")
        return self.download_image(image_info), image_info["filename"]

    def upload_image(self, image_path: Path) -> str:
        boundary = f"----CodexBoundary{uuid.uuid4().hex}"
        filename = image_path.name
        data = image_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8") + data + (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
            "true\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/upload/image",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload.get("name") or filename

    def build_prompt(self, image_name: str, output_prefix: str, high_quality: bool = False, erosion: int = -3) -> dict:
        if high_quality:
            # 高精度モード: 以前使用していたRMBG-2.0に戻す。
            # ComfyUIのノードが極端な値(-30等)でエラーになるのを防ぐため、ここは0固定。
            # 枠削りはserver.pyのPython（v1.3.2）側で強力に実行する。
            return {
                "1": {
                    "class_type": "LoadImage",
                    "inputs": {"image": image_name},
                },
                "2": {
                    "class_type": "RMBG",
                    "inputs": {
                        "image": ["1", 0],
                        "model": "RMBG-2.0",
                        "sensitivity": 1.0,
                        "process_res": 1024,
                        "mask_blur": 1,
                        "mask_offset": 0,
                        "invert_output": False,
                        "refine_foreground": True,
                        "background": "Alpha",
                        "background_color": "#00000000",
                    },
                },
                "3": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["2", 0],
                        "filename_prefix": output_prefix,
                    },
                },
            }
        else:
            # 通常モード: 速度優先のRMBG
            return {
                "1": {
                    "class_type": "LoadImage",
                    "inputs": {"image": image_name},
                },
                "2": {
                    "class_type": "RMBG",
                    "inputs": {
                        "image": ["1", 0],
                        "model": "RMBG-2.0",
                        "sensitivity": 1.0,
                        "process_res": 1024,
                        "mask_blur": 1,
                        "mask_offset": -1,
                        "invert_output": False,
                        "refine_foreground": True,
                        "background": "Alpha",
                        "background_color": "#00000000",
                    },
                },
                "3": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["2", 0],
                        "filename_prefix": output_prefix,
                    },
                },
            }

    def queue_prompt(self, prompt: dict) -> str:
        payload = json.dumps({"prompt": prompt, "client_id": str(uuid.uuid4())}).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/prompt",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        if "prompt_id" not in data:
            raise ComfyBridgeError(f"ComfyUI did not return prompt_id: {data}")
        return data["prompt_id"]

    def wait_for_image(self, prompt_id: str, output_node_id: str) -> dict:
        deadline = time.time() + self.timeout
        last_status = None
        while time.time() < deadline:
            with request.urlopen(f"{self.base_url}/history/{prompt_id}", timeout=30) as response:
                history = json.loads(response.read().decode("utf-8"))
            item = history.get(prompt_id)
            if item:
                status = item.get("status", {})
                last_status = status
                if status.get("completed") is False:
                    messages = status.get("messages") or []
                    raise ComfyBridgeError(f"ComfyUI failed: {messages}")
                outputs = item.get("outputs", {})
                images = outputs.get(output_node_id, {}).get("images", [])
                if images:
                    return images[0]
            time.sleep(1)
        raise ComfyBridgeError(f"ComfyUI timed out waiting for output. Last status: {last_status}")

    def download_image(self, image_info: dict) -> bytes:
        query = parse.urlencode(
            {
                "filename": image_info["filename"],
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            }
        )
        with request.urlopen(f"{self.base_url}/view?{query}", timeout=60) as response:
            return response.read()
