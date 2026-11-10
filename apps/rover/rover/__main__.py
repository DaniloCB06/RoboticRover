import argparse
import logging
import math
import os
import signal
import threading
import time

from .config import Config
from .mqtt_client import RoverMQTT
from .simulator import SimulatedSensors


def main():
    parser = argparse.ArgumentParser(description="Rover MQTT: somente simulação, nenhum hardware")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--fault-after", type=float, help="Injeta falha artificial após N segundos")
    parser.add_argument("--crash-after", type=float, help="Encerra abruptamente para testar Last Will")
    args = parser.parse_args()
    for value in (args.fault_after, args.crash_after):
        if value is not None and (not math.isfinite(value) or value <= 0):
            parser.error("Tempos de falha devem ser positivos e finitos")
    try:
        config = Config.from_env(args.env_file)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    sensors = SimulatedSensors(args.seed)
    transport = RoverMQTT(config)
    started = time.monotonic()
    next_sample = started
    fault_sent = False
    logging.info("SIMULAÇÃO: dados artificiais; nenhum atuador físico conectado")
    transport.start()
    try:
        while not stop.wait(0.05):
            now = time.monotonic()
            if args.crash_after is not None and now - started >= args.crash_after:
                logging.error("Queda abrupta SIMULADA para testar Last Will")
                os._exit(2)
            with transport.lock:
                transport.controller.tick()
                if args.fault_after is not None and not fault_sent and now - started >= args.fault_after:
                    transport.controller.fault()
                    fault_sent = True
                if now >= next_sample:
                    transport.emit("rover/telemetria", sensors.sample())
                    next_sample = now + config.telemetry_interval
    finally:
        transport.stop()


if __name__ == "__main__":
    main()
