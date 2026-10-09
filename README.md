# Robotic Rover

Este repositório contém o detector de visão computacional do Robotic Rover. Ele identifica seis formatos de peça em imagens de uma câmera, independentemente de sua cor. O detector entrega a classe, a confiança, a caixa delimitadora (*bounding box*) e o centro da caixa; a medição de distância por AprilTag é um módulo separado.

O modelo foi pensado para execução em um Raspberry Pi 5 sem cooler: usa uma variante YOLO nano, entrada de 320 × 320 e, para o Pi, o formato NCNN.

## O que foi feito

- O dataset do Roboflow foi incorporado localmente, validado e separado em treino, validação e teste sem misturar frames muito próximos da mesma captura.
- Foi preparado um fluxo para treinamento de um detector de seis classes com Ultralytics YOLO.
- Foram criados scripts para validar rótulos, treinar, avaliar visualmente as imagens de teste, exportar para NCNN e executar a webcam no Raspberry Pi.
- Dados, pesos, ambientes virtuais e resultados gerados são ignorados pelo Git. Apenas código e configurações devem ser versionados.

### Classes do modelo

| ID | Nome usado pelo modelo | Peça |
|---:|---|---|
| 0 | `argola_grande` | argola grande |
| 1 | `argola_pequena` | argola pequena |
| 2 | `cilindro_com_base` | cilindro com base |
| 3 | `dado_hexagonal` | dado hexagonal |
| 4 | `helice` | hélice |
| 5 | `paraboloide_hiperbolico` | paraboloide hiperbólico |

As cores vermelho, preto, azul, cinza e branco **não são classes**: são variações visuais de uma mesma peça.

## Resultado do treinamento atual

O treinamento foi executado com 251 imagens de treino, 71 de validação e 33 de teste (355 imagens anotadas no total). No conjunto de teste, o modelo obteve:

| Métrica | Resultado |
|---|---:|
| Precisão | 95,7% |
| Revocação (*recall*) | 96,2% |
| mAP@50 | 98,4% |
| mAP@50–95 | 83,9% |

### Classes que merecem atenção no próximo treinamento

Neste contexto, são as classes com **menor** *recall* — e não as de maior *recall* — que indicam mais oportunidades de melhoria. Os resultados abaixo justificam prioridade para novas imagens dessas peças:

| Classe | Recall na validação | Recall no teste | Interpretação |
|---|---:|---:|---|
| `cilindro_com_base` | 72,2% | 100,0% | A diferença é grande; precisa de mais cenas independentes para confirmar a generalização. |
| `helice` | 72,6% | 90,8% | Foi a menor taxa no teste; coletar mais ângulos, rotações, sombras e distâncias. |
| `dado_hexagonal` | 92,7% | 90,9% | Também foi uma das menores taxas no teste; incluir mais exemplos isolados e agrupados. |

As demais classes tiveram *recall* de pelo menos 95,3% no teste atual. Esses números são úteis, mas não substituem testes em uma coleta completamente nova e na arena definitiva.

### Pesos e resultados gerados

Após o treinamento, o melhor arquivo de pesos é criado localmente em:

```text
modelo_visao_computacional/runs/train/pecas_6classes_320/weights/best.pt
```

Esse arquivo **não é versionado pelo Git**, assim como as pastas `runs/`, `data/`, `models/` e o ambiente `.venv`. Isso é intencional: pesos, datasets e imagens de resultados são artefatos gerados, potencialmente grandes e reproduzíveis. Um clone limpo do repositório não terá esse caminho até que seja feito um treinamento ou que um modelo seja copiado localmente.

Para compartilhar um modelo pronto, envie o arquivo `.pt` por um meio próprio (por exemplo, armazenamento em nuvem, anexo de release ou pendrive) e informe seu caminho aos comandos abaixo. Não é necessário — nem recomendado — colocá-lo no Git.

## Estrutura relevante

```text
RoboticRover/
├── modelo_visao_computacional/
│   ├── config/                 # nomes e configuração das classes
│   ├── scripts/                # treinamento, exportação e execução
│   ├── vision/                 # código compartilhado
│   ├── treinar.ps1             # comando simples de treinamento no Windows
│   ├── ver_teste_visual.ps1    # comparação visual do conjunto de teste
│   ├── requirements-train.txt
│   └── requirements-pi.txt
├── modelo_na_camera/            # aplicação de detecção em tempo real
│   ├── main.py
│   ├── run_windows.ps1
│   └── run_pi.sh
├── Fotos_pecas/                # imagens originais; não versionadas
└── README.md
```

