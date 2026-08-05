#!/usr/bin/env python3
"""의류 분류기 가중치 학습 (외부 ML 프레임워크 없이 Softmax SGD).

사용법:
  # 합성 샘플로 빠른 학습 (기본)
  python scripts/train_garment_classifier.py --out assets/clothing/classifier_weights.json

  # 라벨 폴더: data/<label>/*.png
  python scripts/train_garment_classifier.py --data-dir data/garments --epochs 80

학습 후 `CLASSIFIER_WEIGHTS=/path/to/classifier_weights.json` 로 로드한다.
(기본 hand-tuned 가중치는 환경변수 없이 유지)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import tempfile
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pipeline.adapters.garment_classifier import (  # noqa: E402
    LABELS,
    _WEIGHTS,
    extract_features,
)


def _softmax(logits: list[float]) -> list[float]:
    m = max(logits)
    ex = [math.exp(v - m) for v in logits]
    s = sum(ex) or 1.0
    return [e / s for e in ex]


def _scores(weights: dict, feats: list[float]) -> list[float]:
    out = []
    for label in LABELS:
        cfg = weights[label]
        s = float(cfg["bias"])
        for wi, fi in zip(cfg["w"], feats):
            s += wi * fi
        out.append(s)
    return out


def _clone_weights(src: dict | None = None) -> dict:
    base = src or _WEIGHTS
    return {
        lab: {"bias": float(base[lab]["bias"]), "w": [float(x) for x in base[lab]["w"]]}
        for lab in LABELS
    }


def make_synthetic_sample(label: str, rng: random.Random, out_dir: str) -> str:
    """라벨별 대략적 실루엣 합성 PNG."""
    from PIL import Image, ImageDraw

    path = os.path.join(out_dir, f"{label}_{rng.randint(0, 1_000_000)}.png")
    w, h = 160, 220
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (
        rng.randint(30, 220),
        rng.randint(30, 220),
        rng.randint(30, 220),
        255,
    )
    cx, cy = w // 2, h // 2

    if label in ("pants", "shorts"):
        torso_h = 40 if label == "shorts" else 55
        leg_h = 70 if label == "shorts" else 140
        d.rectangle([cx - 28, 30, cx + 28, 30 + torso_h], fill=color)
        gap = 8 + rng.randint(0, 6)
        d.rectangle([cx - 30, 30 + torso_h, cx - gap, 30 + torso_h + leg_h], fill=color)
        d.rectangle([cx + gap, 30 + torso_h, cx + 30, 30 + torso_h + leg_h], fill=color)
    elif label == "skirt":
        d.polygon([(cx - 25, 40), (cx + 25, 40), (cx + 55, 180), (cx - 55, 180)], fill=color)
    elif label == "dress":
        d.polygon([(cx - 30, 25), (cx + 30, 25), (cx + 50, 200), (cx - 50, 200)], fill=color)
    elif label == "hoodie":
        d.rectangle([cx - 45, 50, cx + 45, 180], fill=color)
        d.ellipse([cx - 22, 18, cx + 22, 55], fill=color)  # hood-ish
    elif label == "jacket":
        d.rectangle([cx - 50, 40, cx + 50, 175], fill=color)
        d.rectangle([cx - 8, 50, cx + 8, 170], fill=(20, 20, 20, 200))  # open front
    else:  # tshirt
        d.rectangle([cx - 48, 55, cx + 48, 160], fill=color)
        d.rectangle([cx - 70, 55, cx - 40, 95], fill=color)
        d.rectangle([cx + 40, 55, cx + 70, 95], fill=color)

    # jitter crop noise
    if rng.random() < 0.3:
        x0 = rng.randint(0, max(1, w - 30))
        y0 = rng.randint(0, max(1, h - 30))
        x1 = rng.randint(x0 + 10, w)
        y1 = rng.randint(y0 + 10, h)
        d.ellipse([x0, y0, x1, y1], fill=(0, 0, 0, 0))
    img.save(path)
    return path


def load_labeled_dir(data_dir: str) -> list[tuple[str, str]]:
    samples = []
    for label in LABELS:
        folder = os.path.join(data_dir, label)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                samples.append((label, os.path.join(folder, name)))
    return samples


def build_dataset(
    data_dir: str | None,
    synthetic_per_class: int,
    seed: int,
) -> list[tuple[str, list[float]]]:
    rng = random.Random(seed)
    pairs: list[tuple[str, str]] = []
    if data_dir:
        pairs.extend(load_labeled_dir(data_dir))
    tmp = tempfile.mkdtemp(prefix="clf_syn_")
    for label in LABELS:
        for _ in range(synthetic_per_class):
            pairs.append((label, make_synthetic_sample(label, rng, tmp)))

    dataset: list[tuple[str, list[float]]] = []
    for label, path in pairs:
        feats = extract_features(path)
        if feats:
            dataset.append((label, feats))
    return dataset


def train(
    dataset: list[tuple[str, list[float]]],
    epochs: int = 60,
    lr: float = 0.08,
    l2: float = 1e-3,
    seed: int = 0,
    init: dict | None = None,
) -> tuple[dict, dict[str, Any]]:
    rng = random.Random(seed)
    weights = _clone_weights(init)
    label_index = {lab: i for i, lab in enumerate(LABELS)}
    history = []

    for ep in range(epochs):
        rng.shuffle(dataset)
        loss_sum = 0.0
        correct = 0
        for label, feats in dataset:
            logits = _scores(weights, feats)
            probs = _softmax(logits)
            yi = label_index[label]
            loss_sum += -math.log(max(probs[yi], 1e-9))
            pred = max(range(len(LABELS)), key=lambda i: probs[i])
            if pred == yi:
                correct += 1
            # gradient of softmax CE
            for j, lab in enumerate(LABELS):
                err = probs[j] - (1.0 if j == yi else 0.0)
                weights[lab]["bias"] -= lr * (err + l2 * weights[lab]["bias"])
                for k, fk in enumerate(feats):
                    weights[lab]["w"][k] -= lr * (err * fk + l2 * weights[lab]["w"][k])
        n = max(1, len(dataset))
        history.append({"epoch": ep + 1, "loss": round(loss_sum / n, 4), "acc": round(correct / n, 4)})

    # final eval
    cm = {a: {b: 0 for b in LABELS} for a in LABELS}
    correct = 0
    for label, feats in dataset:
        probs = _softmax(_scores(weights, feats))
        pred = LABELS[max(range(len(LABELS)), key=lambda i: probs[i])]
        cm[label][pred] += 1
        if pred == label:
            correct += 1
    metrics = {
        "samples": len(dataset),
        "epochs": epochs,
        "train_acc": round(correct / max(1, len(dataset)), 4),
        "history_tail": history[-5:],
        "confusion": cm,
    }
    return weights, metrics


def maybe_autoload_path() -> str:
    return os.environ.get("CLASSIFIER_WEIGHTS") or os.path.join(
        ROOT, "assets", "clothing", "classifier_weights.json"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--synthetic", type=int, default=24, help="클래스당 합성 샘플 수")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--lr", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "clothing", "classifier_weights.json"))
    args = ap.parse_args()

    dataset = build_dataset(args.data_dir, args.synthetic, args.seed)
    if len(dataset) < 10:
        raise SystemExit(f"데이터 부족: {len(dataset)}")
    weights, metrics = train(dataset, epochs=args.epochs, lr=args.lr, seed=args.seed)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"labels": list(LABELS), "weights": weights, "metrics": metrics}, f, ensure_ascii=False, indent=2)
    # flat format for load_custom_weights
    flat_path = args.out
    with open(flat_path, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)
    meta_path = args.out.replace(".json", "_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(json.dumps({"out": flat_path, "meta": meta_path, **{k: metrics[k] for k in ("samples", "train_acc", "epochs")}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
