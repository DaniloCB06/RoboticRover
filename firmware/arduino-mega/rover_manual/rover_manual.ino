// Firmware exclusivo de bancada para Mega 2560. Não usar os sketches legados
// pwmEsq,pwmDir ou M1/M2 com o cliente RR1: o handshake deve rejeitá-los.
#include "rover_protocol.h"
#if defined(ARDUINO) && !defined(__AVR_ATmega2560__)
#error Este firmware requer Arduino Mega 2560
#endif

// 1 = DRV8833 (IN1 D5, IN2 D6, IN3 D11, IN4 D10).
// 2 = L298N (ENA D8, IN1 D4, IN2 D5, ENB D9, IN3 D6, IN4 D7).
// CONFIRMAR o módulo e a fiação antes de escolher e gravar no Mega.
#ifndef ROVER_DRIVER
#define ROVER_DRIVER 1
#endif
#if ROVER_DRIVER != 1 && ROVER_DRIVER != 2
#error Driver invalido
#endif

rover::Controller controller;
char input[rover::MAX_FRAME];
uint8_t length = 0;
bool dropping = false;
uint32_t inputStarted = 0;

void motor(uint8_t a, uint8_t b, uint8_t enable, int pwm) {
  // Sempre zera as duas entradas antes de alterar o sentido.
  analogWrite(a, 0); analogWrite(b, 0);
#if ROVER_DRIVER == 1
  (void)enable;
  if (pwm > 0) analogWrite(a, pwm);
  else if (pwm < 0) analogWrite(b, -pwm);
#else
  analogWrite(enable, 0);
  digitalWrite(a, pwm > 0 ? HIGH : LOW);
  digitalWrite(b, pwm < 0 ? HIGH : LOW);
  analogWrite(enable, pwm < 0 ? -pwm : pwm);
#endif
}

void applyOutputs() {
#if ROVER_DRIVER == 1
  motor(5, 6, 0, controller.left); motor(11, 10, 0, controller.right);
#else
  motor(4, 5, 8, controller.left); motor(6, 7, 9, controller.right);
#endif
}

void setup() {
#if ROVER_DRIVER == 1
  const uint8_t pins[] = {5, 6, 11, 10};
#else
  const uint8_t pins[] = {8, 4, 5, 9, 6, 7};
#endif
  for (uint8_t i = 0; i < sizeof(pins); ++i) { digitalWrite(pins[i], LOW); pinMode(pins[i], OUTPUT); }
  controller.stop(); applyOutputs();
  Serial.begin(115200);
}

void loop() {
  uint32_t now = millis();
  if (controller.tick(now)) applyOutputs();
  if (length && (uint32_t)(now - inputStarted) >= 100) {
    length = 0; dropping = true; controller.stop(); applyOutputs();
  }
  // Limita trabalho por iteração: ruído contínuo não pode impedir o watchdog.
  for (uint8_t budget = 0; budget < 64 && Serial.available(); ++budget) {
    char value = Serial.read();
    if (value == '\n') {
      if (!dropping && length) {
        input[length] = 0;
        rover::Frame frame;
        if (rover::decode(input, frame)) {
          rover::Frame reply = controller.process(frame, millis());
          applyOutputs();
          char output[rover::MAX_FRAME]; rover::encode(output, reply); Serial.print(output);
        } else { controller.stop(); applyOutputs(); }
      }
      length = 0; dropping = false;
    } else if (!dropping) {
      if (length == rover::MAX_FRAME - 1 || value < 32 || value > 126) {
        length = 0; dropping = true; controller.stop(); applyOutputs();
      } else {
        if (!length) inputStarted = millis();
        input[length++] = value;
      }
    }
  }
}
