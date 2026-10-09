"""Valida anotações no formato YOLO antes do split e do treinamento.

Uso:
    python scripts/validate_annotations.py \
        --images data/annotated/images --labels data/annotated/labels
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

# Permite executar este arquivo diretamente com `python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.classes import CLASS_NAMES, NUM_CLASSES


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument(
        "--allow-empty-labels",
        action="store_true",
        help="Aceita imagens sem .txt (útil somente para imagens negativas intencionais)",
    )
    return parser.parse_args()


def validate_line(line: str, line_number: int, label_path: Path) -> tuple[int, str | None]:
    parts = line.split()
    if len(parts) != 5:
        return -1, f"{label_path}:{line_number}: esperado 5 valores, recebido {len(parts)}"
    try:
        class_id = int(parts[0])
        values = [float(value) for value in parts[1:]]
    except ValueError:
        return -1, f"{label_path}:{line_number}: valores não numéricos"
    if not 0 <= class_id < NUM_CLASSES:
        return -1, f"{label_path}:{line_number}: classe {class_id} fora de 0..{NUM_CLASSES - 1}"
    x_center, y_center, width, height = values
    if not all(0.0 <= value <= 1.0 for value in values):
        return -1, f"{label_path}:{line_number}: coordenadas devem estar entre 0 e 1"
    if width <= 0 or height <= 0:
        return -1, f"{label_path}:{line_number}: largura e altura devem ser positivas"
    if x_center - width / 2 < 0 or x_center + width / 2 > 1:
        return -1, f"{label_path}:{line_number}: caixa ultrapassa limites horizontais"
    if y_center - height / 2 < 0 or y_center + height / 2 > 1:
        return -1, f"{label_path}:{line_number}: caixa ultrapassa limites verticais"
    return class_id, None


def main() -> None:
    args = parse_args()
    images = sorted(path for path in args.images.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"Nenhuma imagem encontrada em: {args.images}")
    if not args.labels.is_dir():
        raise SystemExit(f"Pasta de rótulos não encontrada: {args.labels}")

    errors: list[str] = []
    counts: Counter[int] = Counter()
    empty = 0
    for image in images:
        label_path = args.labels / f"{image.stem}.txt"
        if not label_path.exists():
            if args.allow_empty_labels:
                empty += 1
                continue
            errors.append(f"Rótulo ausente: {label_path}")
            continue
        lines = [line.strip() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            empty += 1
        for line_number, line in enumerate(lines, start=1):
            class_id, error = validate_line(line, line_number, label_path)
            if error:
                errors.append(error)
            else:
                counts[class_id] += 1

    print(f"Imagens verificadas: {len(images)}")
    print(f"Imagens sem caixas: {empty}")
    print("Ocorrências por classe:")
    for class_id, name in enumerate(CLASS_NAMES):
        print(f"  {class_id} ({name}): {counts[class_id]}")

    if errors:
        print("\nErros encontrados:")
        for error in errors[:30]:
            print(f"  - {error}")
        if len(errors) > 30:
            print(f"  ... e mais {len(errors) - 30} erro(s)")
        raise SystemExit(1)
    if any(counts[class_id] == 0 for class_id in range(NUM_CLASSES)):
        raise SystemExit("Há pelo menos uma classe sem exemplos anotados.")
    print("\nAnotações válidas.")


if __name__ == "__main__":
    main()
