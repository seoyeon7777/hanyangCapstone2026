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
        # 짧고 아래로 넓게 벌어짐 (bipodal 없음)
        d.polygon([(cx - 28, 55), (cx + 28, 55), (cx + 62, 175), (cx - 62, 175)], fill=color)
    elif label == "dress":
        d.polygon([(cx - 30, 25), (cx + 30, 25), (cx + 50, 200), (cx - 50, 200)], fill=color)
    elif label == "hoodie":
        # 가로로 넓은 몸통 + 후드 (세로비 낮춤 → pants와 구분)
        d.rectangle([cx - 55, 70, cx + 55, 185], fill=color)
        d.ellipse([cx - 28, 28, cx + 28, 78], fill=color)
        d.rectangle([cx - 70, 75, cx - 48, 120], fill=color)
        d.rectangle([cx + 48, 75, cx + 70, 120], fill=color)
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
    val_dataset: list[tuple[str, list[float]]] | None = None,
) -> tuple[dict, dict[str, Any]]:
    rng = random.Random(seed)
    weights = _clone_weights(init)
    best_weights = _clone_weights(weights)
    best_val = -1.0
    label_index = {lab: i for i, lab in enumerate(LABELS)}
    history = []

    def _eval(ds, wts):
        cm = {a: {b: 0 for b in LABELS} for a in LABELS}
        correct = 0
        loss_sum = 0.0
        for label, feats in ds:
            logits = _scores(wts, feats)
            probs = _softmax(logits)
            yi = label_index[label]
            loss_sum += -math.log(max(probs[yi], 1e-9))
            pred = LABELS[max(range(len(LABELS)), key=lambda i: probs[i])]
            cm[label][pred] += 1
            if pred == label:
                correct += 1
        n = max(1, len(ds))
        recalls = {}
        for lab in LABELS:
            row = sum(cm[lab].values()) or 1
            recalls[lab] = round(cm[lab][lab] / row, 4)
        macro_f1 = round(sum(recalls.values()) / len(LABELS), 4)  # recall proxy
        return {
            "acc": round(correct / n, 4),
            "loss": round(loss_sum / n, 4),
            "confusion": cm,
            "per_class_recall": recalls,
            "macro_f1": macro_f1,
            "samples": len(ds),
        }

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
            for j, lab in enumerate(LABELS):
                err = probs[j] - (1.0 if j == yi else 0.0)
                weights[lab]["bias"] -= lr * (err + l2 * weights[lab]["bias"])
                for k, fk in enumerate(feats):
                    weights[lab]["w"][k] -= lr * (err * fk + l2 * weights[lab]["w"][k])
        n = max(1, len(dataset))
        entry = {"epoch": ep + 1, "loss": round(loss_sum / n, 4), "acc": round(correct / n, 4)}
        if val_dataset:
            v = _eval(val_dataset, weights)
            entry["val_acc"] = v["acc"]
            entry["val_loss"] = v["loss"]
            entry["val_macro_f1"] = v["macro_f1"]
            score = v["macro_f1"]
            if score >= best_val:
                best_val = score
                best_weights = _clone_weights(weights)
        history.append(entry)

    final_w = best_weights if val_dataset else weights
    train_m = _eval(dataset, final_w)
    metrics: dict[str, Any] = {
        "samples": len(dataset),
        "epochs": epochs,
        "train_acc": train_m["acc"],
        "train_macro_f1": train_m["macro_f1"],
        "history_tail": history[-5:],
        "confusion": train_m["confusion"],
        "per_class_recall": train_m["per_class_recall"],
        "held_out": False,
    }
    if val_dataset:
        val_m = _eval(val_dataset, final_w)
        metrics["held_out"] = True
        metrics["val_samples"] = val_m["samples"]
        metrics["val_acc"] = val_m["acc"]
        metrics["val_macro_f1"] = val_m["macro_f1"]
        metrics["val_loss"] = val_m["loss"]
        metrics["val_confusion"] = val_m["confusion"]
        metrics["val_per_class_recall"] = val_m["per_class_recall"]
        metrics["best_val_macro_f1"] = best_val
    return final_w, metrics


def stratified_split(
    dataset: list[tuple[str, list[float]]],
    *,
    val_ratio: float = 0.2,
    seed: int = 0,
) -> tuple[list, list]:
    rng = random.Random(seed)
    by: dict[str, list] = {lab: [] for lab in LABELS}
    for item in dataset:
        by[item[0]].append(item)
    train, val = [], []
    for lab, items in by.items():
        rng.shuffle(items)
        if not items:
            continue
        n_val = max(1, int(round(len(items) * val_ratio))) if len(items) >= 5 else 0
        if n_val >= len(items):
            n_val = max(0, len(items) // 5)
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    if not val:
        # too small — keep all in train
        return dataset, []
    return train, val


def maybe_autoload_path() -> str:
    return os.environ.get("CLASSIFIER_WEIGHTS") or os.path.join(
        ROOT, "assets", "clothing", "classifier_weights.json"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--synthetic", type=int, default=24, help="클래스당 합성 샘플 수 (0=실데이터만)")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--lr", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--no-holdout", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "clothing", "classifier_weights.json"))
    args = ap.parse_args()

    dataset = build_dataset(args.data_dir, args.synthetic, args.seed)
    if len(dataset) < 10:
        raise SystemExit(f"데이터 부족: {len(dataset)}")
    val: list = []
    train_ds = dataset
    if not args.no_holdout and args.val_ratio > 0:
        train_ds, val = stratified_split(dataset, val_ratio=args.val_ratio, seed=args.seed)
        if not train_ds:
            raise SystemExit("holdout 후 train 비어 있음")
    weights, metrics = train(
        train_ds,
        epochs=args.epochs,
        lr=args.lr,
        seed=args.seed,
        val_dataset=val or None,
    )
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # flat format for load_custom_weights
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(weights, f, ensure_ascii=False, indent=2)
    meta_path = args.out.replace(".json", "_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    summary = {
        "out": args.out,
        "meta": meta_path,
        "samples": metrics.get("samples"),
        "train_acc": metrics.get("train_acc"),
        "epochs": metrics.get("epochs"),
        "held_out": metrics.get("held_out"),
        "val_acc": metrics.get("val_acc"),
        "val_macro_f1": metrics.get("val_macro_f1"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
