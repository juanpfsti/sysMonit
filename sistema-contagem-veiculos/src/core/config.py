#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerenciador de configurações do sistema
"""

import json
import logging
from pathlib import Path


class Config:
    """Gerencia configurações do sistema via JSON"""

    def __init__(self):
        self.config_file = 'config.json'
        self.default_config = {
            'rtsp_url': 'rtsp://usuario:senha@ip:porta/caminho',
            'rtsp_url_queue': '',
            'intervalo_relatorio': 15,
            'confianca_minima': 0.5,
            'categorias': ['car', 'motorcycle', 'moto', 'truck', 'bus'],
            'modelo_yolo': 'yolo11n.pt',  # YOLOv11 Nano (recomendado)
            'queue_modelo_yolo': 'yolo11n.pt',  # Modelo para a câmera de fila
            'tracker': 'bytetrack.yaml',

            'counting_mode': 'line',
            'line_config': {
                'x1_ratio': 0.10,
                'x2_ratio': 0.90,
                'y_ratio':  0.55,
                'band_px':  2,
                'invert_direction': False,
                'direction_mode':   'both',   # 'both' | 'ida_only' | 'volta_only'
            },
            'zones_config': {
                'down': [0.10, 0.60, 0.90, 0.95],
                'up':   [0.10, 0.05, 0.90, 0.40]
            },
            'zones_direction': {'down': 'ida', 'up': 'volta'},
            'zone_event_cooldown': 0.8,

            'use_roi_crop': False,
            'roi_crop': {
                'top_percent': 0,
                'bottom_percent': 0,
                'left_percent': 0,
                'right_percent': 0
            },

            # Configurações RTSP para decodificação robusta
            'rtsp_buffer_size': 10,
            'rtsp_enable_frame_validation': False,
            'rtsp_skip_corrupted_frames': False,

            'show_labels': False,
            'show_zone_tags': True,

            # Configurações de Fila
            'queue_config': {
                'enabled': True,
                'threshold_seconds': 60,  # Tempo para considerar fila crítica
                'show_timers': True,      # Mostrar timers individuais
                'show_trail': True,       # Mostrar rastro de movimento
                'min_wait_time': 5.0,     # Tempo mínimo para começar a contar como espera
                'polygon': []             # Pontos do polígono [(x,y), ...] normalizados 0-1
            }
        }
        self.load()

    def load(self):
        """CORRIGIDO: Carrega configurações com backup e recovery"""
        config_path = Path(self.config_file)
        backup_path = Path(f"{self.config_file}.backup")

        try:
            if config_path.exists():
                # Ler arquivo
                with open(config_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                try:
                    # Tentar parsear JSON
                    self.config = json.loads(content)

                    # Validar estrutura básica
                    if not isinstance(self.config, dict):
                        raise ValueError("Config deve ser um dicionário")

                    # Limpar RTSP URL
                    if 'rtsp_url' in self.config and isinstance(self.config['rtsp_url'], str):
                        self.config['rtsp_url'] = self.config['rtsp_url'].strip()

                    # Migra modelos antigos para YOLOv11
                    old_models = {
                        'yolov9s.pt': 'yolo11n.pt',
                        'yolov9c.pt': 'yolo11s.pt',
                        'yolov9e.pt': 'yolo11m.pt'
                    }
                    if self.config.get('modelo_yolo') in old_models:
                        old = self.config['modelo_yolo']
                        new = old_models[old]
                        logging.info(f"Migrando modelo {old} → {new}")
                        self.config['modelo_yolo'] = new
                        self.save()

                    logging.info("Configurações carregadas com sucesso")

                    # FAZER BACKUP da config válida
                    self._save_backup()

                except json.JSONDecodeError as e:
                    logging.error(f"❌ Config JSON inválido: {e}")

                    # TENTAR CARREGAR BACKUP
                    if backup_path.exists():
                        logging.info("Tentando carregar backup...")
                        if self._load_from_backup():
                            logging.info("✅ Backup carregado com sucesso")
                            # Salvar backup como config atual
                            self.save()
                            return

                    # SEM BACKUP VÁLIDO - usar config padrão
                    logging.warning("⚠️ Usando configurações padrão")
                    self.config = self.default_config.copy()
                    self.save()

            else:
                # Arquivo não existe - criar com padrões
                logging.info("Config não encontrada, criando com padrões")
                self.config = self.default_config.copy()
                self.save()

        except Exception as e:
            logging.error(f"❌ Erro ao carregar config: {e}")
            self.config = self.default_config.copy()

    def _save_backup(self):
        """Salva backup da configuração atual"""
        try:
            backup_path = Path(f"{self.config_file}.backup")
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logging.debug("Backup de config salvo")
        except Exception as e:
            logging.warning(f"Falha ao salvar backup: {e}")

    def _load_from_backup(self):
        """Tenta carregar configuração do backup"""
        try:
            backup_path = Path(f"{self.config_file}.backup")
            with open(backup_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            # Validar estrutura
            if not isinstance(self.config, dict):
                return False

            return True
        except Exception as e:
            logging.error(f"Falha ao carregar backup: {e}")
            return False

    def save(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logging.info("Configurações salvas")
        except Exception as e:
            logging.error(f"Erro ao salvar config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, self.default_config.get(key, default))

    def set(self, key, value):
        self.config[key] = value
        self.save()