Os diretórios `modelo_visao_computacional/data`, `runs`, `models` e `.venv` são produzidos localmente e estão no `.gitignore`.

## Requisitos para treinar ou testar no Windows

- Windows com PowerShell;
- Python 3.10 a 3.12;
- ambiente virtual e dependências de treinamento;
- dataset separado em `modelo_visao_computacional/data/yolo` para treinamento/avaliação;
- um arquivo de pesos `.pt` para inferência e revisão visual.

Na primeira utilização, a partir da pasta `modelo_visao_computacional`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-train.txt
```

Se o PowerShell bloquear a ativação, execute uma vez na sessão atual:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

## Usar um modelo `.pt` já pronto

Não há uma etapa especial de “importação”: mantenha o arquivo `.pt` em qualquer pasta acessível e passe seu caminho com `--weights`. Se preferir copiá-lo para dentro do projeto, use `modelo_visao_computacional/models/`; essa pasta é ignorada pelo Git.

Por exemplo, para manter um modelo pronto destinado ao **teste visual** neste repositório, copie-o para:

```text
modelo_visao_computacional/models/best.pt
```

Depois execute, a partir da raiz `RoboticRover`:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1 --weights ".\modelo_visao_computacional\models\best.pt"
```

O modelo não será enviado ao Git, mas as 33 imagens de teste continuam necessárias em `modelo_visao_computacional/data/yolo/images/test`.

Para fazer apenas o teste visual das imagens de teste com um modelo recebido pronto, a partir da raiz `RoboticRover`:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1 --weights "C:\caminho\para\modelo_pronto.pt"
```

Para avaliar quantitativamente esse mesmo modelo nas 33 imagens de teste, abra a pasta `modelo_visao_computacional`, ative o ambiente e execute:

```powershell
python -c "from ultralytics import YOLO; YOLO(r'C:\caminho\para\modelo_pronto.pt').val(data='data/yolo/dataset.runtime.yaml', split='test', imgsz=320, plots=True)"
```

Esse teste exige que o dataset `data/yolo` esteja presente; para uma simples revisão visual, também é necessário que as imagens de teste estejam em `data/yolo/images/test`.

## Treinar o modelo

Com o ambiente preparado, abra o PowerShell na raiz do repositório (`RoboticRover`) e execute:

```powershell
.\modelo_visao_computacional\treinar.ps1
```

O script usa entrada de 320 px, treina por até 150 épocas e aplica *early stopping* caso a validação deixe de melhorar. A CPU funciona, embora seja mais lenta; se houver PyTorch com CUDA instalado, use uma GPU NVIDIA com:

```powershell
.\modelo_visao_computacional\treinar.ps1 --device 0
```

Ao terminar, o melhor modelo é salvo localmente em:

```text
modelo_visao_computacional/runs/train/pecas_6classes_320/weights/best.pt
```

Como explicado acima, esse caminho é ignorado pelo Git e só existirá na máquina que executou o treinamento.

## Testar quantitativamente as 33 imagens de teste

Ainda na pasta `modelo_visao_computacional`, com o ambiente virtual ativo:

```powershell
python -c "from ultralytics import YOLO; YOLO('runs/train/pecas_6classes_320/weights/best.pt').val(data='data/yolo/dataset.runtime.yaml', split='test', imgsz=320, plots=True)"
```

O Ultralytics apresentará precisão, *recall* e mAP por classe. Os gráficos e resultados são gravados em `runs/detect/val`.

> Se `dataset.runtime.yaml` não existir, execute o treinamento uma vez ou use `config/dataset.yaml` ajustando seu campo `path` para o caminho absoluto de `data/yolo`.

Para testar outro arquivo `.pt`, troque somente o primeiro caminho do comando pelo caminho do seu modelo pronto, conforme a seção anterior.

## Teste visual: antes e depois

Para gerar a comparação das 33 imagens de teste, abra o PowerShell na raiz `RoboticRover` e execute:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1
```

Serão criados os arquivos em:

```text
modelo_visao_computacional/runs/visual_test/
```

Cada arquivo `*_comparacao.jpg` contém a imagem original à esquerda e a previsão do modelo à direita, incluindo as *bounding boxes*, classe e confiança. Os arquivos `contato_*.jpg` reúnem seis comparações por página.

