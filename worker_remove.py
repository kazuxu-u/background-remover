from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
os.environ["U2NET_HOME"] = str(APP_DIR / "models")
VENDOR_DIR = APP_DIR / "vendor"
CPU_VENDOR_DIR = APP_DIR / "vendor_cpu"
CPU_DEPS_DIR = Path(os.environ.get("REMBG_CPU_DEPS", r"C:\tmp\rembg_deps"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--provider", default="cpu")
    parser.add_argument("--model", default="isnet-general-use")
    parser.add_argument("--max-edge", type=int, default=1024)
    parser.add_argument("--high-quality", action="store_true")
    args = parser.parse_args()

    if args.provider.lower() in {"cpu", ""} and CPU_VENDOR_DIR.exists():
        sys.path.insert(0, str(CPU_VENDOR_DIR))
    elif args.provider.lower() in {"cpu", ""} and CPU_DEPS_DIR.exists():
        sys.path.insert(0, str(CPU_DEPS_DIR))
    elif VENDOR_DIR.exists():
        sys.path.insert(0, str(VENDOR_DIR))

    import onnxruntime as ort
    from PIL import Image
    from rembg import new_session, remove

    providers = []
    available = ort.get_available_providers()
    provider = args.provider.lower()
    if provider in {"directml", "dml", "gpu"} and "DmlExecutionProvider" in available:
        providers.append("DmlExecutionProvider")
    if provider in {"cuda", "gpu"} and "CUDAExecutionProvider" in available:
        providers.append("CUDAExecutionProvider")
    providers.append("CPUExecutionProvider")

    source = Image.open(args.input).convert("RGBA")
    scale = min(1.0, args.max_edge / max(source.width, source.height))
    if scale < 1.0:
        work_size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
        work = source.resize(work_size, Image.Resampling.LANCZOS)
    else:
        work = source

    session = new_session(args.model, providers=providers)
    result = remove(
        work,
        session=session,
        alpha_matting=args.high_quality,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        alpha_matting_erode_size=8,
        post_process_mask=True,
    )

    if result.size != source.size:
        alpha = result.getchannel("A").resize(source.size, Image.Resampling.LANCZOS)
        source.putalpha(alpha)
        result = source

    result.save(args.output)
    alpha = result.getchannel("A").getextrema()
    print(f"providers={providers}")
    print(f"size={result.width}x{result.height}")
    print(f"alpha={alpha[0]},{alpha[1]}")


if __name__ == "__main__":
    main()
