# Verificação desta entrega

Ambiente: Windows x64, Python 3.12.10, Docker Desktop 4.99.0, Docker Engine
29.9.3 e Docker Compose 5.7.0. As dependências foram
instaladas em `.venv`; binários e dados temporários ficaram em `.runtime`, que
está no `.gitignore`. Não foram instalados serviços do Windows nem alterados
arquivos da licença. Os processos temporários foram encerrados ao final.

## Testes executados

- Suíte sem infraestrutura: `python -m pytest -q --basetemp .runtime/pytest-sandbox`.
  Resultado atual: **105 aprovados, 7 ignorados**. Os ignorados são os testes de
  integração, que exigem habilitação explícita. O `--basetemp` local evitou uma
  restrição de acesso do ambiente ao diretório temporário padrão do Windows.
- Integração inicial isolada: `RUN_MQTT_INTEGRATION=1`,
  `MQTT_HOST=127.0.0.1`, `MQTT_PORT=18883`,
  `NODE_RED_URL=http://127.0.0.1:18880` e
  `python -m pytest -q -p no:cacheprovider -m integration`.
  Resultado: **7 aprovados**. O cache do pytest foi desabilitado nesta rodada
  devido às permissões diferentes do ambiente de execução com acesso à rede.
- `python -m pip check`: sem dependências incompatíveis.
- `python -m rover --help`, verificação sintática de `settings.js` com Node e
  `git diff --check`: executados sem erros.

A integração isolada usou Mosquitto **2.0.22** oficial extraído do instalador para uma
pasta local, sem executá-lo como instalador, e Node-RED **4.1.1** instalado
localmente pelo npm. O broker utilizou a configuração do repositório, alterando
somente o listener para `127.0.0.1:18883`; o Node-RED carregou os arquivos de
configuração e fluxo fornecidos, com diretório de dados temporário. Depois, o
Compose definitivo foi executado com as imagens `eclipse-mosquitto:2.0.22` e
`nodered/node-red:4.1.1`: os dois serviços ficaram `healthy`, o fluxo
`RoboticRover • SIMULAÇÃO` foi carregado e conectado ao broker. A suíte de
integração foi repetida contra os containers em `127.0.0.1:1883/1880`, com
**7 testes aprovados**.

Foram verificados:

1. Telemetria, estados, logs, alarmes e disponibilidade chegando efetivamente aos
   nós Debug do Node-RED, observados pelo WebSocket administrativo local.
2. Injects do Node-RED publicando os modos na ordem válida, movimento manual
   simulado e parada, com ACKs e estados recebidos por um observador MQTT.
3. Rejeição de JSON malformado, transição proibida e comandos retained, inclusive
   publicação ao vivo e replay ao refazer assinatura.
4. Deduplicação por UUID sem repetir efeitos.
5. Last Will offline após encerramento abrupto do processo.
6. Falha artificial, alarme e bloqueio até reiniciar.
7. Perda do heartbeat da origem esperada, parada e rejeição de novos movimentos.
8. Reconexão automática após o broker substituir a sessão por outra com o mesmo
   client ID; retorno em SEGURO_ESPERA e rejeição do comando retained pendente.
9. Encerramento normal do transporte publicando status offline confirmado.

## Limitações e pendências

Não foram testados hardware, arquitetura ARM da Raspberry Pi, rede Wi-Fi real,
TLS/ACL de implantação, emergência física ou firmware. A desconexão de teste
substituiu uma sessão real no broker e não desligou a rede física. As instruções
de autenticação precisam ser aplicadas e validadas antes do uso em LAN.

Referências utilizadas: [Paho MQTT Python](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[Node-RED no Docker](https://nodered.org/docs/getting-started/docker),
[variáveis no Node-RED](https://nodered.org/docs/user-guide/environment-variables),
[Mosquitto](https://mosquitto.org/man/mosquitto-conf-5.html).
