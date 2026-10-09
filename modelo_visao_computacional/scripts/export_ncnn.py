"""Exporta o melhor checkpoint YOLO para NCNN, apropriado ao Raspberry Pi."""

from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True, help="Arquivo best.pt do treinamento")
    parser.add_argument("--imgsz", type=int, default=320)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.weights.is_file():
        raise SystemExit(f"Checkpoint não encontrado: {args.weights}")
    exported = YOLO(str(args.weights)).export(format="ncnn", imgsz=args.imgsz)
    print(f"Modelo NCNN exportado em: {exported}")


if __name__ == "__main__":
    main()

