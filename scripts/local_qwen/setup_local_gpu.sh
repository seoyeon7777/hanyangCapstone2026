#!/usr/bin/env bash
# One-shot local setup for Design2GarmentCode + Qwen2.5-VL-7B-AWQ on NVIDIA GPU
# (e.g. RTX 3070 Ti 8GB). Run this ON YOUR PC, not on the Cursor cloud agent.
#
# Usage:
#   bash scripts/local_qwen/setup_local_gpu.sh
#   # optional:
#   WORKDIR=~/d2g bash scripts/local_qwen/setup_local_gpu.sh

set -euo pipefail

WORKDIR="${WORKDIR:-$HOME/design2garmentcode-local}"
REPO_URL="${REPO_URL:-https://github.com/seoyeon7777/hanyangCapstone2026.git}"
REPO_BRANCH="${REPO_BRANCH:-cursor/local-qwen-awq-server-35e8}"
D2G_URL="${D2G_URL:-https://github.com/Style3D/design2garmentcode-impl.git}"
GDRIVE_PTH_ID="${GDRIVE_PTH_ID:-1CL7OLUq6fYcwoDuLRkBxtKNxJ0_G73U-}"

echo "==> Workdir: $WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. Install NVIDIA drivers first." >&2
  exit 1
fi
nvidia-smi -L || true

if ! command -v conda >/dev/null 2>&1; then
  echo "ERROR: conda not found. Install Miniconda/Anaconda first." >&2
  exit 1
fi

# --- repos ---
if [[ ! -d hanyangCapstone2026/.git ]]; then
  git clone "$REPO_URL" hanyangCapstone2026
fi
git -C hanyangCapstone2026 fetch origin "$REPO_BRANCH" || true
git -C hanyangCapstone2026 checkout "$REPO_BRANCH"
git -C hanyangCapstone2026 pull --ff-only origin "$REPO_BRANCH" || true

if [[ ! -d design2garmentcode-impl/.git ]]; then
  git clone "$D2G_URL" design2garmentcode-impl
fi

# copy helper scripts into d2g tree
mkdir -p design2garmentcode-impl/scripts
cp -f hanyangCapstone2026/scripts/local_qwen/local_openai_server.py \
      hanyangCapstone2026/scripts/local_qwen/start_local_llm.sh \
      hanyangCapstone2026/scripts/local_qwen/start_vllm_server.sh \
      design2garmentcode-impl/scripts/
chmod +x design2garmentcode-impl/scripts/*.sh

# --- conda envs ---
eval "$(conda shell.bash hook)"

if ! conda env list | awk '{print $1}' | grep -qx d2g; then
  echo "==> Creating conda env d2g (may take a while)..."
  conda env create -f design2garmentcode-impl/environment.yml || \
    echo "WARN: environment.yml create failed; create/fix d2g manually if needed."
fi

if ! conda env list | awk '{print $1}' | grep -qx llm-server; then
  echo "==> Creating conda env llm-server..."
  conda create -y -n llm-server python=3.11 pip
fi

echo "==> Installing vLLM into llm-server (CUDA)..."
conda activate llm-server
python -m pip install -U pip
python -m pip install "vllm" "huggingface_hub[cli]" gdown || \
  python -m pip install "vllm" huggingface_hub gdown

# --- models ---
QDIR="$WORKDIR/design2garmentcode-impl/lmm_utils/Qwen"
mkdir -p "$QDIR/qwen2vl_lora_mlp"

if [[ ! -f "$QDIR/Qwen2.5-VL-7B-Instruct-AWQ/config.json" ]]; then
  echo "==> Downloading Qwen2.5-VL-7B-Instruct-AWQ ..."
  hf download Qwen/Qwen2.5-VL-7B-Instruct-AWQ \
    --local-dir "$QDIR/Qwen2.5-VL-7B-Instruct-AWQ"
fi

if [[ ! -f "$QDIR/Qwen2-VL-2B-Instruct/config.json" ]]; then
  echo "==> Downloading Qwen2-VL-2B-Instruct ..."
  hf download Qwen/Qwen2-VL-2B-Instruct \
    --local-dir "$QDIR/Qwen2-VL-2B-Instruct"
fi

if [[ ! -f "$QDIR/qwen2vl_lora_mlp/model.pth" ]]; then
  echo "==> Downloading projector model.pth from Google Drive ..."
  gdown "$GDRIVE_PTH_ID" -O "$QDIR/qwen2vl_lora_mlp/model.pth"
fi

# --- system.json ---
cat > design2garmentcode-impl/system.json <<'EOF'
{
  "output": "./Logs/",
  "datasets_path": "",
  "datasets_sim": "",
  "sim_configs_path": "./assets/Sim_props",
  "bodies_default_path": "./assets/bodies",
  "body_samples_path": "",
  "model": {
    "vl_model": "Qwen2.5-VL-7B-Instruct-AWQ",
    "text_model": "Qwen2.5-VL-7B-Instruct-AWQ"
  },
  "api_keys": "dummy-local-key",
  "base_urls": "http://127.0.0.1:8000/v1",
  "param_model": "lmm_utils/Qwen/qwen2vl_lora_mlp/model.pth"
}
EOF

# Prefer not loading heavy projector at GUI boot on 8GB+tight systems
if grep -q 'Agent(model_init=True)' design2garmentcode-impl/gui.py 2>/dev/null; then
  sed -i.bak 's/Agent(model_init=True)/Agent(model_init=False)/' design2garmentcode-impl/gui.py || true
fi

cat > "$WORKDIR/start_all.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
WORKDIR="$WORKDIR"
eval "\$(conda shell.bash hook)"

export D2G_ROOT="\$WORKDIR/design2garmentcode-impl"
export MODEL_DIR="\$D2G_ROOT/lmm_utils/Qwen/Qwen2.5-VL-7B-Instruct-AWQ"

echo "Starting LLM on GPU (terminal stays attached)..."
echo "In another terminal run:"
echo "  conda activate d2g"
echo "  cd \$D2G_ROOT"
echo "  unset OPENAI_API_KEY"
echo "  python gui.py --host 127.0.0.1 --port 8080"
echo "Then open http://127.0.0.1:8080"
echo

conda activate llm-server
cd "\$WORKDIR/hanyangCapstone2026"
exec bash scripts/local_qwen/start_local_llm.sh
EOF
chmod +x "$WORKDIR/start_all.sh"

echo
echo "=============================================="
echo "Setup finished."
echo "Workdir: $WORKDIR"
echo
echo "Terminal 1 (LLM / GPU):"
echo "  bash $WORKDIR/start_all.sh"
echo
echo "Terminal 2 (GUI):"
echo "  conda activate d2g"
echo "  cd $WORKDIR/design2garmentcode-impl"
echo "  unset OPENAI_API_KEY"
echo "  python gui.py --host 127.0.0.1 --port 8080"
echo
echo "Browser: http://127.0.0.1:8080"
echo "If CUDA OOM on 3070 Ti:"
echo "  MAX_MODEL_LEN=768 GPU_MEM_UTIL=0.92 bash $WORKDIR/hanyangCapstone2026/scripts/local_qwen/start_vllm_server.sh"
echo "=============================================="
