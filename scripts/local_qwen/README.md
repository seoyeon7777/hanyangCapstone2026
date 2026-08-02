# Local Qwen2.5-VL-7B-Instruct-AWQ (OpenAI-compatible)

These scripts serve `Qwen2.5-VL-7B-Instruct-AWQ` at `http://127.0.0.1:8000/v1` for Design2GarmentCode without paid API keys.

## Prerequisites
1. Clone `https://github.com/Style3D/design2garmentcode-impl.git`
2. Create conda env: `conda env create -f environment.yml && conda activate d2g`
3. Download model into:
   `design2garmentcode-impl/lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ/`
4. Install server deps (Python 3.10–3.14 venv recommended):
   `python -m venv /workspace/vllm-venv && source /workspace/vllm-venv/bin/activate && pip install vllm gptqmodel pillow fastapi uvicorn`

## Start
```bash
export MODEL_DIR=/path/to/design2garmentcode-impl/lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ
bash scripts/local_qwen/start_local_llm.sh
```

- GPU present: uses vLLM; auto-sets `--max-model-len` and `--gpu-memory-utilization` from VRAM
- No GPU: transformers CPU OpenAI-compatible fallback

## system.json
```json
{
  "api_keys": "dummy-local-key",
  "base_urls": "http://127.0.0.1:8000/v1",
  "model": {
    "vl_model": "Qwen2.5-VL-7B-Instruct-AWQ",
    "text_model": "Qwen2.5-VL-7B-Instruct-AWQ"
  }
}
```
