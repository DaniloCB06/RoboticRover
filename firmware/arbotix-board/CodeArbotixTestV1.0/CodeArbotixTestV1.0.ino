#include <ax12.h>
#include <stdlib.h>
#include <string.h>


// UART de comunicação com o Arduino Mega
const unsigned long BAUD_MEGA = 57600;

// Registradores DYNAMIXEL protocolo 1.0 (família AX)
const int REG_POSICAO = 36;
const int REG_VELOCIDADE = 38;
const int REG_CARGA = 40;
const int REG_TENSAO = 42;
const int REG_TEMPERATURA = 43;

char buffer[48];
byte indice = 0;

void processarComando(char *linha) {
  char *cmd = strtok(linha, " ");
  if (!cmd) return;

  if (strcmp(cmd, "PING") == 0) {
    Serial.println("PONG");
    return;
  }

  if (strcmp(cmd, "GET") == 0) {
    char *argID = strtok(NULL, " ");
    if (!argID) {
      Serial.println("ERR FORMATO");
      return;
    }

    int id = atoi(argID);

    if (id < 1 || id > 253) {
      Serial.println("ERR ID");
      return;
    }

    int pos = ax12GetRegister(id, REG_POSICAO, 2);

    if (pos < 0) {
      Serial.println("ERR SERVO");
      return;
    }

    int vel = ax12GetRegister(id, REG_VELOCIDADE, 2);
    int carga = ax12GetRegister(id, REG_CARGA, 2);
    int tensao = ax12GetRegister(id, REG_TENSAO, 1);
    int temp = ax12GetRegister(id, REG_TEMPERATURA, 1);

    Serial.print("DATA ");
    Serial.print(id);
    Serial.print(" ");
    Serial.print(pos);
    Serial.print(" ");
    Serial.print(vel);
    Serial.print(" ");
    Serial.print(carga);
    Serial.print(" ");
    Serial.print(tensao);
    Serial.print(" ");
    Serial.println(temp);
    return;
  }

  if (strcmp(cmd, "SET") == 0) {
    char *argID = strtok(NULL, " ");
    char *argPos = strtok(NULL, " ");

    if (!argID || !argPos) {
      Serial.println("ERR FORMATO");
      return;
    }

    int id = atoi(argID);
    int pos = atoi(argPos);

    // Limites iniciais para servos AX em modo de posição.
    if (id < 1 || id > 253 || pos < 0 || pos > 1023) {
      Serial.println("ERR LIMITE");
      return;
    }

    SetPosition(id, pos);

    // Confirma o envio, não a chegada à posição.
    Serial.print("OK SET ");
    Serial.print(id);
    Serial.print(" ");
    Serial.println(pos);
    return;
  }

  Serial.println("ERR COMANDO");
}

void setup() {
  Serial.begin(BAUD_MEGA);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (indice > 0) {
        buffer[indice] = '\0';
        processarComando(buffer);
        indice = 0;
      }
    } else if (indice < sizeof(buffer) - 1) {
      buffer[indice++] = c;
    } else {
      indice = 0;
      Serial.println("ERR BUFFER");
    }
  }
}
