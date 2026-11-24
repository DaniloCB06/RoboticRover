# Iniciar toda a comunicação

Na raiz do projeto no Mac:

```bash
.venv/bin/python inicia_comunicacao.py
```

O menu solicita:

```text
1 = servidor do professor não é alcançável (comunicação local)
2 = servidor do professor é alcançável (modo competição)
```

O modo 2 depende somente de acesso ao MQTT e ao WHIP do professor pela rede local. O professor pode estar sem internet. Se o Wi-Fi dele estiver desligado e não houver outro caminho pela rede (por exemplo, Ethernet), use o modo 1. O programa não consulta sites externos, não baixa pacotes e não troca o Wi-Fi de nenhuma máquina.

Por padrão, o script conecta a `puc@puc.local`, solicita a senha SSH no próprio terminal e obtém o IP do Mac pela conexão. Não é necessário preparar uma sessão SSH compartilhada. Para informar o endereço atual da Pi:

```bash
.venv/bin/python inicia_comunicacao.py --pi puc@192.168.1.113
```

Se o usuário ou caminho do projeto na Pi forem diferentes, use `--pi usuario@IP` e `--pi-dir /caminho/absoluto/RoboticRover`. `--mac-ip` permite informar o IPv4 do Mac quando necessário.

Por padrão, o iniciador força `MOTOR_BACKEND=simulation` na Pi, mesmo que o `.env` remoto contenha uma opção física antiga. Para o teste futuro com o Mega preparado, use `--motor-backend serial --serial-port /dev/serial/by-id/IDENTIFICADOR_REAL` e, opcionalmente, `--motor-pwm 80`, `--invert-left` ou `--invert-right`. Isso vale nos modos 1 e 2. A instalação do extra `motor-control`, a escolha do firmware/pinagem e o roteiro estão em [CONTROLE_MANUAL_MOTORES.md](CONTROLE_MANUAL_MOTORES.md).

## Processos iniciados

| Processo | Modo 1 | Modo 2 |
| --- | --- | --- |
| Mosquitto local, porta 1883 | Sim | Sim |
| Node-RED/dashboard, porta 1880 | Sim | Sim |
| MediaMTX, WHIP/WHEP 8890 e mídia 8190/UDP | Vídeo local | Vídeo local e forwarding ao professor |
| Ponte MQTT da estação | Não | Sim |
| Cliente do Rover na Pi | `roboticrover_pi3`, broker no Mac por túnel SSH reverso 18883 | `competition_rover`, broker do professor |
| Webcam da Pi | H.264 local a 15 FPS + snapshot a 1 FPS | Mesmo formato |
| Publicador `aiortc` na Pi | WHIP para o Mac | WHIP para o Mac |

A dashboard recebe WHEP local nos dois modos. Abra `http://127.0.0.1:1880/dashboard` ou o player `http://127.0.0.1:8890/rover/rover04`. Se existir uma URL antiga salva na dashboard, escolha WebRTC/WHEP na engrenagem e informe `http://127.0.0.1:8890/rover/rover04/whep`.

## Encerramento e recuperação

Mantenha o terminal do script aberto. **Ctrl+C**, SIGTERM e SIGHUP iniciam o encerramento: o supervisor da Pi recebe a parada, encerra os processos de Rover, webcam/FFmpeg e publicador, e confirma o resultado; depois o script fecha os grupos de processos locais e a sessão SSH que criou. Processos que não respondem ao encerramento normal são finalizados após o prazo de espera. Não são abertas janelas adicionais do Terminal.

O supervisor da Pi recebe uma renovação a cada segundo. Se a estação parar de renová-la por mais de 10 segundos, ele encerra os serviços que iniciou, inclusive quando a conexão de rede fica interrompida. Uma falha em qualquer serviço também encerra os demais serviços daquela execução. Se a rede cair durante a parada, o Mac informa quando não recebeu a confirmação da Pi; confira os processos na placa depois de reconectar. Isso não substitui o watchdog físico dos motores.

O iniciador recusa portas ocupadas no Mac e processos do Rover já ativos na Pi, em vez de fechar serviços de outra execução. Pare as execuções manuais anteriores primeiro. Ele mantém uma trava local e uma trava na Pi para evitar duas instâncias simultâneas.

Os logs ficam em `.runtime/comunicacao-DATA-HORA-PID-NOME.log` no Mac e na Pi. Em uma falha, o terminal mostra o caminho correspondente.

## Preparação necessária

O Mac deve ter `.venv`, Mosquitto em `.venv/bin/mosquitto`, `node-red` no PATH e MediaMTX v1.21.4 em `.runtime/mediamtx-v1.21.4/mediamtx`. A Pi deve conter o projeto atualizado em `/home/puc/RoboticRover`, o ambiente `apps/rover/.venv` com `aiortc`, `av`, `paho-mqtt` e `python-dotenv`, o FFmpeg e a webcam USB no caminho configurado pelo projeto. Esses itens já foram preparados nesta instalação.

Para o modo 2, configure `COMPETITION_HOST`, `COMPETITION_TEAM`, `COMPETITION_PASSWORD` e `COMPETITION_MQTT_PORT` no `.env` da raiz do Mac. O iniciador passa os mesmos valores aos processos da Pi para evitar configurações diferentes. No modo 1, se não existir credencial, ele cria uma credencial temporária somente para o vídeo local.

## Conferir sem iniciar os processos

```bash
.venv/bin/python inicia_comunicacao.py --mode 1 --dry-run --mac-ip 192.168.1.36
.venv/bin/python inicia_comunicacao.py --mode 2 --dry-run --mac-ip 192.168.50.130
.venv/bin/python -m pytest -q tests/test_inicia_comunicacao.py
```

`--mode` pula o menu; `--dry-run` imprime os comandos sem conectar à Pi nem iniciar os serviços. Os testes verificam os dois planos, parada dos filhos, falha de um serviço, perda de entrada SSH, expiração da renovação e preservação de processos que não pertencem ao iniciador.
