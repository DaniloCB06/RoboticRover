"""Fonte artificial de leituras, independente de MQTT e da máquina de estados."""
import random


class SimulatedSensors:
    simulated = True

    def __init__(self, seed=None):
        self.random = random.Random(seed)
        self.battery = 95.0

    def sample(self):
        self.battery = max(0.0, self.battery - 0.002)
        return {
            "battery_percent": round(self.battery, 2),
            "temperature_c": round(self.random.uniform(38, 49), 1),
        }
