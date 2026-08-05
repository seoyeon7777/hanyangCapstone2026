#!/usr/bin/env bash
# Start OpenAI-compatible vLLM server for Qwen2.5-VL-7B-Instruct-AWQ.
# Auto-tunes --max-model-len and --gpu-memory-utilization from GPU VRAM.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${D2G_ROOT:-/workspace/design2garmentcode-impl}"
MODEL_DIR="${MODEL_DIR:-$ROOT/lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
SERVED_NAME="${SERVED_NAME:-Qwen2.5-VL-7B-Instruct-AWQ}"

if [[ ! -d "$MODEL_DIR" ]]; then
  echo "ERROR: model directory not found: $MODEL_DIR" >&2
  exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. Qwen2.5-VL-7B-Instruct-AWQ via vLLM requires an NVIDIA GPU." >&2
  exit 1
fi

VRAM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1 | tr -d ' ')"
if [[ -z "${VRAM_MB}" ]]; then
  echo "ERROR: failed to read GPU VRAM." >&2
  exit 1
fi

# Defaults tuned for AWQ 7B VL (weights ~6.5GB + KV cache + vision activations)
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-}"
EXTRA_VLLM_ARGS=(--limit-mm-per-prompt image=2)

if [[ -z "$MAX_MODEL_LEN" || -z "$GPU_MEM_UTIL" ]]; then
  if (( VRAM_MB < 7000 )); then
    echo "ERROR: GPU VRAM ${VRAM_MB} MiB is too small for Qwen2.5-VL-7B-Instruct-AWQ (need ~8GB+)." >&2
    exit 1
  elif (( VRAM_MB < 10000 )); then
    echo "WARN: VRAM ${VRAM_MB} MiB (e.g. 3070 Ti 8GB) is tight; using max-model-len=1024." >&2
    MAX_MODEL_LEN="${MAX_MODEL_LEN:-1024}"
    GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.95}"
    EXTRA_VLLM_ARGS=(--enforce-eager --limit-mm-per-prompt image=1)
  elif (( VRAM_MB < 14000 )); then
    MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"
    GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.90}"
  elif (( VRAM_MB < 20000 )); then
    MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
    GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.85}"
  elif (( VRAM_MB < 26000 )); then
    MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
    GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.90}"
  else
    MAX_MODEL_LEN="${MAX_MODEL_LEN:-16384}"
    GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.92}"
  fi
fi

echo "GPU VRAM: ${VRAM_MB} MiB"
echo "Using --max-model-len=${MAX_MODEL_LEN} --gpu-memory-utilization=${GPU_MEM_UTIL}"
echo "Serving ${MODEL_DIR} as ${SERVED_NAME} on http://${HOST}:${PORT}/v1"

# Prefer project venv / conda if present
if [[ -x /workspace/vllm-venv/bin/python ]]; then
  PYTHON=/workspace/vllm-venv/bin/python
elif command -v conda >/dev/null 2>&1 && conda run -n d2g python -c "import vllm" >/dev/null 2>&1; then
  PYTHON="conda run -n d2g --no-capture-output python"
else
  PYTHON=python
fi

exec $PYTHON -m vllm.entrypoints.openai.api_server \
  --model "$MODEL_DIR" \
  --served-model-name "$SERVED_NAME" \
  --host "$HOST" \
  --port "$PORT" \
  --quantization awq \
  --dtype float16 \
  --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization "$GPU_MEM_UTIL" \
  --trust-remote-code \
  "${EXTRA_VLLM_ARGS[@]}"
