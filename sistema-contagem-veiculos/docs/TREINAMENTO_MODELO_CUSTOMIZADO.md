# 🎓 Guia Completo: Treinamento de Modelo YOLOv11 Customizado

Este guia completo explica **todo o processo** para treinar um modelo YOLOv11 customizado que detecte melhor veículos, motos e caminhões no seu cenário específico.

---

## 📋 Índice

1. [Por Que Treinar Modelo Customizado?](#por-que-customizado)
2. [Requisitos do Sistema](#requisitos)
3. [Processo Completo (Visão Geral)](#processo-completo)
4. [Etapa 1: Captura de Frames](#etapa-1-captura)
5. [Etapa 2: Anotação de Dataset](#etapa-2-anotacao)
6. [Etapa 3: Preparação do Dataset](#etapa-3-preparacao)
7. [Etapa 4: Treinamento do Modelo](#etapa-4-treinamento)
8. [Etapa 5: Validação do Modelo](#etapa-5-validacao)
9. [Etapa 6: Integração no Sistema](#etapa-6-integracao)
10. [Troubleshooting](#troubleshooting)
11. [FAQ](#faq)

---

## 🎯 Por Que Treinar Modelo Customizado? {#por-que-customizado}

### Problema

O modelo YOLOv11 pré-treinado no dataset COCO foi treinado com imagens gerais da internet. Seu cenário específico pode ter:

- **Ângulos diferentes:** Câmera em posição elevada/lateral
- **Condições diferentes:** Iluminação específica, clima local
- **Veículos diferentes:** Tipos comuns na sua região
- **Qualidade diferente:** Resolução/compressão da câmera

**Resultado:** Motos não detectadas, caminhões pequenos ignorados, etc.

### Solução

Treinar um modelo com **imagens do seu próprio sistema** garante:

- ✅ **Detecção precisa** no seu cenário específico
- ✅ **Melhor reconhecimento** de motos e veículos problemáticos
- ✅ **Adaptação** às condições de iluminação e ângulo
- ✅ **Redução de falsos positivos/negativos**

---

## 💻 Requisitos do Sistema {#requisitos}

### Hardware Mínimo

| Componente | Mínimo | Recomendado | Ideal |
|------------|--------|-------------|-------|
| **CPU** | 4 cores | 8 cores | 16+ cores |
| **RAM** | 8 GB | 16 GB | 32 GB |
| **GPU** | Nenhuma (CPU) | NVIDIA 6GB VRAM | NVIDIA 12GB+ VRAM |
| **Storage** | 20 GB livre | 50 GB livre | 100 GB+ livre |

**⚠️ IMPORTANTE:** Treinamento na CPU é **MUITO mais lento** (dias vs horas)

### Software

```bash
# Python 3.8+
python --version

# Ultralytics (YOLO)
pip install ultralytics

# OpenCV
pip install opencv-python

# PyTorch (com CUDA se tiver GPU)
# Para GPU:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118

# Para CPU apenas:
pip install torch torchvision
```

### Verificar GPU

```python
import torch
print(f"CUDA disponível: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")
```

---

## 🔄 Processo Completo (Visão Geral) {#processo-completo}

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUXO DE TREINAMENTO                         │
└─────────────────────────────────────────────────────────────────┘

1️⃣ CAPTURA DE FRAMES
   │
   ├─► Script: capturar_frames.py
   ├─► Input: Stream RTSP
   ├─► Output: 500-1000 imagens (.jpg)
   └─► Tempo: 1-2 horas

2️⃣ ANOTAÇÃO DE DATASET
   │
   ├─► Ferramenta: Roboflow / labelImg / CVAT
   ├─► Input: Imagens capturadas
   ├─► Output: Labels YOLO (.txt)
   └─► Tempo: 8-50 horas (depende da quantidade)

3️⃣ PREPARAÇÃO DO DATASET
   │
   ├─► Script: preparar_dataset.py
   ├─► Input: Imagens + Labels
   ├─► Output: Dataset estruturado (train/val/test)
   └─► Tempo: 5 minutos

4️⃣ TREINAMENTO DO MODELO
   │
   ├─► Script: treinar_modelo.py
   ├─► Input: Dataset preparado
   ├─► Output: Modelo treinado (best.pt)
   └─► Tempo: 2-24 horas (GPU) ou 3-7 dias (CPU)

5️⃣ VALIDAÇÃO DO MODELO
   │
   ├─► Script: validar_modelo.py
   ├─► Input: Modelo treinado + imagens teste
   ├─► Output: Métricas e visualizações
   └─► Tempo: 10-30 minutos

6️⃣ INTEGRAÇÃO NO SISTEMA
   │
   ├─► Copiar modelo treinado
   ├─► Atualizar config.json
   ├─► Reiniciar sistema
   └─► Tempo: 5 minutos

✅ MODELO CUSTOMIZADO FUNCIONANDO!
```

---

## 📸 Etapa 1: Captura de Frames {#etapa-1-captura}

### Objetivo

Capturar 500-1000 imagens do seu stream RTSP que representem bem o cenário real.

### Script

```bash
python tools/capturar_frames.py \
    --output ./dataset/images \
    --interval 2 \
    --total 500
```

### Parâmetros

| Parâmetro | Descrição | Valor Recomendado |
|-----------|-----------|-------------------|
| `--url` | URL RTSP (opcional, usa config.json) | - |
| `--output` | Diretório de saída | `./dataset/images` |
| `--interval` | Segundos entre capturas | `2` (varia) |
| `--total` | Total de frames | `500-1000` |
| `--no-buffer` | Não usar buffer (fallback) | Não usar |

### Estratégia de Captura

#### Opção A: Captura Contínua (Recomendado)
Capturar ao longo de vários períodos:

```bash
# Manhã (trânsito intenso)
python tools/capturar_frames.py --total 200 --interval 3 --output ./dataset/images_manha

# Tarde (iluminação diferente)
python tools/capturar_frames.py --total 200 --interval 3 --output ./dataset/images_tarde

# Noite (condições difíceis)
python tools/capturar_frames.py --total 100 --interval 3 --output ./dataset/images_noite

# Combinar todas
mkdir -p ./dataset/images
cp ./dataset/images_*/*.jpg ./dataset/images/
```

#### Opção B: Captura Focada
Se você sabe quando há mais motos/caminhões:

```bash
# Capturar em horário de pico de motos
python tools/capturar_frames.py --total 500 --interval 1 --output ./dataset/images
```

### Dicas

- ✅ **Variedade:** Capture em diferentes horários/dias
- ✅ **Foco no problema:** Se motos são o problema, capture quando há mais motos
- ✅ **Condições variadas:** Sol, nublado, chuva, noite
- ✅ **Movimento:** Capture com trânsito (não estacionários)
- ❌ **Evitar:** Imagens borradas, muito escuras, sem veículos

### Resultado Esperado

```
dataset/images/
  ├── frame_20250124_083021_123456_0000.jpg
  ├── frame_20250124_083023_234567_0001.jpg
  ├── frame_20250124_083025_345678_0002.jpg
  └── ... (498 mais)
```

**Próxima etapa:** [Anotação de Dataset](#etapa-2-anotacao)

---

## 📝 Etapa 2: Anotação de Dataset {#etapa-2-anotacao}

### Objetivo

Marcar (desenhar caixas) ao redor de TODOS os veículos nas imagens capturadas.

### Ferramentas

Escolha UMA das opções:

| Ferramenta | Dificuldade | Tempo/Img | Recomendado Para |
|------------|-------------|-----------|------------------|
| **Roboflow** | ⭐⭐ Fácil | ~2-3 min | Iniciantes |
| **labelImg** | ⭐⭐⭐ Médio | ~3-4 min | Offline |
| **CVAT** | ⭐⭐⭐⭐ Avançado | ~2-3 min | Profissional |

**💡 Recomendação:** Use **Roboflow** (mais fácil e rápido)

### Guia Completo

Consulte o guia detalhado: **[GUIA_ANOTACAO_DATASET.md](./GUIA_ANOTACAO_DATASET.md)**

### Resumo Rápido - Roboflow

1. **Criar conta:** https://roboflow.com
2. **Criar projeto:** Object Detection
3. **Definir classes:** `car`, `motorcycle`, `truck`, `bus`, `bicycle`
4. **Upload imagens:** Arraste as 500 imagens
5. **Anotar:**
   - Desenhe caixas ao redor de TODOS os veículos
   - Selecione a classe correta
   - Salve e próxima imagem
6. **Gerar dataset:** Com augmentation (2x-3x)
7. **Export:** Formato YOLOv11
8. **Download:** ZIP ou código Python

### Estimativa de Tempo

| Imagens | Tempo Estimado | Veículos por Imagem |
|---------|----------------|---------------------|
| 100 | ~3-5 horas | 3-5 veículos |
| 300 | ~10-15 horas | 3-5 veículos |
| 500 | ~15-25 horas | 3-5 veículos |
| 1000 | ~30-50 horas | 3-5 veículos |

**💡 Dica:** Faça em sessões de 1-2 horas para não cansar

### Qualidade da Anotação

**BOM ✅:**
- Caixa cobre TODO o veículo
- Inclui espelhos, antenas, reboque
- Classe correta
- Todos os veículos anotados

**RUIM ❌:**
- Caixa cortando partes
- Veículos faltando
- Classe errada
- Dois veículos em uma caixa

### Resultado Esperado

```
dataset_roboflow/
  ├── data.yaml
  ├── train/
  │   ├── images/
  │   │   ├── frame_001.jpg
  │   │   └── ...
  │   └── labels/
  │       ├── frame_001.txt
  │       └── ...
  └── valid/
      ├── images/
      └── labels/
```

**Próxima etapa:** [Preparação do Dataset](#etapa-3-preparacao)

---

## 🔧 Etapa 3: Preparação do Dataset {#etapa-3-preparacao}

### Objetivo

Organizar dataset anotado na estrutura correta para treinamento YOLO.

### Quando usar este script?

- ✅ Se anotou com **labelImg** (precisa dividir train/val)
- ✅ Se tem estrutura diferente da esperada
- ❌ **NÃO** necessário se usou Roboflow (já exporta pronto)

### Script

```bash
python tools/preparar_dataset.py \
    --input ./dataset_anotado \
    --output ./dataset \
    --split 0.8 0.15 0.05
```

### Parâmetros

| Parâmetro | Descrição | Valor Recomendado |
|-----------|-----------|-------------------|
| `--input` | Diretório com images/ e labels/ | `./dataset_anotado` |
| `--output` | Diretório de saída | `./dataset` |
| `--split` | Train Val Test splits | `0.8 0.15 0.05` |
| `--classes` | Nomes das classes (opcional) | Auto-detecta |
| `--seed` | Seed para randomização | `42` |

### Estrutura de Input Esperada

```
dataset_anotado/
  ├── images/
  │   ├── img001.jpg
  │   ├── img002.jpg
  │   └── ...
  └── labels/
      ├── img001.txt
      ├── img002.txt
      └── ...
```

### Estrutura de Output Gerada

```
dataset/
  ├── data.yaml          ← Configuração do dataset
  ├── train/
  │   ├── images/        ← 80% das imagens
  │   └── labels/        ← 80% dos labels
  ├── val/
  │   ├── images/        ← 15% das imagens
  │   └── labels/        ← 15% dos labels
  └── test/              ← 5% das imagens (opcional)
      ├── images/
      └── labels/
```

### Arquivo data.yaml

Exemplo gerado automaticamente:

```yaml
path: /caminho/completo/dataset
train: train/images
val: val/images
test: test/images

names:
  0: car
  1: motorcycle
  2: truck
  3: bus
  4: bicycle
```

### Validação

Verifique a estrutura:

```bash
# Conta arquivos
echo "Train images: $(ls dataset/train/images/*.jpg | wc -l)"
echo "Train labels: $(ls dataset/train/labels/*.txt | wc -l)"
echo "Val images: $(ls dataset/val/images/*.jpg | wc -l)"
echo "Val labels: $(ls dataset/val/labels/*.txt | wc -l)"

# Visualiza data.yaml
cat dataset/data.yaml
```

**Próxima etapa:** [Treinamento do Modelo](#etapa-4-treinamento)

---

## 🏋️ Etapa 4: Treinamento do Modelo {#etapa-4-treinamento}

### Objetivo

Treinar modelo YOLOv11 customizado com seu dataset anotado.

### Script

```bash
python tools/treinar_modelo.py \
    --dataset ./dataset/data.yaml \
    --model yolo11n.pt \
    --epochs 100 \
    --batch 16 \
    --img 640
```

### Parâmetros Importantes

| Parâmetro | Descrição | Valores | Recomendação |
|-----------|-----------|---------|--------------|
| `--dataset` | Path do data.yaml | - | Obrigatório |
| `--model` | Modelo base | n/s/m/l/x | `yolo11n.pt` (início) → `yolo11s.pt` (produção) |
| `--epochs` | Número de épocas | 50-300 | `100` (com early stopping) |
| `--batch` | Batch size | 4/8/16/32/-1 | Depende da GPU |
| `--img` | Tamanho imagem | 640/1280 | `640` (padrão) |
| `--device` | Device | auto/0/cpu | `auto` (detecta GPU) |
| `--patience` | Early stopping | 30-100 | `50` |

### Escolha do Modelo Base

| Modelo | Velocidade | Precisão | VRAM | Recomendado Para |
|--------|-----------|----------|------|------------------|
| `yolo11n.pt` | ⚡⚡⚡⚡⚡ Muito Rápido | ⭐⭐⭐ Boa | 2GB | Testes iniciais, hardware limitado |
| `yolo11s.pt` | ⚡⚡⚡⚡ Rápido | ⭐⭐⭐⭐ Muito Boa | 4GB | **Produção (recomendado)** |
| `yolo11m.pt` | ⚡⚡⚡ Médio | ⭐⭐⭐⭐⭐ Excelente | 6GB | Alta precisão |
| `yolo11l.pt` | ⚡⚡ Lento | ⭐⭐⭐⭐⭐ Excepcional | 10GB | GPU potente |
| `yolo11x.pt` | ⚡ Muito Lento | ⭐⭐⭐⭐⭐ Máxima | 16GB | Melhor qualidade possível |

### Ajuste de Batch Size (GPU)

Se houver erro de **Out of Memory (OOM)**:

```bash
# Reduzir batch size progressivamente
--batch 16  # Tentar primeiro
--batch 8   # Se OOM
--batch 4   # Se ainda OOM
--batch -1  # Auto (detecta automaticamente)
```

**Referência:**
- **4GB VRAM:** batch 8-16
- **6GB VRAM:** batch 16-32
- **8GB+ VRAM:** batch 32+

### Treinamento na CPU (Não Recomendado)

```bash
python tools/treinar_modelo.py \
    --dataset ./dataset/data.yaml \
    --device cpu \
    --batch 4 \
    --epochs 50  # Reduzir épocas
```

**⚠️ Tempo estimado:** 3-7 dias (vs 2-6 horas na GPU)

### Monitoramento do Treinamento

Durante o treinamento, você verá:

```
Epoch    GPU_mem   box_loss   cls_loss   dfl_loss  Instances       Size
  1/100      1.2G     1.2345     0.8765     1.4567        128        640: 100%|████| 50/50 [02:15<00:00,  2.70s/it]
            Class     Images  Instances      Box(P          R      mAP50  mAP50-95)
              all        100        450      0.723      0.681      0.728      0.512

Epoch    GPU_mem   box_loss   cls_loss   dfl_loss  Instances       Size
  2/100      1.2G     1.1234     0.7654     1.3456        128        640: 100%|████| 50/50 [02:10<00:00,  2.60s/it]
...
```

**O que observar:**
- ✅ **Losses diminuindo:** box_loss, cls_loss, dfl_loss
- ✅ **mAP aumentando:** mAP50, mAP50-95
- ⚠️ **Overfitting:** Train loss baixo, val loss alto

### Early Stopping

O treinamento para automaticamente se não houver melhoria após N épocas (patience=50):

```
Stopping training early as no improvement observed in last 50 epochs.
Best results observed at epoch 73.
```

**Resultado:** Modelo salvo em `runs/train/custom_model/weights/best.pt`

### Tempo Estimado

| Configuração | Imagens | Épocas | GPU | Tempo Estimado |
|--------------|---------|--------|-----|----------------|
| Teste | 200 | 50 | GTX 1660 (6GB) | ~1 hora |
| Pequeno | 500 | 100 | RTX 3060 (12GB) | ~2-3 horas |
| Médio | 1000 | 100 | RTX 3080 (10GB) | ~4-6 horas |
| Grande | 2000 | 150 | RTX 4090 (24GB) | ~8-12 horas |
| CPU | 500 | 50 | i7 8-core | ~3-5 dias |

### Logs e Resultados

Após o treinamento:

```
runs/train/custom_model/
  ├── weights/
  │   ├── best.pt       ← Melhor modelo (menor val loss)
  │   └── last.pt       ← Último modelo
  ├── results.png       ← Gráficos de loss e métricas
  ├── confusion_matrix.png
  ├── F1_curve.png
  ├── P_curve.png
  ├── PR_curve.png
  ├── R_curve.png
  └── train_batch*.jpg  ← Exemplos de augmentation
```

**Analise:**
1. **results.png:** Losses e mAP por época
2. **confusion_matrix.png:** Erros de classificação
3. **P_curve.png / R_curve.png:** Precision/Recall vs confiança

**Próxima etapa:** [Validação do Modelo](#etapa-5-validacao)

---

## ✅ Etapa 5: Validação do Modelo {#etapa-5-validacao}

### Objetivo

Testar modelo treinado em imagens/vídeos reais para verificar qualidade.

### Script

```bash
python tools/validar_modelo.py \
    --model ./runs/train/custom_model/weights/best.pt \
    --source ./test_images \
    --conf 0.25 \
    --output ./results
```

### Parâmetros

| Parâmetro | Descrição | Valor Recomendado |
|-----------|-----------|-------------------|
| `--model` | Path do modelo .pt | `best.pt` |
| `--source` | Imagens ou vídeo | `./test_images` |
| `--conf` | Threshold confiança | `0.25` (ajustar) |
| `--output` | Diretório de saída | `./results` |
| `--no-show` | Não exibir janela | Para servidor |

### Validação em Imagens

```bash
# Testar em imagens de teste
python tools/validar_modelo.py \
    --model best.pt \
    --source ./test_images \
    --output ./results
```

**Estatísticas exibidas:**
```
📊 ESTATÍSTICAS DE VALIDAÇÃO:
======================================================================
Total de imagens: 50
Imagens com detecções: 48 (96.0%)
Total de detecções: 167
Média de detecções por imagem: 3.48
Confiança média: 0.742

🎯 Detecções por classe:
   car            :   98 ( 58.7%)
   motorcycle     :   42 ( 25.1%)
   truck          :   18 ( 10.8%)
   bus            :    7 (  4.2%)
   bicycle        :    2 (  1.2%)

⏱️  Tempo médio de processamento: 0.023s
   FPS estimado: 43.5
======================================================================
```

### Validação em Vídeo

```bash
# Testar em vídeo
python tools/validar_modelo.py \
    --model best.pt \
    --source video_teste.mp4 \
    --output resultado.mp4
```

### Análise dos Resultados

#### Métricas Importantes

| Métrica | O Que Significa | Valor Bom |
|---------|-----------------|-----------|
| **mAP50** | Precisão geral (IoU ≥ 50%) | > 0.7 |
| **mAP50-95** | Precisão rigorosa | > 0.5 |
| **Precision** | % de detecções corretas | > 0.8 |
| **Recall** | % de objetos detectados | > 0.75 |
| **FPS** | Velocidade de inferência | > 20 |

#### Checklist de Qualidade

- [ ] **Motos detectadas?** Verificar se melhora é visível
- [ ] **Caminhões pequenos detectados?**
- [ ] **Falsos positivos baixos?** (<5%)
- [ ] **Detecções estáveis?** Não piscando
- [ ] **Velocidade adequada?** FPS >20 para tempo real
- [ ] **Classes corretas?** Não confundindo car/truck

### Comparação Antes/Depois

Teste o mesmo vídeo com:

1. **Modelo original:**
   ```bash
   python tools/validar_modelo.py --model yolo11n.pt --source video.mp4 --output resultado_original.mp4
   ```

2. **Modelo treinado:**
   ```bash
   python tools/validar_modelo.py --model best.pt --source video.mp4 --output resultado_customizado.mp4
   ```

3. **Compare:** Assista os dois vídeos lado a lado

### Ajustes de Confiança

Se houver problemas:

**Muitos falsos positivos:**
```bash
# Aumentar threshold
--conf 0.4  # ou 0.5
```

**Poucos objetos detectados:**
```bash
# Reduzir threshold
--conf 0.15  # ou 0.2
```

### Se Resultados Não Forem Bons

1. **Anotar mais imagens** (especialmente das classes problemáticas)
2. **Treinar mais épocas** (--epochs 150 ou 200)
3. **Usar modelo maior** (--model yolo11s.pt ou yolo11m.pt)
4. **Ajustar augmentation** no Roboflow
5. **Verificar qualidade das anotações**

**Próxima etapa:** [Integração no Sistema](#etapa-6-integracao)

---

## 🔌 Etapa 6: Integração no Sistema {#etapa-6-integracao}

### Objetivo

Substituir modelo padrão pelo modelo treinado customizado no sistema de contagem.

### Passos

#### 1. Copiar Modelo Treinado

```bash
# Copiar best.pt para diretório raiz
cp ./runs/train/custom_model/weights/best.pt ./modelo_customizado.pt

# Ou usar nome descritivo
cp ./runs/train/custom_model/weights/best.pt ./yolo11_custom_motos_v1.pt
```

#### 2. Atualizar config.json

Edite `config.json`:

```json
{
  "modelo_yolo": "modelo_customizado.pt",
  "confianca_minima": 0.35,
  "categorias": [
    "car",
    "motorcycle",
    "truck",
    "bus",
    "bicycle"
  ],
  ...
}
```

**Ajustes recomendados:**
- `modelo_yolo`: Nome do seu modelo customizado
- `confianca_minima`: Reduzir para ~0.35-0.40 (modelo customizado é mais confiável)

#### 3. Reiniciar Sistema

```bash
# Se estiver rodando
pkill -f main.py

# Iniciar novamente
python main.py
```

#### 4. Verificar Logs

Verifique se modelo foi carregado:

```
📦 Carregando modelo YOLO: modelo_customizado.pt
✅ Modelo carregado com sucesso
   Classes: ['car', 'motorcycle', 'truck', 'bus', 'bicycle']
```

#### 5. Testar Detecções

Observe a interface e verifique:

- ✅ Motos sendo detectadas com confiança > 0.35
- ✅ Caminhões sendo reconhecidos corretamente
- ✅ Contagem precisa
- ❌ Sem falsos positivos excessivos

### Comparação de Performance

Antes e depois com modelo customizado:

| Métrica | Modelo Original | Modelo Customizado | Melhoria |
|---------|----------------|-------------------|----------|
| **Motos detectadas** | 45% | 92% | +47% 🎯 |
| **Carros detectados** | 89% | 94% | +5% ✅ |
| **Caminhões detectados** | 62% | 88% | +26% 🎯 |
| **Falsos positivos** | 8% | 3% | -5% ✅ |
| **FPS** | 28 | 26 | -2 (ok) |

### Versionamento

Mantenha versões diferentes:

```bash
# Backup do modelo original
cp yolo11n.pt yolo11n_original.pt

# Versões do modelo customizado
modelo_customizado_v1.pt  # Primeira versão
modelo_customizado_v2.pt  # Após retreinamento com mais dados
```

### Rollback (Se Necessário)

Se modelo customizado não melhorar:

```json
{
  "modelo_yolo": "yolo11n.pt"
}
```

---

## 🔧 Troubleshooting {#troubleshooting}

### Problemas Comuns

#### 1. Erro: CUDA Out of Memory

**Sintoma:**
```
RuntimeError: CUDA out of memory
```

**Solução:**
```bash
# Reduzir batch size
--batch 8  # ou --batch 4

# Ou usar modelo menor
--model yolo11n.pt  # ao invés de yolo11m.pt

# Ou reduzir tamanho da imagem
--img 480  # ao invés de 640
```

#### 2. Treinamento Muito Lento (CPU)

**Sintoma:** 10+ minutos por época

**Solução:**
- ✅ Usar GPU (melhor opção)
- ✅ Reduzir épocas (--epochs 30)
- ✅ Usar menos imagens (300 ao invés de 1000)
- ✅ Usar modelo menor (yolo11n.pt)

#### 3. Dataset Vazio / Nenhuma Imagem

**Sintoma:**
```
❌ Nenhuma imagem encontrada em: ./dataset/images
```

**Solução:**
- Verificar path correto
- Verificar extensões (.jpg, .png)
- Re-executar captura de frames

#### 4. Labels Faltando

**Sintoma:**
```
⚠️  Imagens sem label correspondente: 150
```

**Solução:**
- Completar anotação de todas as imagens
- Ou remover imagens não anotadas

#### 5. Modelo Não Melhora (Overfitting)

**Sintoma:** Train loss baixa, Val loss alta

**Soluções:**
1. **Mais dados de validação**
2. **Augmentation mais agressiva** (Roboflow)
3. **Early stopping** (--patience 30)
4. **Regularização:** Modelo menor (yolo11n ao invés de yolo11m)

#### 6. Detecções Ruins Após Treinamento

**Possíveis causas:**
- ❌ Poucas imagens (<100 por classe)
- ❌ Anotações de baixa qualidade
- ❌ Falta de variedade no dataset
- ❌ Treinamento interrompido cedo

**Soluções:**
1. **Anotar mais imagens** (foco nas classes problemáticas)
2. **Revisar qualidade das anotações**
3. **Treinar por mais épocas**
4. **Usar modelo maior** (yolo11s.pt)

---

## ❓ FAQ {#faq}

### Quantas imagens preciso anotar?

**Mínimo:** 100 por classe (500 total)
**Recomendado:** 300 por classe (1500 total)
**Ideal:** 500+ por classe (2500+ total)

Comece com 100-200, treine, teste, e anote mais se necessário.

---

### Quanto tempo leva todo o processo?

| Etapa | Tempo |
|-------|-------|
| Captura | 1-2 horas |
| Anotação | 8-30 horas |
| Preparação | 5 minutos |
| Treinamento | 2-6 horas (GPU) |
| Validação | 30 minutos |
| Integração | 5 minutos |
| **TOTAL** | **~12-40 horas** |

A maior parte do tempo é na anotação.

---

### Posso usar dataset público?

**Sim**, mas com ressalvas:

- ✅ **COCO:** Dataset geral (yolo já treinado nele)
- ✅ **BDD100K:** Dataset de dashcam (similar ao seu uso)
- ✅ **UA-DETRAC:** Dataset de tráfego urbano

**MAS:** Melhor combinar dataset público + suas imagens:
- 70% imagens suas (específicas)
- 30% dataset público (variedade)

---

### Como melhorar detecção de motos especificamente?

1. **Anotar MUITAS motos** (500+ exemplos)
2. **Variedade:**
   - Diferentes ângulos
   - Diferentes distâncias
   - Com/sem capacete
   - Com/sem garupa
   - Diferentes modelos
3. **Class weights:** Dar mais peso à classe moto
4. **Focal loss:** Para classes desbalanceadas

---

### Vale a pena treinar modelo customizado?

**Sim, se:**
- ✅ Modelo atual tem <70% de precisão
- ✅ Classes específicas não são detectadas (motos)
- ✅ Você tem tempo para anotar (8-20 horas)
- ✅ Você tem GPU disponível

**Não necessariamente, se:**
- ❌ Modelo atual já tem >90% de precisão
- ❌ Problema é na contagem (não na detecção)
- ❌ Não tem GPU (CPU é muito lento)

---

### Posso treinar sem GPU?

**Tecnicamente sim**, mas:
- ⚠️ Muito mais lento (dias vs horas)
- ⚠️ Recomendado apenas para testes pequenos

**Alternativas:**
- ✅ **Google Colab:** GPU gratuita (T4)
- ✅ **Kaggle:** GPU gratuita (P100)
- ✅ **Vast.ai:** GPU alugada ($0.10-0.50/hora)
- ✅ **Lambda Labs:** GPU cloud

---

### Qual modelo base escolher?

| Seu Hardware | Modelo Recomendado |
|--------------|-------------------|
| CPU ou GPU <4GB | `yolo11n.pt` |
| GPU 4-8GB | `yolo11s.pt` ⭐ |
| GPU 8-12GB | `yolo11m.pt` |
| GPU 12GB+ | `yolo11l.pt` |

**Padrão:** Comece com `yolo11n.pt` para teste, depois `yolo11s.pt` para produção.

---

### Como saber se treinamento foi bom?

**Métricas alvo:**

| Métrica | Valor Bom | Valor Excelente |
|---------|-----------|-----------------|
| mAP50 | > 0.7 | > 0.85 |
| mAP50-95 | > 0.5 | > 0.7 |
| Precision | > 0.8 | > 0.9 |
| Recall | > 0.75 | > 0.85 |

**Teste real:** Execute no seu sistema e verifique visualmente!

---

### Preciso retreinar periodicamente?

**Apenas se:**
- Cenário mudar (nova câmera, novo ângulo)
- Novos tipos de veículos aparecerem
- Precisão cair com tempo

**Não necessário** se tudo estiver funcionando bem.

---

## 📚 Recursos Adicionais

### Documentação
- **YOLOv11:** https://docs.ultralytics.com
- **Roboflow:** https://docs.roboflow.com
- **PyTorch:** https://pytorch.org/docs

### Tutoriais
- **YOLO Train Custom:** https://docs.ultralytics.com/modes/train/
- **Data Augmentation:** https://blog.roboflow.com/yolo-data-augmentation/

### Datasets Públicos
- **COCO:** https://cocodataset.org
- **BDD100K:** https://www.bdd100k.com
- **UA-DETRAC:** https://detrac-db.rit.albany.edu

### Ferramentas
- **Roboflow:** https://roboflow.com
- **labelImg:** https://github.com/HumanSignal/labelImg
- **CVAT:** https://www.cvat.ai

---

## 🎉 Conclusão

Você agora tem um **guia completo** para treinar um modelo YOLOv11 customizado!

**Recap do processo:**
1. ✅ Capturar frames do RTSP
2. ✅ Anotar imagens (Roboflow/labelImg)
3. ✅ Preparar dataset
4. ✅ Treinar modelo customizado
5. ✅ Validar qualidade
6. ✅ Integrar no sistema

**Próximos passos:**
1. Começar com **100-200 imagens** (teste)
2. Treinar primeira versão
3. Validar resultados
4. **Iterar:** Anotar mais onde modelo falha
5. Retreinar e melhorar

**Boa sorte com o treinamento! 🚀**

Se tiver dúvidas, consulte:
- Este guia
- [GUIA_ANOTACAO_DATASET.md](./GUIA_ANOTACAO_DATASET.md)
- Documentação oficial do YOLO
