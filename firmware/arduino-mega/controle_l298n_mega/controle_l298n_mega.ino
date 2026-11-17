// ==============================================================================
// Controle simples da Ponte H L298N no Arduino Mega 2560
// Recebe comandos da Raspberry Pi 3 via USB Serial no formato: "pwmEsq,pwmDir\n"
// Exemplos: "160,160" (frente), "-120,120" (gira), "0,0" (para)
// OBS: Os pinos 18 (TX1) e 19 (RX1) ficam livres para a ArbotiX-M / AX-12A.
// ==============================================================================

// Pinos da Ponte H L298N (ajuste se sua fiação estiver em outros pinos)
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
  Serial.begin(115200);

  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  pararMotores();
  ultimoComandoMs = millis();
}

void loop() {
  // Lê comandos vindos da Raspberry Pi 3 pela USB Serial
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
    }
  }

  // Watchdog de segurança (Fail-Safe): se a Pi travar ou desconectar, freia
  if (millis() - ultimoComandoMs > TIMEOUT_WATCHDOG_MS) {
    pararMotores();
  }
}
