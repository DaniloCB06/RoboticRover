
void setup() {
  // USB: PC / Raspberry Pi
  Serial.begin(115200);

  // UART: ArbotiX-M
  Serial1.begin(57600);

  Serial.println("MEGA_PRONTO");
}

void loop() {
  // PC -> Mega -> ArbotiX-M
  while (Serial.available()) {
    Serial1.write(Serial.read());
  }

  // ArbotiX-M -> Mega -> PC
  while (Serial1.available()) {
    Serial.write(Serial1.read());
  }
}
