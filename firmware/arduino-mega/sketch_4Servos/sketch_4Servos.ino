
#include <Arduino.h>
#include <Servo.h>

// ==========================================
// CONFIGURACAO DOS PINOS
// ==========================================

// Ponte H - NXT 1
const int M1_IN1 = 5;
const int M1_IN2 = 6;

// Ponte H - NXT 2
const int M2_IN1 = 11;
const int M2_IN2 = 10;

// Encoders NXT
const int ENC1_A = 2;
const int ENC1_B = 4;

const int ENC2_A = 3;
const int ENC2_B = 7;

// Servomotores
const int MG996_PIN = 12;
const int SG90_PIN  = 8;

// ==========================================
// VARIAVEIS
// ==========================================

// Encoders
volatile long posicaoM1 = 0;
volatile long posicaoM2 = 0;

// Velocidades comandadas
int velocidadeM1 = 0;
int velocidadeM2 = 0;

// Servos
Servo mg996;
Servo sg90;

int anguloMG996 = 90;
int anguloSG90  = 90;

// ==========================================
// CONTROLE DOS MOTORES NXT
// ==========================================

void controlarMotor(int motor, int velocidade) {

  velocidade = constrain(velocidade, -255, 255);

  if (motor == 1) {

    velocidadeM1 = velocidade;

    if (velocidade > 0) {
      digitalWrite(M1_IN2, LOW);
      analogWrite(M1_IN1, velocidade);
    }
    else if (velocidade < 0) {
      digitalWrite(M1_IN1, LOW);
      analogWrite(M1_IN2, -velocidade);
    }
    else {
      digitalWrite(M1_IN1, LOW);
      digitalWrite(M1_IN2, LOW);
    }
  }

  else if (motor == 2) {

    velocidadeM2 = velocidade;

    if (velocidade > 0) {
      digitalWrite(M2_IN2, LOW);
      analogWrite(M2_IN1, velocidade);
    }
    else if (velocidade < 0) {
      // PWM invertido para permitir reversao
      // usando apenas o pino PWM D11.
      digitalWrite(M2_IN2, HIGH);
      analogWrite(M2_IN1, 255 + velocidade);
    }
    else {
      digitalWrite(M2_IN1, LOW);
      digitalWrite(M2_IN2, LOW);
    }
  }
}

void pararMotores() {
  controlarMotor(1, 0);
  controlarMotor(2, 0);
}

// ==========================================
// CONTROLE DOS SERVOS
// ==========================================

void controlarMG996(int angulo) {

  angulo = constrain(angulo, 0, 180);

  mg996.write(angulo);
  anguloMG996 = angulo;

  Serial.print("S1 | MG996R: ");
  Serial.print(anguloMG996);
  Serial.println(" graus");
}

void controlarSG90(int angulo) {

  angulo = constrain(angulo, 0, 180);

  sg90.write(angulo);
  anguloSG90 = angulo;

  Serial.print("S2 | SG90: ");
  Serial.print(anguloSG90);
  Serial.println(" graus");
}

// ==========================================
// LEITURA DOS ENCODERS
// ==========================================

void encoderMotor1() {

  bool a = digitalRead(ENC1_A);
  bool b = digitalRead(ENC1_B);

  if (a == b)
    posicaoM1++;
  else
    posicaoM1--;
}

void encoderMotor2() {

  bool a = digitalRead(ENC2_A);
  bool b = digitalRead(ENC2_B);

  if (a == b)
    posicaoM2++;
  else
    posicaoM2--;
}

// ==========================================
// MONITORAMENTO
// ==========================================

void mostrarStatus() {

  long p1, p2;

  noInterrupts();
  p1 = posicaoM1;
  p2 = posicaoM2;
  interrupts();

  Serial.println("========== STATUS ==========");

  Serial.print("M1 | PWM: ");
  Serial.print(velocidadeM1);
  Serial.print(" | Encoder: ");
  Serial.println(p1);

  Serial.print("M2 | PWM: ");
  Serial.print(velocidadeM2);
  Serial.print(" | Encoder: ");
  Serial.println(p2);

  Serial.print("S1 | MG996R: ");
  Serial.print(anguloMG996);
  Serial.println(" graus");

  Serial.print("S2 | SG90: ");
  Serial.print(anguloSG90);
  Serial.println(" graus");

  Serial.println("============================");
}

