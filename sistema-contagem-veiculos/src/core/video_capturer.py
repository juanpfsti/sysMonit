



#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wrapper para captura de vídeo que integra RTSPBufferedCapture com QObject/Signals
"""

import logging
from PyQt5.QtCore import QObject, pyqtSignal
from src.capture.rtsp_capture import RTSPBufferedCapture

class VideoCapturer(QObject):
    """
    Wrapper que adapta RTSPBufferedCapture para uso com Qt Signals
    e interface esperada pelo VideoThread.
    """
    log_message = pyqtSignal(str)
    update_status = pyqtSignal(str)

    def __init__(self, config, rtsp_url):
        super().__init__()
        self.config = config
        self.rtsp_url = rtsp_url
        self.capture = None
        
    def start(self):
        """Inicia a captura"""
        try:
            self.log_message.emit(f"Iniciando conexão RTSP: {self.rtsp_url}")
            
            # Callback para logs do capturador
            def log_callback(msg):
                self.log_message.emit(msg)

            self.capture = RTSPBufferedCapture(
                self.rtsp_url, 
                buffer_size=2,
                log_callback=log_callback
            )
            
            if self.capture.isOpened():
                self.update_status.emit("Online")
                return True
            else:
                self.update_status.emit("Erro Conexão")
                return False
                
        except Exception as e:
            self.log_message.emit(f"Erro fatal ao iniciar captura: {e}")
            self.update_status.emit("Erro Fatal")
            return False

    def stop(self):
        """ Para a captura de forma segura"""
        try:
            if self.capture:
                self.capture.release()
        except Exception as e:
            logging.warning(f"Erro ao liberar captura: {e}")
        finally:
            self.capture = None
        
        try:
            self.update_status.emit("Parado")
        except Exception as e:
            logging.warning(f"Erro ao emitir sinal: {e}")

    def read(self):
        """Lê um frame"""
        if not self.capture:
            return False, None
        return self.capture.read()

    def check_health(self):
        """Verifica saúde da conexão (RTSPBufferedCapture gerencia internamente)"""
        if not self.capture:
            return False
        return self.capture.isOpened()
