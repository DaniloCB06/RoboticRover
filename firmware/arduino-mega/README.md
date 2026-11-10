# Futuro firmware Arduino Mega 2560

Não há firmware executável nesta etapa. A Raspberry Pi fará a ponte entre MQTT
e o microcontrolador por uma interface a definir. Motores e servos devem iniciar
desabilitados. O firmware deverá implementar watchdog independente da Pi,
interromper motores ao expirar o prazo local de comandos válidos e exigir rearme
após falha. A parada física de emergência independe de MQTT.

Antes da implementação, definir protocolo serial, confirmação de comandos,
limites dos atuadores, frequência do watchdog e testes de perda da Pi. O simulador
atual não abre porta serial nem escreve GPIO.
