# 📝 Guia Completo de Anotação de Dataset para YOLO

Este guia explica como anotar (labelar) suas imagens para treinar um modelo YOLOv11 customizado que detecte veículos no seu cenário específico.

---

## 📋 Índice

1. [O Que é Anotação de Dataset](#o-que-é-anotação-de-dataset)
2. [Ferramentas de Anotação](#ferramentas-de-anotação)
3. [Guia Passo a Passo - Roboflow (Recomendado)](#guia-roboflow)
4. [Guia Passo a Passo - labelImg (Desktop)](#guia-labelimg)
5. [Guia Passo a Passo - CVAT (Profissional)](#guia-cvat)
6. [Boas Práticas de Anotação](#boas-práticas)
7. [Formato YOLO Explicado](#formato-yolo)
8. [Validação da Anotação](#validação)

---

## 🎯 O Que é Anotação de Dataset

**Anotação** é o processo de marcar (desenhar caixas) ao redor dos objetos nas imagens e identificar sua classe (carro, moto, caminhão, etc.).

### Exemplo Visual

```
Imagem Original:          Imagem Anotada:
┌─────────────────┐      ┌─────────────────┐
│                 │      │  ┌────┐         │
│   🚗   🏍️       │  →   │  │car │  ┌────┐ │
│                 │      │  └────┘  │moto│ │
│      🚛         │      │          └────┘ │
│                 │      │     ┌────────┐  │
└─────────────────┘      │     │ truck  │  │
                         │     └────────┘  │
                         └─────────────────┘
```

Cada caixa contém:
- **Classe:** tipo do veículo (0=car, 1=motorcycle, 2=truck, etc.)
- **Coordenadas:** posição e tamanho da caixa (x, y, width, height)

---

## 🛠️ Ferramentas de Anotação

### Comparação Rápida

| Ferramenta | Tipo | Dificuldade | Export YOLO | Recomendado Para |
|------------|------|-------------|-------------|------------------|
| **Roboflow** | Online | ⭐⭐ Fácil | ✅ Sim | Iniciantes, rapidez |
| **labelImg** | Desktop | ⭐⭐⭐ Médio | ✅ Sim | Trabalho offline |
| **CVAT** | Online/Self-hosted | ⭐⭐⭐⭐ Avançado | ✅ Sim | Projetos grandes, colaboração |
| **Label Studio** | Self-hosted | ⭐⭐⭐⭐ Avançado | ✅ Sim | Customização avançada |

**💡 Recomendação:** Use **Roboflow** para começar (mais fácil e rápido)

---

## 🌐 Guia Roboflow (Recomendado)

### Vantagens
- ✅ Interface intuitiva e fácil de usar
- ✅ Funciona no navegador (sem instalação)
- ✅ Export direto para YOLO
- ✅ Ferramentas de augmentation integradas
- ✅ Gratuito até 10.000 imagens

### Passo a Passo

#### 1. Criar Conta
1. Acesse: https://roboflow.com
2. Clique em **Sign Up** (usar conta Google é mais rápido)
3. Crie um workspace (nome do projeto)

#### 2. Criar Projeto
1. Clique em **Create New Project**
2. Configurações:
   - **Project Name:** `SistemaMonitoramento`
   - **Annotation Group:** Object Detection
   - **What will your model predict?:** Vehicles
3. Clique em **Create Project**

#### 3. Definir Classes
1. Na página do projeto, vá em **Classes**
2. Adicione as classes (clique em "+ Add Class"):
   ```
   car
   motorcycle
   truck
   bus
   bicycle
   ```
3. Salve

#### 4. Upload de Imagens
1. Clique em **Upload Data**
2. Arraste suas imagens capturadas (do `tools/capturar_frames.py`)
3. Selecione **Drag & Drop or Click to Upload**
4. Clique em **Finish Uploading**
5. Aguarde o processamento

#### 5. Anotar Imagens
1. Clique em **Annotate** no menu lateral
2. Selecione a primeira imagem
3. Para cada veículo na imagem:
   - Selecione a classe no lado direito (car, motorcycle, etc.)
   - Clique e arraste para desenhar uma caixa ao redor do veículo
   - **IMPORTANTE:** A caixa deve cobrir TODO o veículo (incluir espelhos, antenas, etc.)
4. Atalhos úteis:
   - **C:** Modo de desenhar caixa
   - **D:** Delete caixa selecionada
   - **Setas ←/→:** Navegar entre imagens
   - **Ctrl+Z:** Desfazer
5. Clique em **Save** quando terminar uma imagem
6. Repita para TODAS as imagens

**🎯 Meta de Anotação:**
- **Mínimo:** 100 imagens por classe
- **Recomendado:** 500+ imagens por classe
- **Ideal:** 1000+ imagens por classe

#### 6. Gerar Dataset
1. Quando terminar de anotar, clique em **Generate**
2. Configurações de augmentation (opcional):
   - **Preprocessing:**
     - Auto-Orient: ✅ Enabled
     - Resize: 640x640 (ou 640x480 se suas imagens forem retangulares)
   - **Augmentation:** (para aumentar dataset)
     - Flip: Horizontal ✅
     - Rotation: ±15°
     - Brightness: ±15%
     - Exposure: ±15%
     - Blur: Up to 1.5px
   - **Número de augmentations:** 2x-3x (gera múltiplas variações)
3. Clique em **Continue**
4. Clique em **Generate**

#### 7. Export para YOLO
1. Após geração, clique em **Export Dataset**
2. **Format:** Selecione **YOLOv11**
3. **Show download code:** Marque ✅
4. Copie o código Python fornecido, exemplo:
   ```python
   from roboflow import Roboflow
   rf = Roboflow(api_key="YOUR_API_KEY")
   project = rf.workspace("seu-workspace").project("sistema-contagem-veiculos")
   dataset = project.version(1).download("yolov11")
   ```
5. Ou clique em **Download ZIP** para baixar diretamente

#### 8. Integrar com Sistema
1. Execute o código de download do Roboflow (se usou código Python)
2. Ou extraia o ZIP baixado
3. Estrutura gerada:
   ```
   dataset/
     data.yaml
     train/
       images/
       labels/
     valid/
       images/
       labels/
     test/ (opcional)
       images/
       labels/
   ```
4. Pronto para treinar! 🎉

---

## 🖥️ Guia labelImg (Desktop)

### Vantagens
- ✅ Funciona offline
- ✅ Leve e rápido
- ✅ Export direto para YOLO
- ✅ Open source

### Instalação

#### Linux/macOS
```bash
pip install labelImg
```

#### Windows
1. Baixe em: https://github.com/HumanSignal/labelImg/releases
2. Extraia o ZIP
3. Execute `labelImg.exe`

### Passo a Passo

#### 1. Configurar labelImg
1. Abra o labelImg
2. Clique em **View** → **Auto Save mode** (para salvar automaticamente)
3. Clique em **View** → **Show Labels** (para exibir labels)

#### 2. Definir Classes
1. Crie arquivo `classes.txt` no mesmo diretório das imagens:
   ```
   car
   motorcycle
   truck
   bus
   bicycle
   ```
2. No labelImg: **Edit** → **Change default saved annotation folder**
   - Selecione a pasta `labels/` (crie se não existir)

#### 3. Carregar Imagens
1. Clique em **Open Dir**
2. Selecione a pasta com suas imagens capturadas

#### 4. Anotar
1. Para cada veículo:
   - Pressione **W** (ou clique em Create RectBox)
   - Desenhe a caixa ao redor do veículo
   - Selecione a classe no popup
2. Navegação:
   - **D:** Próxima imagem
   - **A:** Imagem anterior
   - **Del:** Deletar caixa selecionada
   - **Ctrl+S:** Salvar (se auto-save estiver desabilitado)

#### 5. Verificar Labels
- Cada imagem terá um arquivo `.txt` correspondente na pasta `labels/`
- Exemplo: `frame_001.jpg` → `frame_001.txt`

#### 6. Preparar Dataset
```bash
# Organize estrutura
mkdir -p dataset_anotado/images
mkdir -p dataset_anotado/labels

# Mova as imagens e labels
mv *.jpg dataset_anotado/images/
mv *.txt dataset_anotado/labels/

# Prepare dataset YOLO
python tools/preparar_dataset.py --input ./dataset_anotado --output ./dataset
```

---

## 🏢 Guia CVAT (Profissional)

### Vantagens
- ✅ Colaboração em equipe
- ✅ Ferramentas avançadas (auto-annotation, tracking)
- ✅ Suporte para vídeo
- ✅ Qualidade profissional

### Passo a Passo

#### 1. Criar Conta
1. Acesse: https://www.cvat.ai
2. Clique em **Sign Up** (ou use self-hosted)

#### 2. Criar Projeto
1. Clique em **Projects** → **Create new project**
2. Configure:
   - **Name:** SistemaMonitoramento
   - **Labels:** Adicione `car`, `motorcycle`, `truck`, `bus`, `bicycle`
3. Clique em **Submit**

#### 3. Criar Task
1. Dentro do projeto, clique em **Create new task**
2. Configure:
   - **Name:** Anotação Dataset 001
   - **Select files:** Upload suas imagens
3. Clique em **Submit**

#### 4. Anotar
1. Clique na task criada
2. Clique em **Job #1**
3. Interface de anotação:
   - **N:** Shape mode (desenhar caixa)
   - **Shape:** Arraste para criar caixa
   - **Label:** Selecione a classe
   - **F:** Próxima imagem
   - **D:** Imagem anterior
4. Anote todas as imagens

#### 5. Export
1. Volte ao projeto
2. Clique em **⋮** → **Export dataset**
3. **Format:** YOLO 1.1
4. Clique em **OK**
5. Download do ZIP

#### 6. Preparar Dataset
```bash
# Extrair ZIP
unzip cvat-export.zip -d dataset_anotado

# Preparar dataset
python tools/preparar_dataset.py --input ./dataset_anotado --output ./dataset
```

---

## ✅ Boas Práticas de Anotação

### 1. Qualidade da Caixa
- ✅ **Cobrir TODO o veículo** (incluir espelhos, antenas, reboque)
- ✅ **Ajustado ao contorno** (não deixar muito espaço vazio)
- ❌ **Não cortar partes do veículo**
- ❌ **Não incluir outros veículos na mesma caixa**

### Exemplo Visual
```
✅ BOM:                    ❌ RUIM:
┌─────────┐              ┌───────────────┐
│  🚗     │              │  🚗    🏍️    │  (dois veículos em uma caixa)
│         │              └───────────────┘
└─────────┘
                         ┌────┐
                         │ 🚗 │             (cortado)
                         └────┴────
```

### 2. Veículos Parcialmente Visíveis
- ✅ **Anotar mesmo se parcialmente cortado** (≥20% visível)
- ❌ **Não anotar se muito pequeno/distante** (<10 pixels)
- ❌ **Não anotar se totalmente obstruído**

### 3. Consistência
- ✅ **Sempre usar a mesma classe** para mesmo tipo de veículo
- ✅ **Ser consistente com categorização** (ex: pickup é car ou truck?)
- ✅ **Definir regras claras** (ex: motos incluem scooters? sim!)

### 4. Casos Especiais

| Veículo | Classe | Observação |
|---------|--------|------------|
| Carro sedan | `car` | Padrão |
| SUV/Pickup | `car` | Considerar como carro |
| Moto/Scooter | `motorcycle` | Incluir todos tipos de 2 rodas motorizadas |
| Caminhão pequeno | `truck` | Qualquer veículo de carga |
| Caminhão grande | `truck` | Incluir carretas |
| Van/Kombi | `car` ou `bus` | Decidir regra e seguir |
| Ônibus | `bus` | Micro-ônibus também |

### 5. Variedade do Dataset
Inclua imagens com:
- ✅ **Diferentes ângulos** (frontal, lateral, traseira)
- ✅ **Diferentes distâncias** (perto, longe)
- ✅ **Diferentes condições** (dia, noite, chuva, sol)
- ✅ **Diferentes densidades** (trânsito leve, pesado)
- ✅ **Oclusões** (veículos parcialmente cobertos)

### 6. Quantidade Recomendada

| Nível | Imagens por Classe | Total Estimado | Tempo Estimado |
|-------|-------------------|----------------|----------------|
| **Mínimo** | 100 | 500 imagens | ~8-10 horas |
| **Bom** | 300 | 1.500 imagens | ~25-30 horas |
| **Ótimo** | 500+ | 2.500+ imagens | ~40-50 horas |
| **Profissional** | 1000+ | 5.000+ imagens | ~80-100 horas |

**💡 Dica:** Comece com mínimo (100), treine, teste, e aumente se necessário!

---

## 📐 Formato YOLO Explicado

### Estrutura do Arquivo `.txt`

Cada imagem tem um arquivo `.txt` correspondente com o mesmo nome:
```
frame_001.jpg → frame_001.txt
frame_002.jpg → frame_002.txt
```

### Formato de Cada Linha
```
<class_id> <x_center> <y_center> <width> <height>
```

**Valores normalizados (0.0 a 1.0):**
- `class_id`: ID da classe (0=car, 1=motorcycle, 2=truck, etc.)
- `x_center`: Centro X da caixa (relativo à largura da imagem)
- `y_center`: Centro Y da caixa (relativo à altura da imagem)
- `width`: Largura da caixa (relativa à largura da imagem)
- `height`: Altura da caixa (relativa à altura da imagem)

### Exemplo Real

**Imagem:** 1920x1080 pixels
**Veículo:** Carro no centro da imagem

**Caixa:**
- Posição: (700, 400) a (1100, 700)
- Centro: (900, 550)
- Tamanho: 400x300

**Normalização:**
```
x_center = 900 / 1920 = 0.46875
y_center = 550 / 1080 = 0.50926
width = 400 / 1920 = 0.20833
height = 300 / 1080 = 0.27778
```

**Label final:**
```
0 0.46875 0.50926 0.20833 0.27778
```

### Exemplo com Múltiplos Veículos

```
0 0.3 0.5 0.15 0.2    # Carro à esquerda
1 0.6 0.4 0.08 0.12   # Moto à direita
0 0.8 0.6 0.18 0.25   # Outro carro
```

---

## ✔️ Validação da Anotação

### 1. Verificação Visual (Script Python)

Crie script `visualizar_anotacoes.py`:

```python
import cv2
import os
from pathlib import Path

def visualizar_anotacoes(img_path, label_path):
    """Visualiza anotações em uma imagem"""
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]

    # Lê labels
    with open(label_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            class_id = int(parts[0])
            x_center, y_center, width, height = map(float, parts[1:])

            # Converte para pixels
            x1 = int((x_center - width/2) * w)
            y1 = int((y_center - height/2) * h)
            x2 = int((x_center + width/2) * w)
            y2 = int((y_center + height/2) * h)

            # Desenha caixa
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, f"Class {class_id}", (x1, y1-5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Mostra imagem
    cv2.imshow('Anotações', img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

# Uso
visualizar_anotacoes('frame_001.jpg', 'frame_001.txt')
```

### 2. Checklist de Qualidade

Antes de treinar, verifique:

- [ ] Todas as imagens têm label correspondente?
- [ ] Todos os veículos visíveis foram anotados?
- [ ] As caixas estão bem ajustadas?
- [ ] As classes estão corretas?
- [ ] Labels não têm erros de formato?
- [ ] Dataset tem variedade suficiente?
- [ ] Mínimo de 100 imagens por classe?

### 3. Script de Validação

```bash
# Conta imagens e labels
echo "Imagens: $(ls images/*.jpg | wc -l)"
echo "Labels: $(ls labels/*.txt | wc -l)"

# Verifica pares
for img in images/*.jpg; do
  label="labels/$(basename ${img%.jpg}.txt)"
  if [ ! -f "$label" ]; then
    echo "Faltando: $label"
  fi
done

# Conta anotações por classe
echo "Distribuição de classes:"
cat labels/*.txt | awk '{print $1}' | sort | uniq -c
```

---

## 🎯 Resumo Rápido

1. **Capturar frames:** `python tools/capturar_frames.py`
2. **Anotar:** Use Roboflow (fácil) ou labelImg (offline)
3. **Preparar dataset:** `python tools/preparar_dataset.py`
4. **Treinar:** `python tools/treinar_modelo.py --dataset dataset/data.yaml`
5. **Validar:** `python tools/validar_modelo.py --model best.pt`
6. **Integrar:** Atualizar `config.json` com novo modelo

---

## 📚 Recursos Adicionais

- **Roboflow:** https://roboflow.com
- **labelImg:** https://github.com/HumanSignal/labelImg
- **CVAT:** https://www.cvat.ai
- **YOLO Docs:** https://docs.ultralytics.com
- **Dataset Público (COCO):** https://cocodataset.org

---

## 💡 Dicas Finais

1. **Comece pequeno:** 100-200 imagens para validar processo
2. **Teste cedo:** Treine com dataset pequeno primeiro
3. **Iteração:** Anote → Treine → Teste → Anote mais onde falhou
4. **Foco nas falhas:** Se motos não são detectadas, anote MAIS motos
5. **Qualidade > Quantidade:** 500 imagens bem anotadas > 2000 ruins
6. **Seja consistente:** Defina regras claras e siga sempre

**Boa anotação! 🚀**
