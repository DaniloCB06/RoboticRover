"""Executa detecção por webcam e publica somente detecções temporalmente estáveis.

As linhas emitidas no stdout são JSON, adequadas para integração com o controle do rover.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
import sys

import cv2
from ultralytics import YOLO

# Permite executar este arquivo diretamente com `python scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision.classes import CLASS_NAMES


@dataclass
class Track:
    class_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    hits: int = 1
    missed: int = 0


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0.0


class TemporalFilter:
    def __init__(self, confirmations: int, max_missed: int, match_iou: float = 0.30) -> None:
        self.confirmations = confirmations
        self.max_missed = max_missed
        self.match_iou = match_iou
        self.tracks: list[Track] = []

    def update(self, detections: list[Track]) -> list[Track]:
        available = set(range(len(self.tracks)))
        for detection in detections:
            candidates = [
                index
                for index in available
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
                available.remove(index)
            else:
                self.tracks.append(detection)
        for index in available:
            self.tracks[index].missed += 1
        self.tracks = [track for track in self.tracks if track.missed <= self.max_missed]
        return [track for track in self.tracks if track.hits >= self.confirmations and track.missed == 0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True, help="Pasta *_ncnn_model exportada")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--fps", type=float, default=8.0, help="Teto de inferências por segundo")
    parser.add_argument("--confidence", type=float, default=0.55)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--confirmations", type=int, default=3)
    parser.add_argument("--max-missed", type=int, default=2)
    parser.add_argument("--display", action="store_true", help="Exibe janela de depuração")
    return parser.parse_args()


def as_json(track: Track) -> dict[str, object]:
    x1, y1, x2, y2 = track.bbox
    return {
        "class_id": track.class_id,
        "label": CLASS_NAMES[track.class_id],
        "confidence": round(track.confidence, 3),
        "bbox_xyxy": [round(value, 1) for value in track.bbox],
        "center_xy": [round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1)],
        "confirmations": track.hits,
    }


def main() -> None:
    args = parse_args()
    if args.fps <= 0:
        raise SystemExit("--fps deve ser maior que zero")
    if not args.model.exists():
        raise SystemExit(f"Modelo NCNN não encontrado: {args.model}")
    model = YOLO(str(args.model))
    camera = cv2.VideoCapture(args.camera)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not camera.isOpened():
        raise SystemExit(f"Não foi possível abrir a câmera {args.camera}")

    filter_ = TemporalFilter(args.confirmations, args.max_missed)
    interval = 1.0 / args.fps
    next_inference = 0.0
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("Falha ao capturar frame da câmera")
            now = time.monotonic()
            if now < next_inference:
                if args.display and cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue
            next_inference = now + interval
            result = model.predict(frame, imgsz=args.imgsz, conf=args.confidence, iou=args.iou, verbose=False)[0]
            detections: list[Track] = []
            if result.boxes is not None:
                for box in result.boxes:
                    class_id = int(box.cls.item())
                    coords = tuple(float(value) for value in box.xyxy[0].tolist())
                    detections.append(Track(class_id, coords, float(box.conf.item())))
            stable = filter_.update(detections)
            message = {
                "timestamp_monotonic": round(now, 3),
                "detections": [as_json(track) for track in stable],
            }
            print(json.dumps(message, ensure_ascii=False), flush=True)

            if args.display:
                debug = result.plot()
                for track in stable:
                    x1, y1, x2, y2 = (int(value) for value in track.bbox)
                    cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imshow("Robotic Rover - deteccao", debug)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        if args.display:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
