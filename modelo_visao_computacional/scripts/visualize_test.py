"""Gera comparação visual entre a imagem original e a predição do modelo.

Uso, a partir de modelo_visao_computacional:
    ./.venv/Scripts/python.exe scripts/visualize_test.py
"""

from __future__ import annotations

import argparse
from math import ceil
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weights",
        type=Path,
        default=PROJECT_ROOT / "runs" / "train" / "pecas_6classes_320" / "weights" / "best.pt",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=PROJECT_ROOT / "data" / "yolo" / "images" / "test",
    )
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "runs" / "visual_test")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--show", action="store_true", help="Mostra cada comparação; pressione espaço para avançar")
    return parser.parse_args()


def add_title(image: np.ndarray, title: str, color: tuple[int, int, int]) -> np.ndarray:
    header_height = 38
    header = np.full((header_height, image.shape[1], 3), color, dtype=np.uint8)
    cv2.putText(header, title, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return np.vstack((header, image))


def build_comparison(original: np.ndarray, prediction: np.ndarray) -> np.ndarray:
    original = add_title(original, "Original", (65, 65, 65))
    prediction = add_title(prediction, "Predicao do modelo", (37, 109, 51))
    separator = np.full((original.shape[0], 12, 3), 245, dtype=np.uint8)
    return np.hstack((original, separator, prediction))


def create_contact_sheets(images: list[np.ndarray], output: Path, columns: int = 2, rows: int = 3) -> None:
    """Cria pranchas para visualizar todas as comparações sem abrir 33 arquivos."""
    per_sheet = columns * rows
    for page in range(ceil(len(images) / per_sheet)):
        batch = images[page * per_sheet : (page + 1) * per_sheet]
        thumb_width = 640
        thumbs: list[np.ndarray] = []
        for image in batch:
            scale = thumb_width / image.shape[1]
            thumbs.append(cv2.resize(image, (thumb_width, int(image.shape[0] * scale))))
        thumb_height = max(image.shape[0] for image in thumbs)
        blank = np.full((thumb_height, thumb_width, 3), 235, dtype=np.uint8)
        thumbs.extend([blank.copy()] * (per_sheet - len(thumbs)))
        rows_images = [np.hstack(thumbs[index : index + columns]) for index in range(0, per_sheet, columns)]
        sheet = np.vstack(rows_images)
        cv2.imwrite(str(output / f"contato_{page + 1:02d}.jpg"), sheet)


def main() -> None:
    args = parse_args()
    weights = args.weights.resolve()
    images_dir = args.images.resolve()
    output = args.output.resolve()
    if not weights.is_file():
        raise SystemExit(f"Pesos não encontrados: {weights}")
    if not images_dir.is_dir():
        raise SystemExit(f"Pasta de teste não encontrada: {images_dir}")
    images = sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"Nenhuma imagem de teste em: {images_dir}")

    output.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(weights))
    comparisons: list[np.ndarray] = []
    total_detections = 0

    for index, image_path in enumerate(images, start=1):
        original = cv2.imread(str(image_path))
        if original is None:
            print(f"Ignorada (não foi possível abrir): {image_path.name}")
            continue
        result = model.predict(original, imgsz=args.imgsz, conf=args.confidence, verbose=False)[0]
        annotated = result.plot()
        comparison = build_comparison(original, annotated)
        cv2.imwrite(str(output / f"{index:02d}_{image_path.stem}_comparacao.jpg"), comparison)
        comparisons.append(comparison)
        total_detections += 0 if result.boxes is None else len(result.boxes)

        if args.show:
            cv2.imshow("Teste visual - espaco: proxima | q: sair", comparison)
            key = cv2.waitKey(0) & 0xFF
            if key in (ord("q"), 27):
                break

    if args.show:
        cv2.destroyAllWindows()
    create_contact_sheets(comparisons, output)
    print(f"Comparações geradas: {len(comparisons)}")
    print(f"Detecções totais com confiança >= {args.confidence:.2f}: {total_detections}")
    print(f"Abra as imagens em: {output}")


if __name__ == "__main__":
    main()