Para ver cada comparação numa janela enquanto o programa executa:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1 --show
```

Pressione Espaço para avançar; `q` ou `Esc` encerra.

Se já possui outro modelo `.pt`, informe seu caminho sem copiar ou renomear o arquivo:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1 --weights "C:\caminho\para\outro_modelo.pt"
```

Também é possível trocar o limiar mínimo de confiança, por exemplo para 50%:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1 --confidence 0.50
```

## Exportar o modelo pronto para Raspberry Pi

No computador de treinamento, entre em `modelo_visao_computacional`, ative o ambiente e exporte o `best.pt` para NCNN:

```powershell
python scripts/export_ncnn.py --weights runs/train/pecas_6classes_320/weights/best.pt --imgsz 320
```

Caso o modelo já esteja pronto em outro local, basta apontar para ele:

```powershell
python scripts/export_ncnn.py --weights "C:\caminho\para\modelo.pt" --imgsz 320
```

O comando cria uma pasta com sufixo `_ncnn_model` ao lado do arquivo de pesos. Ela também é ignorada pelo Git; copie a pasta inteira para o Raspberry Pi, por exemplo para `~/rover/models/best_ncnn_model`. Para testar no PC, use o `.pt`; a pasta NCNN é a versão destinada à execução no Pi.

## Detector em tempo real pela câmera

A aplicação recomendada para testar e usar a classificação ao vivo está em [`modelo_na_camera`](modelo_na_camera/README.md). Ela desenha as caixas, classes e confiança sobre a webcam, limita a taxa de inferência e pode emitir as detecções confirmadas em JSON.

No Windows, a partir da raiz do repositório, teste o modelo `.pt`:

```powershell
.\modelo_na_camera\run_windows.ps1 --model ".\modelo_visao_computacional\runs\train\pecas_6classes_320\weights\best.pt"
```

Esse primeiro caminho existe somente depois de treinar localmente. Para usar um `.pt` já pronto sem retreinar, copie-o para `modelo_na_camera/models/best.pt` (pasta ignorada pelo Git) e use:

```powershell
.\modelo_na_camera\run_windows.ps1 --model ".\modelo_na_camera\models\best.pt"
```

Também é válido manter o `.pt` fora do repositório e passar seu caminho absoluto ao `--model`.

Para identificar o índice correto de uma webcam USB ou DroidCam, execute antes:

```powershell
.\modelo_na_camera\listar_cameras.ps1
```

No Raspberry Pi, após copiar a pasta NCNN exportada, execute:

```bash
./run_pi.sh --model /home/pi/rover/models/best_ncnn_model --fps 8
```

Consulte o README desse diretório para instalação, uso sem monitor, saída JSON e opções de câmera.

## Executar na webcam do Raspberry Pi

Recomendado: Raspberry Pi OS 64-bit, Python 3 e câmera funcional. No Pi, copie a pasta `modelo_visao_computacional` (ou ao menos `scripts`, `vision`, `requirements-pi.txt`) e a pasta completa do modelo NCNN exportado.

Instale as dependências:

```bash
cd ~/rover/modelo_visao_computacional
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
```

Execute a câmera, substituindo o caminho do modelo se necessário:

```bash
python3 scripts/run_camera.py \
  --model models/best_ncnn_model \
  --camera 0 \
  --width 640 \
  --height 480 \
  --imgsz 320 \
  --fps 8
```

O programa escreve uma linha JSON por inferência no terminal. Cada detecção confirmada contém `class_id`, `label`, `confidence`, `bbox_xyxy` e `center_xy`. O centro da caixa pode ser usado em conjunto com o módulo de AprilTag, que continuará responsável pela distância.

Para mostrar a janela de depuração na tela do Pi, acrescente `--display`. Comece com `--fps 8`; sem cooler, reduza para `--fps 5` se houver aquecimento ou perda de desempenho. A webcam permanece em 640 × 480, mas o detector recebe a imagem redimensionada para 320 × 320, equilibrando velocidade e precisão.

## Atualizar o dataset no futuro

1. Anote todas as peças visíveis em cada imagem, usando apenas as seis classes na ordem apresentada acima.
2. Exporte do Roboflow no formato **YOLOv8**.
3. Valide os rótulos e gere a separação treino/validação/teste com os scripts em `modelo_visao_computacional/scripts`.
4. Treine novamente, faça a revisão visual e teste na arena antes de substituir o modelo no Pi.

O guia detalhado de preparação de imagens e anotações está em [modelo_visao_computacional/README.md](modelo_visao_computacional/README.md).
