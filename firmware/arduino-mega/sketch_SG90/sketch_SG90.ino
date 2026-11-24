
#include <Arduino.h>
#include <Servo.h>

// ==========================================
// CONFIGURACAO DOS PINOS
// ==========================================

const int SG90_PIN = 8;

// ==========================================
// VARIAVEIS
// ==========================================

Servo sg90;
int anguloSG90 = 90;

// ==========================================
// CONTROLE DO SERVO
// ==========================================

void controlarSG90(int angulo) {

  angulo = constrain(angulo, 0, 180);

  sg90.write(angulo);
  anguloSG90 = angulo;

  Serial.print("SG90 | Angulo: ");
  Serial.println(anguloSG90);
}

// ==========================================
// MONITORAMENTO
// ==========================================

void mostrarStatus() {

  Serial.print("S2 | SG90: ");
  Serial.print(anguloSG90);
  Serial.println(" graus (solicitado)");
}

// ==========================================
// COMANDOS VIA SERIAL
// ==========================================

void processarComando(String comando) {

  comando.trim();
  comando.toUpperCase();

  if (comando == "STATUS") {
    mostrarStatus();
  }

  else if (comando == "CENTER") {
    controlarSG90(90);
  }

  else if (comando.startsWith("S2 ")) {

    String valor = comando.substring(3);
    valor.trim();

    if (valor.length() == 0) {
      Serial.println("Informe um angulo.");
      return;
    }

    for (unsigned int i = 0; i < valor.length(); i++) {
      if (!isDigit(valor[i])) {
        Serial.println("Angulo invalido.");
        return;
      }
    }

    int angulo = valor.toInt();

    if (angulo < 0 || angulo > 180) {
      Serial.println("Angulo deve estar entre 0 e 180.");
      return;
    }

    controlarSG90(angulo);
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

  sg90.write(90);
  sg90.attach(SG90_PIN);

  Serial.println("Controle SG90 iniciado.");
  Serial.println("Comandos: S2 [0-180], STATUS, CENTER");
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