// ==========================================
// PROCESSAMENTO DOS COMANDOS
// ==========================================

void processarComando(String comando) {

  comando.trim();
  comando.toUpperCase();

  // Comandos gerais
  if (comando == "STOP") {
    pararMotores();
    Serial.println("Motores NXT parados.");
    return;
  }

  if (comando == "STATUS") {
    mostrarStatus();
    return;
  }

  if (comando == "ZERO") {
    noInterrupts();
    posicaoM1 = 0;
    posicaoM2 = 0;
    interrupts();

    Serial.println("Encoders zerados.");
    return;
  }

  if (comando == "CENTER") {
    controlarMG996(90);
    controlarSG90(90);
    return;
  }

  // Comandos individuais
  if (comando.length() < 4 || comando[2] != ' ') {
    Serial.println("Comando invalido.");
    return;
  }

  String tipo = comando.substring(0, 2);
  String valorTexto = comando.substring(3);
  valorTexto.trim();

  if (valorTexto.length() == 0) {
    Serial.println("Valor nao informado.");
    return;
  }

  // Validacao do numero
  int inicio = 0;

  if (valorTexto[0] == '-') {
    inicio = 1;
  }

  if (inicio == (int)valorTexto.length()) {
    Serial.println("Valor invalido.");
    return;
  }

  for (unsigned int i = inicio; i < valorTexto.length(); i++) {
    if (!isDigit(valorTexto[i])) {
      Serial.println("Valor invalido.");
      return;
    }
  }

  long valorLong = valorTexto.toInt();

  // NXT
  if (tipo == "M1" || tipo == "M2") {

    if (valorLong < -255 || valorLong > 255) {
      Serial.println("PWM deve estar entre -255 e 255.");
      return;
    }

    int motor = (tipo == "M1") ? 1 : 2;

    controlarMotor(motor, (int)valorLong);
    mostrarStatus();
  }

  // Servos
  else if (tipo == "S1" || tipo == "S2") {

    if (valorLong < 0 || valorLong > 180) {
      Serial.println("Angulo deve estar entre 0 e 180.");
      return;
    }

    if (tipo == "S1")
      controlarMG996((int)valorLong);
    else
      controlarSG90((int)valorLong);
  }

  else {
    Serial.println("Comando invalido.");
  }
}

// ==========================================
// SETUP
// ==========================================

void setup() {

  Serial.begin(115200);
  Serial.setTimeout(30);

  // Ponte H
  pinMode(M1_IN1, OUTPUT);
  pinMode(M1_IN2, OUTPUT);

  pinMode(M2_IN1, OUTPUT);
  pinMode(M2_IN2, OUTPUT);

  pararMotores();

  // Encoders
  pinMode(ENC1_A, INPUT);
  pinMode(ENC1_B, INPUT);

  pinMode(ENC2_A, INPUT);
  pinMode(ENC2_B, INPUT);

  attachInterrupt(
    digitalPinToInterrupt(ENC1_A),
    encoderMotor1,
    CHANGE
  );

  attachInterrupt(
    digitalPinToInterrupt(ENC2_A),
    encoderMotor2,
    CHANGE
  );

  // MG996R
  mg996.write(90);
  mg996.attach(MG996_PIN);

  // SG90
  sg90.write(90);
  sg90.attach(SG90_PIN);

  // Inicializacao
  Serial.println();
  Serial.println("Sistema de controle iniciado!");
  Serial.println();
  Serial.println("M1 [PWM]  - NXT 1");
  Serial.println("M2 [PWM]  - NXT 2");
  Serial.println("S1 [ANG]  - MG996R");
  Serial.println("S2 [ANG]  - SG90");
  Serial.println();
  Serial.println("STOP   - Para os NXT");
  Serial.println("ZERO   - Zera os encoders");
  Serial.println("CENTER - Centraliza os servos");
  Serial.println("STATUS - Exibe informacoes");
}

// ==========================================
// LOOP
// ==========================================

void loop() {

  if (Serial.available()) {

    String comando = Serial.readStringUntil('\n');
    processarComando(comando);
  }
}
