# Passagem do desenvolvimento local para rede real

O Compose desta entrega permite clientes anônimos e editor sem senha apenas em
loopback. O listener 0.0.0.0 no container permite a rede interna Docker; a porta
publicada no host é 127.0.0.1. Não exponha essas configurações à Internet ou Wi-Fi
compartilhado. Outros processos locais e containers na mesma rede ainda podem
acessar o broker. Aplique as etapas abaixo antes do uso físico.

1. Copie `infra/mqtt/mosquitto.conf` para uma configuração de implantação.
   Troque `allow_anonymous true` por `allow_anonymous false` e adicione
   `password_file /mosquitto/config/passwords` e
   `acl_file /mosquitto/config/acl`. Monte esses arquivos como somente leitura.
2. Gere usuários com `mosquitto_passwd -c /caminho/passwords rover` e depois
   `mosquitto_passwd /caminho/passwords station`. Execute interativamente numa
   instalação local ou container com volume apropriado; `-c` é só para a primeira
   criação, pois substitui um arquivo existente. Não versione senhas ou hashes.
3. Crie ACL para limitar o que cada identidade pode publicar e assinar:

```text
user rover
topic write rover/estado
topic write rover/telemetria
topic write rover/alarme
topic write rover/log
topic write rover/status
topic write rover/cmd/ack
topic read rover/cmd/modo
topic read rover/cmd/manual
topic read station/heartbeat

user station
topic read rover/#
topic write rover/cmd/modo
topic write rover/cmd/manual
topic write station/heartbeat
```

4. Configure TLS no broker: listener 8883, `certfile`, `keyfile` e a cadeia
   correspondente. Monte certificados/chave sem versioná-los, restrinja permissões
   e use certificado cujo SAN contenha o DNS/IP utilizado. Publique apenas a
   interface da LAN necessária, restrinja o firewall à estação e à Pi e remova o
   listener anônimo. Credenciais sem TLS podem ser interceptadas.
5. No Python, ajuste `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`
   e `MQTT_CA_FILE`. O cliente usa validação TLS padrão de certificado/hostname;
   não desabilite essa verificação. No broker do fluxo Node-RED, configure
   usuário/senha na aba Security e TLS com a CA correta. O `.env` do simulador
   não configura automaticamente as credenciais do Node-RED.
6. Adapte o healthcheck do Compose à nova autenticação/TLS; o atual publica
   anonimamente em `healthcheck`, exclusivamente para desenvolvimento. Configure
   `adminAuth` no Node-RED (hash gerado por `node-red admin hash-pw`), um
   `credentialSecret` próprio e HTTPS ou acesso local por túnel. Faça Deploy e
   exporte o fluxo sem segredos.
7. Verifique versões e atualizações de segurança das imagens antes de implantar.
   As tags desta entrega fixam uma base reproduzível para testes locais; não
   representam uma configuração de produção pronta.

Uma configuração TLS/ACL real precisa ser validada com os certificados e a rede
do projeto. Não há integração fictícia com endpoints do professor.

## Limite da parada remota

MQTT depende do broker, Wi-Fi, SO e aplicação. **Não é parada de emergência
física.** A implementação no Arduino deverá ter watchdog independente, desligar
motores em ausência de comandos válidos periódicos, iniciar sempre desabilitada
e exigir rearme explícito após falha. A interface serial e a frequência desse
watchdog serão definidas junto ao firmware; não há controle de GPIO/serial nesta
entrega. A disponibilidade MQTT não confirma o estado físico dos motores.

Referências: [configuração Mosquitto](https://mosquitto.org/man/mosquitto-conf-5.html),
[segurança Node-RED](https://nodered.org/docs/user-guide/runtime/securing-node-red),
[Paho MQTT Python](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
