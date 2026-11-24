"""Confirm one selected target with YOLO using fresh snapshots of the Rover camera."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from roboticrover_pi3.camera import MAX_JPEG_BYTES
from roboticrover_pi3.competition import ARTIFACTS, IDENTIFICATION_TOPIC, Arena, epoch_ms, load_competition_env, number
from roboticrover_pi3.competition_rover import tag_id

LABELS = {label: label for label in ARTIFACTS} | {"cilindro_com_base": "cilindro"}


def confirm(snapshot, predict, labels, threshold):
    matches = []
    frames = set()
    for _ in range(9):
        frame_id, image = snapshot()
        if frame_id in frames:
            time.sleep(0.15)
            continue
        frames.add(frame_id)
        options = sorted(predict(image), key=lambda item: item[1], reverse=True)
        if not options or options[0][0] not in labels or options[0][1] < threshold:
            matches.clear()
        else:
            label, confidence = options[0]
            artifact = labels[label]
            if matches and matches[-1][0] != artifact:
                matches.clear()
            if any(conf >= threshold and labels.get(other) != artifact for other, conf in options[1:]):
                matches.clear()
            else:
                matches.append((artifact, confidence))
                if len(matches) == 3:
                    return artifact, min(conf for _, conf in matches)
        time.sleep(0.15)
    raise ValueError("YOLO não confirmou uma classe compatível em 3 quadros distintos do alvo")


def snapshot(url):
    with urlopen(url, timeout=2) as response:
        frame_id = response.headers.get("X-Frame-Id")
        image = response.read(MAX_JPEG_BYTES + 1)
    if not frame_id or len(image) > MAX_JPEG_BYTES or not image.startswith(b"\xff\xd8"):
        raise ValueError("snapshot sem identificação válida")
    return frame_id, image


def write_detection(path, event):
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
            name = Path(handle.name)
            json.dump(event, handle, allow_nan=False)
        name.replace(path)
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def send_detection(arena, event):
    client = arena.client("vision")
    client.connect_timeout = 4
    connected = threading.Event()
    result = []
    acknowledged = threading.Event()
    publish_result = []

    def on_connect(client, userdata, flags, reason, properties):
        result.append(reason)
        connected.set()

    def on_publish(client, userdata, message_id, reason, properties):
        publish_result.append(reason)
        acknowledged.set()

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.connect(arena.host, arena.port, keepalive=5)
    client.loop_start()
    try:
        if not connected.wait(3) or result[0].is_failure:
            raise OSError("Conexão MQTT não confirmada para o detector")
        properties = Properties(PacketTypes.PUBLISH)
        properties.MessageExpiryInterval = 8
        info = client.publish(arena.topic(IDENTIFICATION_TOPIC), json.dumps(event, allow_nan=False),
                              qos=1, retain=False, properties=properties)
        if info.rc != mqtt.MQTT_ERR_SUCCESS or not acknowledged.wait(3) or publish_result[0].is_failure:
            raise OSError("Confirmação MQTT não recebida para a identificação")
        if publish_result[0].value == 16:
            raise OSError("O broker não encontrou um agente da Pi assinando a identificação")
    finally:
        client.disconnect()
        client.loop_stop()


def main():
    load_competition_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--identification", required=True, help="ID estável do alvo nesta rodada, ex. rodada12-tag4")
    parser.add_argument("--tag", type=int)
    parser.add_argument("--snapshot", help="URL da foto; porta 8080 na Pi ou 8081 no Mac")
    parser.add_argument("--via-arena", action="store_true", help="Enviar confirmação da estação à Pi por MQTT")
    parser.add_argument("--model", type=Path, default=Path(__file__).with_name("weights_model.pt"))
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--labels", type=Path, help="JSON com mapeamentos de classes confirmados com o professor")
    parser.add_argument("--output", type=Path, default=Path(os.getenv("COMPETITION_TELEMETRY_DIR", ".runtime/competition")) / "detection.json")
    args = parser.parse_args()
    try:
        threshold = number(args.confidence, 0.01, 1)
        if not 1 <= len(args.identification) <= 80:
            raise ValueError("identification deve ter de 1 a 80 caracteres")
        if args.tag is not None:
            tag_id(args.tag)
        overrides = json.loads(args.labels.read_text(encoding="utf-8")) if args.labels else {}
        if not isinstance(overrides, dict) or any(not isinstance(value, str) or value not in ARTIFACTS
                                                 for value in overrides.values()):
            raise ValueError("O arquivo de classes deve mapear apenas para nomes do contrato")
        labels = LABELS | overrides
        arena = Arena.from_env() if args.via_arena else None
        import cv2
        import numpy as np
        from ultralytics import YOLO

        model = YOLO(str(args.model))

        def predict(jpeg):
            image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("JPEG inválido")
            result = model.predict(image, conf=threshold, verbose=False, device="cpu")[0]
            return [(result.names[int(box.cls.item())], float(box.conf.item())) for box in result.boxes]

        port = 8081 if args.via_arena else 8080
        url = args.snapshot or f"http://127.0.0.1:{port}/snapshot.jpg"
        artifact, conf = confirm(lambda: snapshot(url), predict, labels, threshold)
        event = {"ts": epoch_ms(), "identification": args.identification, "artifact": artifact, "conf": conf}
        if args.tag is not None:
            event["tag"] = args.tag
        if arena:
            send_detection(arena, event)
            print(f"YOLO confirmou {artifact} ({conf:.0%}); enviado à Pi via broker")
        else:
            write_detection(args.output, event)
            print(f"YOLO confirmou {artifact} ({conf:.0%}); evento disponível em {args.output}")
    except ImportError:
        parser.error("Instale o YOLO com pip install -e '.[competition-vision]'")
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
