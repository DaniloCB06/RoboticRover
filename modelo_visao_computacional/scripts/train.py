"""Treina o detector de seis tipos de peças a 320 px."""

from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO
from vision.classes import CLASS_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_runtime_dataset_yaml(dataset_root: Path) -> Path:
    """Gera YAML com caminho absoluto para não depender do diretório atual."""
    required = [
        dataset_root / "images" / split
        for split in ("train", "val", "test")
    ]
    missing = [path for path in required if not path.is_dir()]
    if missing:
        formatted = "\n  - ".join(str(path) for path in missing)
        raise SystemExit(f"Dataset YOLO incompleto. Pastas ausentes:\n  - {formatted}")

    runtime_yaml = dataset_root / "dataset.runtime.yaml"
    quoted_path = dataset_root.resolve().as_posix().replace("'", "''")
    names = "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
    runtime_yaml.write_text(
        "# Gerado automaticamente por scripts/train.py; não versionar.\n"
        f"path: '{quoted_path}'\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        f"{names}\n",
        encoding="utf-8",
    )
    return runtime_yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="YAML externo opcional; por padrão usa data/yolo e gera um YAML absoluto",
    )
    parser.add_argument("--model", default=str(PROJECT_ROOT / "yolo26n.pt"), help="Checkpoint inicial")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--batch", type=int, default=8, help="8 é seguro para CPU e GPUs de 4 GB")
    parser.add_argument("--device", default="auto", help="auto, 0 ou cpu")
    parser.add_argument("--workers", type=int, default=2, help="Processos de carregamento de imagens")
    parser.add_argument("--project", type=Path, default=PROJECT_ROOT / "runs" / "train")
    parser.add_argument("--name", default="pecas_6classes_320")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_yaml = args.data.resolve() if args.data is not None else create_runtime_dataset_yaml(PROJECT_ROOT / "data" / "yolo")
    if not data_yaml.is_file():
        raise SystemExit(f"Dataset YAML não encontrado: {data_yaml}")
    device = None if args.device.lower() == "auto" else args.device
    model = YOLO(args.model)
    train_arguments = {
        "data": str(data_yaml),
        "imgsz": args.imgsz,
        "epochs": args.epochs,
        "batch": args.batch,
        "project": str(args.project),
        "name": args.name,
        "seed": args.seed,
        "pretrained": True,
        "patience": 35,
        "cos_lr": True,
        "degrees": 12.0,
        "translate": 0.10,
        "scale": 0.35,
        "perspective": 0.0005,
        "fliplr": 0.5,
        "hsv_h": 0.015,
        "hsv_s": 0.45,
        "hsv_v": 0.35,
        "mosaic": 0.5,
        "close_mosaic": 15,
        "workers": args.workers,
    }
    if device is not None:
        train_arguments["device"] = device
    model.train(**train_arguments)
    save_dir = getattr(getattr(model, "trainer", None), "save_dir", args.project / args.name)
    print(f"Treinamento concluído. Resultados: {save_dir}")


if __name__ == "__main__":
    main()
