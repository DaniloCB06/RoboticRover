
#include <Arduino.h>

// ==========================================
// CONFIGURACAO DOS PINOS
// ==========================================

// Ponte H - Motor NXT 1
const int M1_IN1 = 5;
const int M1_IN2 = 6;

// Ponte H - Motor NXT 2
const int M2_IN1 = 11;  // ALTERADO: D9 -> D11
const int M2_IN2 = 10;

// Encoder - Motor NXT 1
const int ENC1_A = 2;
const int ENC1_B = 4;

// Encoder - Motor NXT 2
const int ENC2_A = 3;
const int ENC2_B = 7;

// ==========================================
// VARIAVEIS DOS MOTORES
// ==========================================

volatile long posicaoM1 = 0;
volatile long posicaoM2 = 0;

int velocidadeM1 = 0;
int velocidadeM2 = 0;

// ==========================================
// CONTROLE DOS MOTORES
// ==========================================

// Velocidade: -255 ate +255
void controlarMotor(int motor, int velocidade) {

  velocidade = constrain(velocidade, -255, 255);

  int in1, in2;

  if (motor == 1) {
    in1 = M1_IN1;
    in2 = M1_IN2;
    velocidadeM1 = velocidade;
  }
  else if (motor == 2) {
    in1 = M2_IN1;
    in2 = M2_IN2;
    velocidadeM2 = velocidade;
  }
  else {
    return;
  }

  if (velocidade > 0) {
    analogWrite(in1, velocidade);
    digitalWrite(in2, LOW);
  }
  else if (velocidade < 0) {
    digitalWrite(in1, LOW);
    analogWrite(in2, -velocidade);
  }
  else {
    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);
  }
}

// Parar ambos os motores
void pararMotores() {
  controlarMotor(1, 0);
  controlarMotor(2, 0);
}

// ==========================================
// LEITURA DOS ENCODERS
// ==========================================

void encoderMotor1() {
  bool a = digitalRead(ENC1_A);
  bool b = digitalRead(ENC1_B);

  if (a == b) {
    posicaoM1++;
  } else {
    posicaoM1--;
  }
}

void encoderMotor2() {
  bool a = digitalRead(ENC2_A);
  bool b = digitalRead(ENC2_B);

  if (a == b) {
    posicaoM2++;
  } else {
    posicaoM2--;
  }
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

  Serial.print("M1 PWM: ");
  Serial.print(velocidadeM1);

  Serial.print(" | Encoder 1: ");
  Serial.print(p1);

  Serial.print(" | M2 PWM: ");
  Serial.print(velocidadeM2);

  Serial.print(" | Encoder 2: ");
  Serial.println(p2);
}

// ==========================================
// COMANDOS VIA SERIAL
// ==========================================

void processarComando(String comando) {

  comando.trim();
  comando.toUpperCase();

  if (comando == "STOP") {
    pararMotores();
    Serial.println("Motores parados.");
  }

  else if (comando == "STATUS") {
    mostrarStatus();
  }

  else if (comando == "ZERO") {
    noInterrupts();
    posicaoM1 = 0;
    posicaoM2 = 0;
    interrupts();

    Serial.println("Encoders zerados.");
  }

  else if (comando.startsWith("M1 ")) {
    int valor = comando.substring(3).toInt();
    controlarMotor(1, valor);
    mostrarStatus();
  }

  else if (comando.startsWith("M2 ")) {
    int valor = comando.substring(3).toInt();
    controlarMotor(2, valor);
    mostrarStatus();
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

  Serial.println("Controle NXT iniciado.");
  Serial.println("Comandos: M1, M2, STOP, STATUS, ZERO");
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
