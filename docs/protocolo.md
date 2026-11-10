# Protocolo v1 e estados

Cada mensagem possui `version`, `timestamp`, `source`, `simulated`, `type` e
`data`. Campos extras são rejeitados. O schema é validado em todas as entradas e
saídas Python; o Node-RED interpreta JSON e verifica envelope/tópico antes de
encaminhar aos Debug. A decisão final de comando pertence ao controlador Python.

## Máquina de estados

| Estado atual | Próximo modo permitido, além de espera e do próprio estado |
| --- | --- |
| SEGURO_ESPERA | BUSCA |
| BUSCA | APROXIMACAO |
| APROXIMACAO | AGUARDANDO_PEGA |
| AGUARDANDO_PEGA | CAPTURA_MANUAL |
| CAPTURA_MANUAL | BUSCA |

Os Injects simulam o progresso operacional. Não há detecção de objeto real nem
transições temporizadas que retomem uma missão sem intervenção. Todo modo emite
estado e log. Ações manuais de movimento só são aceitas em CAPTURA_MANUAL e
param em até 1 s pelo relógio monotônico local; ao expirar, entram em espera.
Qualquer mudança de modo também zera movimento e seu prazo.

## Decisão e ACK

1. Limite de 16 KiB, UTF-8, JSON estrito (sem NaN, Infinity ou chaves repetidas).
2. Schema e tipo compatível com tópico; versão 1.0 e marca de simulação obrigatória.
3. UUID válido; `source` igual à origem configurada da estação.
4. Comando nunca retained. MQTT 5 e `retainAsPublished` preservam o flag inclusive
   para publicação retained recebida por uma assinatura que já estava ativa.
5. Timestamp com fuso: idade máxima 10 s, tolerância futura 2 s. `expires_at`
   deve ser posterior à emissão e ao recebimento e até 10 s após a emissão.
6. UUID repetido com corpo idêntico dentro da validade recebe o ACK original com
   `duplicate: true`, sem reexecutar. Corpo diferente com o mesmo UUID é rejeitado.
7. Exceto PARAR/SEGURO_ESPERA, exige broker conectado, heartbeat fresco e nenhuma
   falha latched. Em seguida aplica-se a tabela de transições ou a regra manual.

O ACK contém `accepted`, `reason`, `state` resultante da decisão original e
`duplicate`. Para duplicata, `state` pode ser histórico: não deve ser interpretado
como estado atual. Consulte `rover/estado`. JSON malformado ou UUID inválido recebe
ACK de rejeição com `command_id: null`, pois não há correlação confiável. Um
payload inválido com UUID válido preserva a correlação. Mensagens maiores que o
limite do broker podem ser descartadas antes de chegar ao cliente, sem ACK.

A deduplicação guarda até 512 decisões na memória do processo. Não promete
exactly-once através de reinícios ou após a remoção de um ID do cache. QoS 1
admite duplicatas; um futuro protocolo físico deverá tratar persistência e
confirmações do microcontrolador antes de garantir execução única.

## Disponibilidade

`rover/status` e `rover/estado` são retained como último conhecimento. Estado
retained não prova que o Rover está online. Telemetria, alarmes, logs e ACKs não
são retained, evitando reapresentar eventos antigos como novos.

`station/heartbeat` é um tópico adicional necessário para detectar a perda do
Node-RED enquanto o broker permanece ativo. O fluxo envia um pulso por segundo,
com origem esperada, timestamp fresco e UUID de sessão. Retained, origem incorreta
ou pulso velho não renovam o prazo. Sessão nova força espera. O relógio monotônico
mede o timeout local; o relógio UTC valida a idade das mensagens.

Após 4 s sem heartbeat, o controlador entra em espera e gera alarme. O laço do
simulador verifica isso a cada 50 ms (sujeito ao escalonamento do SO, sem garantia
de tempo real). Ao perder o broker, o callback põe o estado em espera, invalida o
heartbeat e zera movimento. A detecção TCP/keepalive não é instantânea; o prazo
de heartbeat continua oferecendo o limite local mesmo quando o TCP fica preso.

Reconexões usam sessão MQTT limpa para evitar fila de comandos antigos. O
controlador assina novamente os tópicos e publica estado seguro e status. O
broker de desenvolvimento não persiste mensagens. Callbacks e ciclo de sensores
são serializados por lock; o gerador artificial não conhece MQTT.

Os contratos desta fase não são uma barreira de autenticação: qualquer cliente
local autorizado ao broker anônimo pode declarar a origem da estação. Use ACL,
credenciais e TLS antes de conectar o Rover pela rede.
