"""Detecta e classifica as seis peças em tempo real pela webcam.

Aceita tanto um checkpoint YOLO (.pt) quanto uma pasta *_ncnn_model exportada
para o Raspberry Pi. Pressione Q ou Esc para encerrar a janela.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
from ultralytics import YOLO


CLASS_NAMES = (
    "argola_grande",
    "argola_pequena",
    "cilindro_com_base",
    "dado_hexagonal",
    "helice",
    "paraboloide_hiperbolico",
)

COLORS = (
    (255, 150, 40),
    (40, 220, 255),
    (255, 80, 180),
    (80, 230, 80),
    (180, 100, 255),
    (70, 180, 255),
)


@dataclass
class Detection:
    class_id: int
    bbox: tuple[float, float, float, float]
    confidence: float


@dataclass
class Track(Detection):
    hits: int = 1
    missed: int = 0


def iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    """Calcula a interseção sobre união de duas caixas XYXY."""
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    area_first = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    area_second = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = area_first + area_second - intersection
    return intersection / union if union else 0.0


class TemporalFilter:
    """Evita que um único frame instável seja publicado como peça confirmada."""

    def __init__(self, confirmations: int, max_missed: int, match_iou: float) -> None:
        self.confirmations = confirmations
        self.max_missed = max_missed
        self.match_iou = match_iou
        self.tracks: list[Track] = []

    def update(self, detections: list[Detection]) -> list[Track]:
        unmatched_tracks = set(range(len(self.tracks)))
        for detection in detections:
            candidates = [
                index
                for index in unmatched_tracks
                if self.tracks[index].class_id == detection.class_id
                and iou(self.tracks[index].bbox, detection.bbox) >= self.match_iou
            ]
            if candidates:
                index = max(candidates, key=lambda item: iou(self.tracks[item].bbox, detection.bbox))
                track = self.tracks[index]
                track.bbox = detection.bbox
                track.confidence = detection.confidence
                track.hits += 1
                track.missed = 0
                unmatched_tracks.remove(index)
            else:
                self.tracks.append(Track(**detection.__dict__))

        for index in unmatched_tracks:
            self.tracks[index].missed += 1
        self.tracks = [track for track in self.tracks if track.missed <= self.max_missed]
        return self.tracks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="Arquivo .pt (computador) ou pasta *_ncnn_model (Raspberry Pi)",
    )
    parser.add_argument("--camera", type=int, default=0, help="Índice da câmera no OpenCV")
    parser.add_argument("--width", type=int, default=640, help="Largura solicitada à câmera")
    parser.add_argument("--height", type=int, default=480, help="Altura solicitada à câmera")
    parser.add_argument("--imgsz", type=int, default=320, help="Resolução de entrada do detector")
    parser.add_argument("--fps", type=float, default=8.0, help="Máximo de inferências por segundo")
    parser.add_argument("--confidence", type=float, default=0.55, help="Confiança mínima, entre 0 e 1")
    parser.add_argument("--iou", type=float, default=0.45, help="IoU para supressão de caixas")
    parser.add_argument("--confirmations", type=int, default=2, help="Frames consecutivos para confirmar uma peça")
    parser.add_argument("--max-missed", type=int, default=2, help="Inferências ausentes antes de remover uma peça")
    parser.add_argument(
        "--backend",
        choices=("auto", "dshow", "msmf", "v4l2"),
        default="auto",
        help="Backend da câmera; auto funciona na maioria dos casos",
    )
    parser.add_argument("--no-display", action="store_true", help="Não abre janela; adequado a Pi sem monitor")
    parser.add_argument("--json", action="store_true", help="Emite detecções confirmadas em JSON no terminal")
    return parser.parse_args()


def open_camera(index: int, backend: str) -> cv2.VideoCapture:
    if backend == "dshow":
        return cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if backend == "msmf":
        return cv2.VideoCapture(index, cv2.CAP_MSMF)
    if backend == "v4l2":
        return cv2.VideoCapture(index, cv2.CAP_V4L2)
    if platform.system() == "Windows":
        camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if camera.isOpened():
            return camera
        camera.release()
    return cv2.VideoCapture(index)


def tracks_from_result(result) -> list[Detection]:
    if result.boxes is None:
        return []
    detections: list[Detection] = []
    for box in result.boxes:
        class_id = int(box.cls.item())
        if 0 <= class_id < len(CLASS_NAMES):
            coords = tuple(float(value) for value in box.xyxy[0].tolist())
            detections.append(Detection(class_id, coords, float(box.conf.item())))
    return detections


def draw_tracks(frame, tracks: list[Track], confirmations: int) -> None:
    for track in tracks:
        x1, y1, x2, y2 = (int(value) for value in track.bbox)
        color = COLORS[track.class_id]
        confirmed = track.hits >= confirmations and track.missed == 0
        thickness = 2 if confirmed else 1
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
        state = "" if confirmed else f" ({track.hits}/{confirmations})"
        label = f"{CLASS_NAMES[track.class_id]} {track.confidence:.0%}{state}"
        (label_width, label_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        label_top = max(0, y1 - label_height - baseline - 6)
        cv2.rectangle(frame, (x1, label_top), (x1 + label_width + 6, y1), color, -1)
        cv2.putText(
            frame,
            label,
            (x1 + 3, y1 - baseline - 3),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (15, 15, 15),
            1,
            cv2.LINE_AA,
        )


def confirmed_as_json(tracks: list[Track], confirmations: int) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for track in tracks:
        if track.hits < confirmations or track.missed:
            continue
        x1, y1, x2, y2 = track.bbox
        result.append(
            {
                "class_id": track.class_id,
                "label": CLASS_NAMES[track.class_id],
                "confidence": round(track.confidence, 3),
                "bbox_xyxy": [round(value, 1) for value in track.bbox],
                "center_xy": [round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1)],
                "confirmations": track.hits,
            }
        )
    return result


def main() -> None:
    args = parse_args()
    if not args.model.exists():
        raise SystemExit(f"Modelo não encontrado: {args.model}")
    if args.fps <= 0 or args.confirmations < 1 or args.max_missed < 0:
        raise SystemExit("--fps deve ser positivo, --confirmations >= 1 e --max-missed >= 0")
    if not 0.0 <= args.confidence <= 1.0 or not 0.0 <= args.iou <= 1.0:
        raise SystemExit("--confidence e --iou devem estar entre 0 e 1")

    model = YOLO(str(args.model))
    camera = open_camera(args.camera, args.backend)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not camera.isOpened():
        raise SystemExit(
            f"Não foi possível abrir a câmera {args.camera}. "
            "Tente --camera 1 ou escolha --backend msmf/dshow/v4l2."
        )

    tracker = TemporalFilter(args.confirmations, args.max_missed, args.iou)
    inference_interval = 1.0 / args.fps
    next_inference = 0.0
    inference_times: deque[float] = deque(maxlen=30)

    print("Câmera iniciada. Pressione Q ou Esc na janela para encerrar.")
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("Falha ao ler um frame da câmera")

            now = time.monotonic()
            if now >= next_inference:
                started = time.monotonic()
                result = model.predict(
                    frame,
                    imgsz=args.imgsz,
                    conf=args.confidence,
                    iou=args.iou,
                    verbose=False,
                )[0]
                tracks = tracker.update(tracks_from_result(result))
                elapsed = time.monotonic() - started
                inference_times.append(elapsed)
                next_inference = time.monotonic() + max(0.0, inference_interval - elapsed)

                if args.json:
                    print(
                        json.dumps(
                            {
                                "timestamp_monotonic": round(now, 3),
                                "detections": confirmed_as_json(tracks, args.confirmations),
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )

            if args.no_display:
                # Sem janela, evita ocupar um núcleo inteiro entre duas inferências.
                wait_time = next_inference - time.monotonic()
                if wait_time > 0:
                    time.sleep(min(wait_time, 0.01))
                continue

            preview = frame.copy()
            draw_tracks(preview, tracker.tracks, args.confirmations)
            mean_time = sum(inference_times) / len(inference_times) if inference_times else 0.0
            measured_fps = 1.0 / mean_time if mean_time else 0.0
            status = f"inferência: {measured_fps:.1f} FPS | limite: {args.fps:.1f} FPS | Q: sair"
            cv2.putText(preview, status, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 255, 30), 2, cv2.LINE_AA)
            cv2.imshow("Robotic Rover - detector de pecas", preview)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        camera.release()
        if not args.no_display:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
