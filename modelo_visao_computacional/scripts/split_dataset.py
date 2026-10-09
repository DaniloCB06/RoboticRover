"""Cria um dataset YOLO train/val/test sem espalhar frames vizinhos entre splits.

Usa o horário no nome WIN_AAAAMMDD_HH_MM_SS para formar blocos temporais. Ajuste
--group-minutes ou --group-seconds de acordo com a duração de cada tomada.
"""

from __future__ import annotations

import argparse
import math
import random
import re
import shutil
from collections import defaultdict
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
TIMESTAMP = re.compile(r"WIN_(\d{8})_(\d{2})_(\d{2})_(\d{2})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/yolo"))
    parser.add_argument("--group-minutes", type=int, default=5)
    parser.add_argument(
        "--group-seconds",
        type=int,
        default=None,
        help="Granularidade temporal exata; substitui --group-minutes quando informado",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=float, default=0.70)
    parser.add_argument("--val", type=float, default=0.20)
    parser.add_argument("--test", type=float, default=0.10)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def group_name(image: Path, group_seconds: int) -> str:
    match = TIMESTAMP.search(image.name)
    if not match:
        raise ValueError(f"Nome sem timestamp WIN_AAAAMMDD_HH_MM_SS: {image.name}")
    day, hour, minute, second = match.groups()
    elapsed_seconds = int(hour) * 3600 + int(minute) * 60 + int(second)
    block = elapsed_seconds // group_seconds
    return f"{day}-bloco-{block:04d}"


def label_class_counts(label: Path) -> dict[int, int]:
    counts: dict[int, int] = defaultdict(int)
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts:
            counts[int(parts[0])] += 1
    return counts


def choose_splits(
    groups: dict[str, list[Path]],
    ratios: dict[str, float],
    seed: int,
    group_class_counts: dict[str, dict[int, int]],
) -> dict[str, str]:
    if len(groups) < 3:
        raise SystemExit(
            "São necessários pelo menos 3 blocos temporais para train/val/test. "
            "Colete mais sessões ou reduza --group-minutes."
        )
    total_images = sum(len(images) for images in groups.values())
    targets = {name: ratio * total_images for name, ratio in ratios.items()}
    assigned_sizes = {name: 0 for name in ratios}
    assignment: dict[str, str] = {}
    randomizer = random.Random(seed)
    class_ids = sorted({class_id for counts in group_class_counts.values() for class_id in counts})

    # Garante que validation e test tenham ao menos uma ocorrência de cada
    # classe. Cada grupo continua íntegro; nunca misturamos frames próximos.
    for split in ("val", "test"):
        for class_id in class_ids:
            candidates = [
                group
                for group in groups
                if group not in assignment and group_class_counts[group].get(class_id, 0) > 0
            ]
            if not candidates:
                raise SystemExit(
                    f"Não há bloco temporal livre para colocar a classe {class_id} em {split}. "
                    "Reduza --group-seconds ou colete mais sessões."
                )
            randomizer.shuffle(candidates)
            group = max(
                candidates,
                key=lambda item: (
                    len(group_class_counts[item]),
                    group_class_counts[item].get(class_id, 0) / len(groups[item]),
                ),
            )
            assignment[group] = split
            assigned_sizes[split] += len(groups[group])

    # Treino recebe o restante. Se um grupo já escolhido cobre várias classes,
    # isto ainda preserva a cobertura por classe nos conjuntos de avaliação.
    ordered = sorted((group for group in groups if group not in assignment), key=lambda name: (-len(groups[name]), name))
    randomizer.shuffle(ordered)
    for group in ordered:
        split = max(ratios, key=lambda name: targets[name] - assigned_sizes[name])
        assignment[group] = split
        assigned_sizes[split] += len(groups[group])
    return assignment


def sanitized_yolo_labels(label: Path) -> tuple[str, int]:
    """Recorta caixas que ultrapassam a borda, preservando objetos parciais.

    Alguns anotadores exportam caixas parcialmente fora da imagem. O YOLO exige
    coordenadas normalizadas dentro do intervalo [0, 1].
    """
    corrected = 0
    sanitized_lines: list[str] = []
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 5:
            raise ValueError(f"Rótulo inválido em {label}: {line!r}")
        class_id = int(parts[0])
        x_center, y_center, width, height = (float(value) for value in parts[1:])
        x1, y1 = max(0.0, x_center - width / 2), max(0.0, y_center - height / 2)
        x2, y2 = min(1.0, x_center + width / 2), min(1.0, y_center + height / 2)
        if x2 <= x1 or y2 <= y1:
            corrected += 1
            continue
        new_values = ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)
        if any(abs(before - after) > 1e-8 for before, after in zip((x_center, y_center, width, height), new_values)):
            corrected += 1
        sanitized_lines.append(f"{class_id} " + " ".join(f"{value:.8f}" for value in new_values))
    return "\n".join(sanitized_lines) + ("\n" if sanitized_lines else ""), corrected


def main() -> None:
    args = parse_args()
    group_seconds = args.group_seconds if args.group_seconds is not None else args.group_minutes * 60
    if group_seconds <= 0:
        raise SystemExit("A granularidade temporal deve ser maior que zero")
    ratios = {"train": args.train, "val": args.val, "test": args.test}
    if not math.isclose(sum(ratios.values()), 1.0, abs_tol=1e-9):
        raise SystemExit("As proporções --train, --val e --test devem somar 1.0")
    images = sorted(path for path in args.images.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"Nenhuma imagem encontrada em: {args.images}")
    groups: dict[str, list[Path]] = defaultdict(list)
    group_class_counts: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for image in images:
        label = args.labels / f"{image.stem}.txt"
        if not label.exists():
            raise SystemExit(f"Rótulo ausente: {label}. Execute validate_annotations.py antes.")
        group = group_name(image, group_seconds)
        groups[group].append(image)
        for class_id, count in label_class_counts(label).items():
            group_class_counts[group][class_id] += count
    assignment = choose_splits(groups, ratios, args.seed, group_class_counts)

    output = args.output.resolve()
    if output.exists():
        if not args.overwrite:
            raise SystemExit(f"Saída já existe: {output}. Use --overwrite para recriá-la.")
        shutil.rmtree(output)
    for split in ratios:
        (output / "images" / split).mkdir(parents=True)
        (output / "labels" / split).mkdir(parents=True)

    counts = defaultdict(int)
    corrected_labels = 0
    for group, group_images in groups.items():
        split = assignment[group]
        for image in group_images:
            label = args.labels / f"{image.stem}.txt"
            shutil.copy2(image, output / "images" / split / image.name)
            sanitized, corrections = sanitized_yolo_labels(label)
            (output / "labels" / split / label.name).write_text(sanitized, encoding="utf-8")
            corrected_labels += corrections
            counts[split] += 1

    print("Blocos temporais atribuídos:")
    for group in sorted(groups):
        print(f"  {group}: {assignment[group]} ({len(groups[group])} imagens)")
    print("\nImagens por split:")
    for split in ratios:
        print(f"  {split}: {counts[split]}")
    print(f"Caixas normalizadas/recortadas nas bordas: {corrected_labels}")


if __name__ == "__main__":
    main()
