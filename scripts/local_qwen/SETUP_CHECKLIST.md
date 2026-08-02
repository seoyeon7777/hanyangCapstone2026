# Design2GarmentCode full local setup checklist

## Required (pattern generation / PARSE DESIGN)

| Item | Path / value | Status target |
|------|----------------|---------------|
| Repo | `design2garmentcode-impl/` | cloned |
| Conda env | `d2g` from `environment.yml` | installed |
| MMUA local API | `http://127.0.0.1:8000/v1` | running |
| `system.json` | `api_keys=dummy-local-key`, `base_urls=http://127.0.0.1:8000/v1`, model name `Qwen2.5-VL-7B-Instruct-AWQ` | set |
| AWQ VL model | `lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ/` | downloaded |
| Projector base | `lmm_utils/Qwen/Qwen2-VL-2B-Instruct/` | downloaded |
| Projector weights | `lmm_utils/Qwen/qwen2vl_lora_mlp/model.pth` | downloaded |
| Do **not** set `OPENAI_API_KEY` | env override forces gpt-4o in `lmm_utils/core.py` | unset |

## Optional

| Item | Notes |
|------|------|
| NVIDIA GPU + vLLM | Prefer `start_vllm_server.sh` / GPU path in `start_local_llm.sh` |
| GarmentCode Warp Simulator | 3D cloth sim / visualization only |

## Start local LLM

```bash
bash scripts/local_qwen/start_local_llm.sh
# or
bash design2garmentcode-impl/scripts/start_local_llm.sh
```

## GUI

```bash
cd design2garmentcode-impl
conda activate d2g
# ensure OPENAI_API_KEY is unset
python gui.py
```
