#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de detecção de objetos usando YOLO
OTIMIZAÇÕES: GPU, Float16, Warmup, Cache
"""

import logging
import torch
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal
from ultralytics import YOLO

class ObjectDetector(QObject):
    """
    Classe responsável pela detecção e rastreamento de objetos usando YOLO.
    OTIMIZAÇÕES:
    - GPU enabled (CUDA/CPU automático)
    - Warmup do modelo no carregamento
    - Float16 (half precision) para acelerar inferência
    - Cache de modelo em memória
    """
    log_message = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.model = None
        self.names = {}
        self.device = None
        self.use_half = False

    def _get_device(self):
        """Detecta melhor device disponível (GPU > CPU)"""
        if torch.cuda.is_available():
            device = 'cuda:0'
            gpu_name = torch.cuda.get_device_name(0)
            self.log_message.emit(f"[GPU] NVIDIA {gpu_name} detectada - aceleração ativada")
        else:
            device = 'cpu'
            self.log_message.emit("[CPU] GPU nao disponivel - usando CPU")
        return device

    def load_model(self):
        """Carrega o modelo YOLO com otimizações"""
        try:
            model_path = self.config.get('modelo_yolo', 'yolo11n.pt')
            self.log_message.emit(f"Carregando modelo: {model_path}")
            
            # OTIMIZAÇÃO 1: Detectar device (GPU/CPU)
            self.device = self._get_device()
            
            # OTIMIZAÇÃO 2: Carregar modelo com device
            self.model = YOLO(model_path)
            self.model.to(self.device)
            
            # OTIMIZAÇÃO 3: Usar half precision (float16) se GPU disponível
            if 'cuda' in str(self.device) and torch.cuda.is_available():
                self.use_half = True
                self.log_message.emit("[HALF] Float16 ativado para aceleracao GPU")
            else:
                self.use_half = False
            
            self.names = self.model.names
            
            # OTIMIZAÇÃO 4: Warmup do modelo (primeiro frame mais rápido)
            self.log_message.emit("[WARMUP] Aquecendo modelo...")
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            _ = self.model.predict(dummy_frame, verbose=False, conf=0.1)
            self.log_message.emit("[OK] Modelo carregado e pronto para inferencia")
            
            return True
        except Exception as e:
            self.log_message.emit(f"[ERRO] Falha ao carregar modelo: {e}")
            return False

    def track(self, frame):
        """Realiza o tracking no frame com otimizações"""
        if self.model is None:
            return None
        
        try:
            # Configurações de inferência
            conf = float(self.config.get('confidence', 0.3))
            iou = float(self.config.get('iou', 0.5))
            
            # OTIMIZAÇÃO: Usar half precision em GPU
            results = self.model.track(
                frame, 
                persist=True,
                conf=conf,
                iou=iou,
                verbose=False,
                tracker="bytetrack.yaml",
                device=self.device,
                half=self.use_half
            )
            return results
        except Exception as e:
            self.log_message.emit(f"[ERRO] Falha na inferencia: {e}")
            return None
