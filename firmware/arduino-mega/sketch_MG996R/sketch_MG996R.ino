
#include <Arduino.h>
#include <Servo.h>

// ==========================================
// CONFIGURACAO DOS PINOS
// ==========================================

const int MG996_PIN = 12;

// ==========================================
// VARIAVEIS
// ==========================================

Servo mg996;
int anguloMG996 = 90;

// ==========================================
// CONTROLE DO SERVO
// ==========================================

void controlarMG996(int angulo) {

  angulo = constrain(angulo, 0, 180);

  mg996.write(angulo);
  anguloMG996 = angulo;

  Serial.print("MG996R | Angulo: ");
  Serial.println(anguloMG996);
}

// ==========================================
// MONITORAMENTO
// ==========================================

void mostrarStatus() {
  Serial.print("S1 | MG996R: ");
  Serial.print(anguloMG996);
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
    controlarMG996(90);
  }

  else if (comando.startsWith("S1 ")) {

    String valor = comando.substring(3);
    valor.trim();

    // Rejeita comandos sem um angulo valido
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

    controlarMG996(angulo);
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

  mg996.write(90);
  mg996.attach(MG996_PIN);

  Serial.println("Controle MG996R iniciado.");
  Serial.println("Comandos: S1 [0-180], STATUS, CENTER");
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
