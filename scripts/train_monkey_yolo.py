#!/usr/bin/env python3
"""
Fine-tune YOLOv8 on a custom dataset (e.g. person + monkey).

Requires: pip install ultralytics (already in requirements.txt)

Example:
  python scripts/train_monkey_yolo.py --data training/example_monkey_dataset.yaml --epochs 50

After training, copy runs/detect/<name>/weights/best.pt to models/ and set in .env:
  YOLO_MODEL_PATH=models/best.pt
  EXTRA_ANIMAL_CLASS_IDS=<monkey_class_index>
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train YOLOv8 with a YOLO-format dataset (monkey / custom classes)."
    )
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Path to dataset YAML (see training/example_monkey_dataset.yaml)",
    )
    parser.add_argument(
        "--model",
        default="yolov8s.pt",
        help="Base checkpoint (Ultralytics downloads if missing)",
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument(
        "--project",
        default="runs/detect",
        help="Ultralytics project directory under the repo root",
    )
    parser.add_argument("--name", default="monkey", help="Run name (subfolder under project)")
    args = parser.parse_args()

    if not args.data.is_file():
        raise SystemExit(f"Dataset YAML not found: {args.data.resolve()}")

    from ultralytics import YOLO

    model = YOLO(str(args.model))
    model.train(
        data=str(args.data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
    )

    weights_dir = Path(args.project) / args.name / "weights"
    best = weights_dir / "best.pt"
    print(f"\nDone. If training succeeded, best weights: {best.resolve()}")
    print("Copy to models/ and set YOLO_MODEL_PATH and EXTRA_ANIMAL_CLASS_IDS in .env (see training/README.md).")


if __name__ == "__main__":
    main()
