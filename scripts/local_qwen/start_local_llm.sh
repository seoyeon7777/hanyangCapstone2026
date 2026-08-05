#!/usr/bin/env bash
# Start local OpenAI-compatible server for Qwen2.5-VL-7B-Instruct-AWQ.
# Uses vLLM on GPU (auto max-model-len / gpu-memory-utilization), else CPU fallback.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${D2G_ROOT:-/workspace/design2garmentcode-impl}"
MODEL_DIR="${MODEL_DIR:-$ROOT/lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
SERVED_NAME="${SERVED_NAME:-Qwen2.5-VL-7B-Instruct-AWQ}"
API_KEY="${API_KEY:-dummy-local-key}"

if [[ -x /home/ubuntu/miniconda3/envs/llm-server/bin/python ]]; then
  PYTHON=/home/ubuntu/miniconda3/envs/llm-server/bin/python
elif [[ -x "$HOME/miniconda3/envs/llm-server/bin/python" ]]; then
  PYTHON="$HOME/miniconda3/envs/llm-server/bin/python"
elif [[ -x /workspace/vllm-venv/bin/python ]]; then
  PYTHON=/workspace/vllm-venv/bin/python
elif [[ -x "$HOME/miniconda3/envs/d2g/bin/python" ]]; then
  PYTHON="$HOME/miniconda3/envs/d2g/bin/python"
else
  PYTHON=python3
fi

MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-}"

if command -v nvidia-smi >/dev/null 2>&1; then
  VRAM_MB="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1 | tr -d ' ')"
  echo "Detected GPU VRAM: ${VRAM_MB} MiB"
  if [[ -z "$MAX_MODEL_LEN" || -z "$GPU_MEM_UTIL" ]]; then
    if (( VRAM_MB < 7000 )); then
      echo "ERROR: VRAM ${VRAM_MB} MiB too small for AWQ 7B VL (need ~8GB+)." >&2
      exit 1
    elif (( VRAM_MB < 10000 )); then
      # RTX 3070 Ti 8GB: tight — short context + high util; may still OOM on large images
      echo "WARN: VRAM ${VRAM_MB} MiB is tight for Qwen2.5-VL-7B-AWQ; using aggressive 8GB settings." >&2
      MAX_MODEL_LEN="${MAX_MODEL_LEN:-1024}"
      GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.95}"
      export VLLM_ENFORCE_EAGER="${VLLM_ENFORCE_EAGER:-1}"
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
else
  echo "No nvidia-smi; using CPU fallback server."
  MAX_MODEL_LEN="${MAX_MODEL_LEN:-2048}"
  GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.0}"
fi

export GPU_MEM_UTIL
echo "Using PYTHON=$PYTHON"
echo "max-model-len=${MAX_MODEL_LEN} gpu-memory-utilization=${GPU_MEM_UTIL}"
echo "base_url=http://${HOST}:${PORT}/v1 api_key=${API_KEY}"

exec "$PYTHON" "$SCRIPT_DIR/local_openai_server.py" \
  --model "$MODEL_DIR" \
  --served-model-name "$SERVED_NAME" \
  --host "$HOST" \
  --port "$PORT" \
  --max-model-len "$MAX_MODEL_LEN" \
  --api-key "$API_KEY"
