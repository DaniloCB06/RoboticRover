"""Copia imagens únicas para anotação e registra as cópias exatas ignoradas.

Uso (a partir de modelo_visao_computacional):
    python scripts/prepare_images.py --source ../Fotos_pecas
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from pathlib import Path


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_name(source: Path, digest: str) -> str:
    """Evita colisões de nome depois de achatar a árvore de diretórios."""
    return f"{source.stem}-{digest[:12]}{source.suffix.lower()}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Pasta original das fotos")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/unlabeled/images"),
        help="Pasta de imagens a anotar",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/unlabeled/manifest.csv"),
        help="CSV que liga cada imagem preparada à sua origem",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Permite substituir uma imagem de saída já existente",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    manifest = args.manifest.resolve()

    if not source.is_dir():
        raise SystemExit(f"Pasta de origem não encontrada: {source}")

    files = sorted(
        path for path in source.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not files:
        raise SystemExit(f"Nenhuma imagem encontrada em: {source}")

    output.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    first_by_hash: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    copied = duplicates = 0

    for image in files:
        digest = sha256(image)
        relative = image.relative_to(source).as_posix()
        if digest in first_by_hash:
            duplicates += 1
            rows.append(
                {
                    "prepared_name": "",
                    "source_relative": relative,
                    "sha256": digest,
                    "status": "duplicate",
                    "duplicate_of": first_by_hash[digest],
                }
            )
            continue

        name = unique_name(image, digest)
        destination = output / name
        if destination.exists() and not args.overwrite:
            raise SystemExit(
                f"Saída já existe: {destination}. Use --overwrite se ela puder ser substituída."
            )
        shutil.copy2(image, destination)
        first_by_hash[digest] = name
        copied += 1
        rows.append(
            {
                "prepared_name": name,
                "source_relative": relative,
                "sha256": digest,
                "status": "kept",
                "duplicate_of": "",
            }
        )

    with manifest.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Imagens encontradas: {len(files)}")
    print(f"Imagens únicas copiadas para anotação: {copied}")
    print(f"Cópias exatas ignoradas: {duplicates}")
    print(f"Manifesto: {manifest}")


if __name__ == "__main__":
    main()

