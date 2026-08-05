#!/usr/bin/env python3
"""OpenAI-compatible local server for Qwen2.5-VL-7B-Instruct-AWQ.

Prefers vLLM when CUDA is available. Falls back to transformers+CPU with a
visual-weight repair for AWQ checkpoints that keep the vision tower in FP/BF16.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import time
import uuid
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from safetensors.torch import load_file


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model",
        default=str(root / "lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ"),
    )
    p.add_argument("--served-model-name", default="Qwen2.5-VL-7B-Instruct-AWQ")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--max-model-len", type=int, default=4096)
    p.add_argument("--api-key", default="dummy-local-key")
    return p.parse_args()


def load_visual_float_weights(model_dir: Path) -> dict[str, torch.Tensor]:
    state: dict[str, torch.Tensor] = {}
    for f in sorted(model_dir.glob("model-*.safetensors")):
        for key, value in load_file(str(f)).items():
            if "visual" not in key:
                continue
            if any(tok in key for tok in ("qweight", "qzeros", "scales")):
                continue
            if key.endswith(".weight") or key.endswith(".bias"):
                state[key] = value
    return state


def repair_visual_awq_modules(model: Any, model_dir: Path) -> int:
    """Replace broken visual AwqLinear modules with nn.Linear + checkpoint weights."""
    state = load_visual_float_weights(model_dir)
    awq_mods = []
    for name, module in model.model.visual.named_modules():
        cls = module.__class__.__name__
        if "Awq" in cls or "AWQ" in cls or hasattr(module, "qweight"):
            awq_mods.append((name, module))

    replaced = 0
    for name, module in awq_mods:
        parts = name.split(".")
        parent = model.model.visual
        for part in parts[:-1]:
            parent = getattr(parent, part)
        child = parts[-1]
        in_f = getattr(module, "in_features", None) or getattr(module, "infeatures", None)
        out_f = getattr(module, "out_features", None) or getattr(
            module, "outfeatures", None
        )
        has_bias = getattr(module, "bias", None) is not None
        # nn.Linear defaults to float32; activations are bf16 → dtype mismatch.
        lin = nn.Linear(in_f, out_f, bias=has_bias).to(dtype=torch.bfloat16)
        for key in (
            f"visual.{name}.weight",
            f"model.visual.{name}.weight",
            f"{name}.weight",
        ):
            if key in state:
                lin.weight.data.copy_(state[key].to(torch.bfloat16))
                bias_key = key.replace(".weight", ".bias")
                if has_bias and bias_key in state:
                    lin.bias.data.copy_(state[bias_key].to(torch.bfloat16))
                break
        else:
            continue
        setattr(parent, child, lin)
        replaced += 1
    # Ensure the whole vision tower stays on one dtype after replacements.
    model.model.visual.to(dtype=torch.bfloat16)
    return replaced


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    max_tokens: int = 512
    temperature: float = 0.2
    top_p: float = 0.8
    stream: bool = False


def content_to_qwen_parts(content: Any) -> list[dict[str, Any]]:
    if content is None:
        return [{"type": "text", "text": ""}]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    parts: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            parts.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            parts.append({"type": "text", "text": item.get("text", "")})
        elif item.get("type") == "image_url":
            url = item.get("image_url", {})
            if isinstance(url, dict):
                url = url.get("url", "")
            parts.append({"type": "image", "image": url})
    return parts or [{"type": "text", "text": ""}]


def decode_image_ref(ref: str, max_side: int = 512):
    from PIL import Image

    if ref.startswith("data:"):
        _, b64 = ref.split(",", 1)
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    else:
        if ref.startswith("file://"):
            ref = ref[7:]
        img = Image.open(ref).convert("RGB")
    # Shrink large photos so CPU vision forward stays tractable.
    w, h = img.size
    scale = min(1.0, float(max_side) / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BICUBIC)
    return img


def build_app(args: argparse.Namespace) -> FastAPI:
    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

    model_dir = Path(args.model).resolve()
    if not model_dir.exists():
        raise FileNotFoundError(model_dir)

    print(f"[local-openai] Loading model from {model_dir} on CPU ...", flush=True)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        str(model_dir),
        torch_dtype=torch.bfloat16,
        device_map="cpu",
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )
    replaced = repair_visual_awq_modules(model, model_dir)
    print(f"[local-openai] Repaired visual modules: {replaced}", flush=True)
    processor = AutoProcessor.from_pretrained(str(model_dir), trust_remote_code=True)
    model.eval()

    app = FastAPI(title="Local OpenAI-compatible Qwen2.5-VL server")
    served = args.served_model_name

    def check_auth(authorization: str | None) -> None:
        if not args.api_key:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")
        token = authorization.split(" ", 1)[1].strip()
        if token != args.api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")

    @app.get("/health")
    def health():
        return {"status": "ok", "model": served, "backend": "transformers-cpu"}

    @app.get("/v1/models")
    def list_models(authorization: str | None = Header(default=None)):
        check_auth(authorization)
        return {
            "object": "list",
            "data": [
                {
                    "id": served,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    def chat_completions(
        req: ChatCompletionRequest,
        authorization: str | None = Header(default=None),
    ):
        check_auth(authorization)
        if req.stream:
            raise HTTPException(status_code=400, detail="stream=false only")

        qwen_messages = []
        images = []
        for msg in req.messages:
            parts = content_to_qwen_parts(msg.content)
            normalized = []
            for part in parts:
                if part.get("type") == "image":
                    img = decode_image_ref(part["image"])
                    images.append(img)
                    normalized.append({"type": "image", "image": img})
                else:
                    normalized.append(part)
            qwen_messages.append({"role": msg.role, "content": normalized})

        text = processor.apply_chat_template(
            qwen_messages, tokenize=False, add_generation_prompt=True
        )
        inputs = processor(
            text=[text],
            images=images or None,
            return_tensors="pt",
            padding=True,
        )
        # Keep activations on the same dtype/device as the loaded model.
        param = next(model.parameters())
        inputs = {
            k: (
                v.to(device=param.device, dtype=param.dtype)
                if torch.is_floating_point(v)
                else v.to(device=param.device)
            )
            for k, v in inputs.items()
        }
        # Cap generation on CPU; callers often request 2000 tokens.
        cpu_cap = 512 if not torch.cuda.is_available() else args.max_model_len
        max_new = max(1, min(req.max_tokens, args.max_model_len, cpu_cap))
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=max_new,
                do_sample=req.temperature > 0,
                temperature=max(req.temperature, 1e-5),
                top_p=req.top_p,
            )
        prompt_len = inputs["input_ids"].shape[-1]
        gen_ids = output_ids[0, prompt_len:]
        content = processor.decode(gen_ids, skip_special_tokens=True).strip()

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model or served,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": int(prompt_len),
                "completion_tokens": int(gen_ids.numel()),
                "total_tokens": int(prompt_len + gen_ids.numel()),
            },
        }

    return app


def maybe_exec_vllm(args: argparse.Namespace) -> None:
    if not torch.cuda.is_available():
        return
    # Delegate to vLLM OpenAI server when a GPU is present.
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        args.model,
        "--served-model-name",
        args.served_model_name,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--quantization",
        "awq",
        "--dtype",
        "float16",
        "--max-model-len",
        str(args.max_model_len),
        "--trust-remote-code",
        "--api-key",
        args.api_key,
        "--gpu-memory-utilization",
        os.environ.get("GPU_MEM_UTIL", "0.85"),
    ]
    print("[local-openai] CUDA detected; starting vLLM:", " ".join(cmd), flush=True)
    os.execvp(cmd[0], cmd)


def main() -> None:
    args = parse_args()
    maybe_exec_vllm(args)
    print(
        "[local-openai] No CUDA GPU; starting transformers CPU OpenAI-compatible server.",
        flush=True,
    )
    app = build_app(args)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
