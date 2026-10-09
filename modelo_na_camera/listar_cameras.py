"""Lista índices de câmeras que o OpenCV consegue abrir no computador.

Útil para webcams USB e câmeras virtuais, como DroidCam. Execute antes do
main.py quando não souber o valor a usar em --camera.
"""

from __future__ import annotations

import argparse
import platform

import cv2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-index", type=int, default=10, help="Maior índice a testar")
    parser.add_argument(
        "--backend",
        choices=("auto", "dshow", "msmf", "v4l2"),
        default="dshow" if platform.system() == "Windows" else "v4l2",
        help="No Windows, dshow costuma encontrar melhor câmeras virtuais",
    )
    return parser.parse_args()


def backend_id(name: str) -> int | None:
    return {
        "dshow": cv2.CAP_DSHOW,
        "msmf": cv2.CAP_MSMF,
        "v4l2": cv2.CAP_V4L2,
    }.get(name)


def open_camera(index: int, backend: str) -> cv2.VideoCapture:
    backend_value = backend_id(backend)
    return cv2.VideoCapture(index) if backend_value is None else cv2.VideoCapture(index, backend_value)


def main() -> None:
    args = parse_args()
    if args.max_index < 0:
        raise SystemExit("--max-index deve ser maior ou igual a zero")

    print(f"Testando índices de 0 a {args.max_index} com backend {args.backend}...")
    found = 0
    for index in range(args.max_index + 1):
        camera = open_camera(index, args.backend)
        try:
            if not camera.isOpened():
                continue
            ok, frame = camera.read()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            print(f"[OK] --camera {index}: frame {width}x{height}")
            found += 1
        finally:
            camera.release()

    if not found:
        print("Nenhuma câmera forneceu imagem.")
        print("No Windows, tente novamente com: --backend msmf")
        print("Confirme também que o DroidCam Client está iniciado e que nenhum outro programa usa a câmera.")
    else:
        print("Use um índice marcado como [OK] no comando principal.")


if __name__ == "__main__":
    main()
