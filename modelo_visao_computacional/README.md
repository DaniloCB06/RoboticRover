# Modelo de visão computacional — Robotic Rover

Detector de objetos para reconhecer seis **tipos de peça**, independente da cor. O alvo de implantação é um Raspberry Pi 5 sem acelerador e sem cooler; por isso o projeto usa um modelo YOLO nano, entrada de 320×320 e runtime NCNN.

## Decisões do projeto

- Classes: seis formatos; vermelho, preto, azul, cinza e branco são variações da mesma classe.
- Entrada do detector: **320×320** com *letterbox*. A câmera pode continuar em 640×480.
- Plataforma: Raspberry Pi 5, inferência limitada inicialmente a 8 FPS para conter aquecimento.
- Escopo: o detector devolve tipo, confiança e caixa/centro da peça. A distância por AprilTag continua desacoplada.

## Estrutura esperada dos dados

```text
data/
├── unlabeled/
│   ├── images/                 # gerado por prepare_images.py
│   └── manifest.csv
├── annotated/
│   ├── images/                 # cópia das imagens após anotação
│   └── labels/                 # um .txt YOLO por imagem
└── yolo/                       # gerado por split_dataset.py
    ├── images/{train,val,test}/
    └── labels/{train,val,test}/
```

O formato de cada linha de rótulo YOLO é:

```text
<id_classe> <centro_x> <centro_y> <largura> <altura>
```

Todas as coordenadas são normalizadas entre zero e um. Cada peça visível deve ter uma caixa; se houver três peças em uma foto, o respectivo `.txt` terá três linhas. Consulte `config/dataset.yaml` para a numeração das seis classes.

| ID | Nome técnico usado no dataset | Peça |
|---:|---|---|
| 0 | `argola_grande` | argola grande |
| 1 | `argola_pequena` | argola pequena |
| 2 | `cilindro_com_base` | cilindro com base |
| 3 | `dado_hexagonal` | dado hexagonal |
| 4 | `helice` | hélice |
| 5 | `paraboloide_hiperbolico` | paraboloide hiperbólico |

## 1. Preparar as imagens

No PowerShell, a partir desta pasta:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-train.txt
python scripts/prepare_images.py --source ..\Fotos_pecas
```

O script não altera `Fotos_pecas`. Ele cria cópias das imagens únicas em `data/unlabeled/images` e um manifesto com as cópias exatas ignoradas. No conjunto atual, espera-se obter 355 imagens únicas de 504 arquivos.

## 2. Anotar

Use CVAT, Roboflow Annotate, Label Studio ou outro anotador que exporte **YOLO Object Detection**. Anote apenas a geometria/tipo da peça, sem criar classes de cor.

Importe ou crie as seis classes na mesma ordem de `config/classes.txt`. Para cada peça, desenhe um retângulo horizontal que cubra toda a área visível da peça e escolha seu tipo. Não use caixas rotacionadas, não inclua sombras nem objetos de fundo e marque todas as peças quando houver mais de uma na imagem. Uma peça parcialmente escondida deve ser anotada somente se seu tipo ainda for inequívoco.

Depois da exportação, coloque imagens e arquivos `.txt` em `data/annotated/images` e `data/annotated/labels`, mantendo exatamente o mesmo nome-base. Use as imagens preparadas, não as 504 originais: isso evita que cópias exatas contaminem treino e validação.

É indispensável incluir cenas mais próximas das condições reais: chão da arena, iluminação final, sombra, desfoque por movimento, rotações, sobreposição parcial e objetos que não são peças. Fotos consecutivas quase iguais não substituem novas cenas independentes.

## 3. Validar e separar o dataset

```powershell
python scripts/validate_annotations.py --images data/annotated/images --labels data/annotated/labels
python scripts/split_dataset.py --images data/annotated/images --labels data/annotated/labels --group-minutes 5
```

O split é feito por blocos de tempo no nome das fotos, nunca por sorteio individual de frames. Isso reduz vazamento entre imagens muito parecidas. Confira a saída: todas as seis classes devem ter exemplos tanto no treino quanto na validação. Caso uma tomada contínua tenha durado mais que cinco minutos, aumente `--group-minutes`; use `--group-seconds 10` somente se blocos maiores deixarem uma classe fora da validação/teste. Se não houver ao menos três blocos independentes, colete novas sessões antes de treinar.

## 4. Treinar

Com o dataset já preparado, execute um único comando a partir da raiz do repositório:

```powershell
.\modelo_visao_computacional\treinar.ps1
```

O comando detecta automaticamente uma GPU CUDA, se o PyTorch CUDA estiver instalado; caso contrário, treina em CPU. Ele usa `data/yolo`, constrói um YAML com caminhos absolutos, treina por até 150 épocas e aplica *early stopping* após 35 épocas sem evolução na validação. Não depende do diretório em que o PowerShell foi aberto.

Para forçar uma GPU NVIDIA disponível:

```powershell
.\modelo_visao_computacional\treinar.ps1 --device 0
```

O melhor checkpoint ficará em `runs/train/pecas_6classes_320/weights/best.pt`. Antes de exportar, revise as métricas de validação e, sobretudo, teste com fotos e vídeo de uma sessão que não participou do treino.

### Revisão visual do conjunto de teste

Para gerar uma comparação para cada imagem de teste, execute a partir da raiz do repositório:

```powershell
.\modelo_visao_computacional\ver_teste_visual.ps1
```

O resultado é gravado em `modelo_visao_computacional/runs/visual_test/`. Cada arquivo mostra a imagem original à esquerda e as caixas/classes previstas à direita. Os arquivos `contato_*.jpg` agrupam seis comparações por página para revisão rápida. Para abrir uma imagem por vez durante a execução, acrescente `--show`.

## 5. Exportar para o Raspberry Pi

```powershell
python scripts/export_ncnn.py --weights runs/train/pecas_6classes_320/weights/best.pt
```

Copie a pasta resultante `best_ncnn_model` para o Pi. No Raspberry Pi OS 64-bit:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-pi.txt
```

## 6. Executar na webcam

```bash
python3 scripts/run_camera.py --model models/best_ncnn_model --camera 0
```

O programa captura em 640×480, executa o detector a 320×320 e limita a inferência a 8 FPS. Cada linha emitida é JSON com as peças confirmadas em pelo menos três frames, por exemplo:

```json
{"timestamp_monotonic": 123.456, "detections": [{"class_id": 2, "label": "cilindro_com_base", "confidence": 0.91, "bbox_xyxy": [130.2, 85.1, 255.8, 364.0], "center_xy": [193.0, 224.6], "confirmations": 3}]}
```

Para depuração com janela de vídeo, acrescente `--display`. Para reduzir calor sem cooler, mantenha inicialmente `--fps 8`; se o Pi aquecer ou reduzir desempenho, use `--fps 5`. Se as peças estiverem pequenas demais a 320 px, teste `--imgsz 416` primeiro no hardware real, pois isso aumentará consumo e latência.

## Critério de aceite inicial

Só integre a detecção à navegação depois que o modelo:

1. reconhecer as seis peças nas cinco cores em um cenário que não foi usado no treino;
2. não confundir objetos do cenário com peças de forma recorrente;
3. operar de maneira estável durante alguns minutos no Pi 5 sem queda excessiva de velocidade;
4. entregar centro da caixa consistente para que o módulo de AprilTag faça a aproximação final.
