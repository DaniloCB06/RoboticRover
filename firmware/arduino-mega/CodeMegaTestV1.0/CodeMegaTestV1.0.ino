// ==============================================================================
// Arduino Mega 2560 — Controle da Ponte H L298N (com Watchdog) + Ponte ArbotiX-M
// - USB Serial (115200 baud): recebe "pwmEsq,pwmDir\n" da Raspberry Pi 3 para
//   tração diferencial ou comandos ASCII ("PING", "GET <ID>", "SET <ID> <POS>")
//   encaminhados para a ArbotiX-M.
// - UART1 Serial1 (57600 baud): pinos 18 (TX1) e 19 (RX1) dedicados à ArbotiX-M.
// ==============================================================================

// Pinos da Ponte H L298N (mantendo 18 e 19 livres para Serial1 / ArbotiX-M)
const int ENA = 8;   // PWM Motor Esquerdo
const int IN1 = 4;
const int IN2 = 5;

const int ENB = 9;   // PWM Motor Direito
const int IN3 = 6;
const int IN4 = 7;

const unsigned long TIMEOUT_WATCHDOG_MS = 350;  // Para os motores se perder comunicação
unsigned long ultimoComandoMs = 0;

void acionarMotor(int pinoPwm, int pinoA, int pinoB, int pwm) {
  pwm = constrain(pwm, -255, 255);

  if (pwm > 0) {
    digitalWrite(pinoA, HIGH);
    digitalWrite(pinoB, LOW);
    analogWrite(pinoPwm, pwm);
  } else if (pwm < 0) {
    digitalWrite(pinoA, LOW);
    digitalWrite(pinoB, HIGH);
    analogWrite(pinoPwm, -pwm);
  } else {
    digitalWrite(pinoA, LOW);
    digitalWrite(pinoB, LOW);
    analogWrite(pinoPwm, 0);
  }
}

void pararMotores() {
  acionarMotor(ENA, IN1, IN2, 0);
  acionarMotor(ENB, IN3, IN4, 0);
}

void setup() {
  // USB: PC / Raspberry Pi
  Serial.begin(115200);

  // UART: ArbotiX-M (pinos 18 TX1 e 19 RX1)
  Serial1.begin(57600);

  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  pararMotores();
  ultimoComandoMs = millis();

  Serial.println("MEGA_PRONTO");
}

void loop() {
  // PC / Raspberry Pi -> Mega (L298N ou encaminhamento para ArbotiX-M)
  if (Serial.available() > 0) {
    String linha = Serial.readStringUntil('\n');
    linha.trim();

    int virgula = linha.indexOf(',');
    if (virgula > 0) {
      int pwmEsq = linha.substring(0, virgula).toInt();
      int pwmDir = linha.substring(virgula + 1).toInt();

      acionarMotor(ENA, IN1, IN2, pwmEsq);
      acionarMotor(ENB, IN3, IN4, pwmDir);
      ultimoComandoMs = millis();
    } else if (linha.length() > 0) {
      Serial1.println(linha);
    }
  }

  // ArbotiX-M -> Mega -> PC / Raspberry Pi
  while (Serial1.available()) {
    Serial.write(Serial1.read());
  }

  // Watchdog de segurança (Fail-Safe): se a Pi travar ou desconectar, freia
  if (millis() - ultimoComandoMs > TIMEOUT_WATCHDOG_MS) {
    pararMotores();
  }
}
