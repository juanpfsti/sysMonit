#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SistemaMonitoramento em Tempo Real via RTSP
(YOLO + ByteTrack/BoT-SORT + Linha/Áreas Configuráveis + Sistema de Fila)

Autor: Felipe, João Vitor, Juan, Pablo, Ramon e Willians
Versão: 2.5.1
Data: 24/02/2026
"""

# ==============================================================================
# BLOCO 0: IMPORTS DO SISTEMA (ANTES DE TUDO)
# ==============================================================================
import sys
import os
import faulthandler # CRÍTICO: Para debug de crashes (Exit code -1073740771)

# Ativar faulthandler imediatamente (com tratamento para PyInstaller)
try:
    if sys.stderr is not None:
        faulthandler.enable()
except (AttributeError, ValueError, RuntimeError):
    # PyInstaller ou ambiente sem stderr pode causar erro
    pass

# ==============================================================================
# BLOCO 1: DETECÇÃO E CONFIGURAÇÃO DE PLATAFORMA
# ==============================================================================
import platform
IS_WINDOWS = platform.system() == 'Windows'

# ==============================================================================
# BLOCO 2: CONFIGURAÇÕES CRÍTICAS DO WINDOWS (ANTES DE QUALQUER OUTRO IMPORT)
# ==============================================================================
if IS_WINDOWS:
    # CRÍTICO 1: Threading COM (DEVE ser 2 para GUI)
    try:
        sys.coinit_flags = 2
    except:
        pass
    
    # CRÍTICO 2: Desabilitar DPI Awareness (evita crash em drivers antigos)
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(0)
    except:
        pass
    
    # CRÍTICO 3: Error Mode (suprimir popups de erro do Windows)
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetErrorMode(0x8007)  # Todos os error modes
    except:
        pass

# ==============================================================================
# BLOCO 3: VARIÁVEIS DE AMBIENTE (ANTES DE cv2 e PyQt5)
# ==============================================================================
# Forçar renderização via software
os.environ['QT_OPENGL'] = 'software'
os.environ['QT_ANGLE_PLATFORM'] = 'warp'
os.environ['QMLSCENE_DEVICE'] = 'softwarecontext'
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

# Logs OpenCV
os.environ['OPENCV_LOG_LEVEL'] = 'SILENT'
os.environ['OPENCV_VIDEOIO_DEBUG'] = '0'
os.environ['OPENCV_VIDEOIO_PRIORITY_MSMF'] = '0'
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Desabilitar multithreading do OpenCV/NumPy
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'

# ==============================================================================
# BLOCO 4: IMPORTS NA ORDEM CORRETA
# ==============================================================================

print("Carregando bibliotecas...")

# PASSO 1: OpenCV SEMPRE PRIMEIRO
try:
    import cv2
    CV2_OK = True
    # CRÍTICO: Desabilitar threads internas do OpenCV para evitar conflito com Qt
    cv2.setNumThreads(0)
except ImportError:
    CV2_OK = False
    print("ERRO: OpenCV não instalado!")
    sys.exit(1)

# PASSO 2: PyTorch (com tratamento especial para PyInstaller)
try:
    # Proteger import de PyTorch em ambientes com problema de DLL
    try:
        import torch
        TORCH_OK = True
    except (ImportError, OSError, RuntimeError) as e:
        # OSError: Erro de DLL do PyTorch
        # RuntimeError: Erro de inicialização do PyTorch
        print(f"⚠️  Aviso: PyTorch não disponível ({type(e).__name__})")
        print(f"   O programa pode funcionar de forma limitada")
        TORCH_OK = False
except Exception as e:
    print(f"⚠️  Erro ao carregar PyTorch: {e}")
    TORCH_OK = False

# PASSO 3: NumPy
try:
    import numpy as np
    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False

# PASSO 4: Outras libs Python padrão
import logging
import threading
import argparse

# PASSO 5: PyQt5 POR ÚLTIMO
try:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR, Qt
    PYQT_OK = True
except ImportError:
    PYQT_OK = False
    print("ERRO: PyQt5 não instalado!")
    sys.exit(1)

# ==============================================================================
# LOGGING
# ==============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sistema_monitoramento.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ==============================================================================
# FUNÇÃO PRINCIPAL
# ==============================================================================

def main():
    print()
    print("=" * 70)
    print("  SISTEMA MONITORAMENTO v2.5.1")
    print("  Sistema de Fila | Análises | Export Excel | Detecção Configurável | Monitoramento")
    print("=" * 70)
    print()
    
    # Criar QApplication com configurações seguras
    try:
        print("Inicializando interface gráfica...")
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        
        if IS_WINDOWS:
            app.setAttribute(Qt.AA_DisableHighDpiScaling, True)
        
        print("✓ Interface gráfica iniciada")
        
    except Exception as e:
        print(f"ERRO FATAL: {e}")
        sys.exit(1)
    
    # Iniciar janela principal
    try:
        logging.info("Carregando interface principal...")
        from src.ui import MainWindow
        
        win = MainWindow()
        win.show()
        
        logging.info("Sistema iniciado com sucesso!")
        sys.exit(app.exec_())
        
    except Exception as e:
        logging.critical(f"Erro fatal ao iniciar: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Erro não tratado: {e}")
        sys.exit(1)
