# Detector em tempo real pela câmera

Este diretório contém a aplicação de câmera do projeto. Ela reconhece, em tempo real, as seis peças abaixo:

- `argola_grande`
- `argola_pequena`
- `cilindro_com_base`
- `dado_hexagonal`
- `helice`
- `paraboloide_hiperbolico`

Ela aceita dois formatos de modelo:

- `best.pt`: ideal para testes no computador;
- `best_ncnn_model/`: pasta exportada para NCNN, ideal para o Raspberry Pi.

## Onde colocar o modelo

Os modelos são artefatos gerados e **não entram no Git**. Há duas opções equivalentes:

1. passar ao `--model` o caminho onde o arquivo já está;
2. copiá-lo para a pasta local `modelo_na_camera/models/`, que já é ignorada pelo Git.

Para um teste em tempo real no computador, a organização mais simples é:

```text
modelo_na_camera/
└── models/
    └── best.pt
```

Nesse caso, a partir da raiz do repositório, use `--model ".\modelo_na_camera\models\best.pt"`. Para o Raspberry Pi, copie a pasta NCNN inteira para, por exemplo, `/home/pi/rover/models/best_ncnn_model` e passe esse diretório ao `--model`.

A janela exibe a imagem da câmera, as caixas delimitadoras, a classe, a confiança e o FPS real de inferência. Uma detecção é confirmada depois de dois frames consecutivos por padrão; antes disso, a etiqueta mostra `(1/2)`.

## Executar no Windows

O ambiente criado em `modelo_visao_computacional/.venv` já contém as dependências necessárias. A partir da raiz do repositório:

```powershell
.\modelo_na_camera\run_windows.ps1 --model ".\modelo_visao_computacional\runs\train\pecas_6classes_320\weights\best.pt"
```

Se você copiou um modelo pronto para a pasta local recomendada, execute em vez disso:

```powershell
.\modelo_na_camera\run_windows.ps1 --model ".\modelo_na_camera\models\best.pt"
```

Pressione `Q` ou `Esc` na janela para encerrar. Se a webcam não for a câmera de índice zero, experimente `--camera 1`.

### Usando DroidCam

Inicie o **DroidCam Client** no computador e conecte o telefone antes de abrir o detector. Em seguida, descubra o índice que o OpenCV atribuiu à câmera virtual:

```powershell
.\modelo_na_camera\listar_cameras.ps1
```

O programa exibirá, por exemplo, `[OK] --camera 1: frame 640x480`. Use esse número e o **mesmo backend** que gerou o resultado `[OK]`. Por exemplo, se `msmf` encontrou o DroidCam:

```powershell
.\modelo_na_camera\run_windows.ps1 --model ".\modelo_visao_computacional\runs\train\pecas_6classes_320\weights\best.pt" --camera 1 --backend msmf
```

Em alguns computadores o DroidCam funciona com `msmf`; em outros, com `dshow`. O teste de índices indica qual deles deve ser usado.

Se nenhum índice aparecer, feche aplicativos que possam estar usando a câmera (Teams, Discord, navegador e aplicativo Câmera), confirme em **Configurações do Windows → Privacidade e segurança → Câmera** que aplicativos de desktop podem acessar a câmera e tente:

```powershell
.\modelo_na_camera\listar_cameras.ps1 --backend msmf
```

Para reduzir falsos positivos ou aumentar a exigência do detector:

```powershell
.\modelo_na_camera\run_windows.ps1 --model ".\modelo_visao_computacional\runs\train\pecas_6classes_320\weights\best.pt" --confidence 0.70
```

## Executar no Raspberry Pi

Copie para o Pi:

1. a pasta `modelo_na_camera`;
2. a pasta completa `best_ncnn_model` exportada;
3. opcionalmente, a pasta `modelo_visao_computacional` se desejar usar a mesma estrutura do projeto.

No Raspberry Pi OS 64-bit, dentro de `modelo_na_camera`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x run_pi.sh
./run_pi.sh --model /home/pi/rover/models/best_ncnn_model --fps 8
```

Para um Pi sem monitor, não abra a janela e envie as detecções confirmadas como JSON para o terminal:

```bash
./run_pi.sh --model /home/pi/rover/models/best_ncnn_model --fps 8 --no-display --json
```

O padrão de câmera é `--camera 0`, em 640 × 480, com entrada do detector em 320 px. Sem cooler, comece com `--fps 8`; se o Pi aquecer ou ficar lento, use `--fps 5`.

## Opções úteis

```text
--model CAMINHO          .pt ou pasta *_ncnn_model (obrigatório)
--camera 0               índice da câmera
--width 640 --height 480 resolução solicitada à webcam
--imgsz 320              resolução de entrada do YOLO
--fps 8                  teto de inferências por segundo
--confidence 0.55        confiança mínima
--confirmations 2        frames necessários para confirmar a peça
--no-display             execução sem janela
--json                   imprime caixas e centro em JSON
```

Em alguns computadores Windows, `--backend dshow` ajuda se a câmera não abrir. Em Linux/Raspberry Pi, tente `--backend v4l2` para webcams USB compatíveis com V4L2.

Os arquivos de modelo devem permanecer fora do Git. A pasta `models/` e arquivos `.pt` neste diretório já são ignorados automaticamente.
