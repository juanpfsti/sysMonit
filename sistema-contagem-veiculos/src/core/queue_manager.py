#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerenciador de Fila e Métricas de Espera

Algoritmo de detecção:
- Usa cv2.pointPolygonTest() com o ponto base (bottom-center) da bounding box
- Robustez via debounce: ENTER_FRAMES frames dentro → entra na fila
                         EXIT_FRAMES frames fora  → sai da fila
- Entry/exit lines são mantidas como marcadores opcionais no preview
"""

import cv2
import time
import numpy as np
from collections import deque
from datetime import datetime

# Quantos frames consecutivos dentro/fora para mudança de estado
ENTER_FRAMES = 3   # ~0.1s @ 30fps — evita contar passagens rápidas
EXIT_FRAMES  = 12  # ~0.4s @ 30fps — tolerância a oclusão momentânea


class QueueManager:
    """
    Gerencia a lógica de detecção de fila, rastreamento de tempo de espera
    e estatísticas associadas.
    """
    def __init__(self, config, database=None, rtsp_url=''):
        self.config = config
        self.database = database
        self.rtsp_url = rtsp_url

        # Estado atual: {track_id: VehicleState}
        self.waiting_vehicles = {}
        self.completed_waits = deque(maxlen=200)
        self.session_history = []

        # Estatísticas
        self.current_queue_size = 0
        self.max_wait_current = 0
        self.status = "Normal"

        # Cache de geometria desnormalizada
        self._geo_cache = {}

    # ------------------------------------------------------------------
    # Geometria
    # ------------------------------------------------------------------
    def _get_geo(self, width, height):
        """Retorna geometrias desnormalizadas (em pixels), com cache."""
        q_cfg = self.config.get('queue_config', {})
        cfg_hash = str(q_cfg) + f"{width}x{height}"
        if self._geo_cache.get('hash') == cfg_hash:
            return self._geo_cache['data']

        # Polígono padrão: trapézio simples cobrindo a metade inferior
        def_poly = [[0.15, 0.55], [0.85, 0.55], [0.85, 0.95], [0.15, 0.95]]

        raw_poly = q_cfg.get('polygon', def_poly)
        polygon = np.array(raw_poly, np.float32).reshape(-1, 2)
        polygon[:, 0] *= width
        polygon[:, 1] *= height
        polygon = polygon.astype(np.int32)

        # Linhas de entrada/saída (opcionais — só para exibição)
        def scale_line(key, default):
            pts = np.array(q_cfg.get(key, default), np.float32).reshape(-1, 2)
            pts[:, 0] *= width
            pts[:, 1] *= height
            return pts.astype(np.int32)

        data = {
            'poly':  polygon,
            'entry': scale_line('entry_line', [[0.15, 0.55], [0.85, 0.55]]) if q_cfg.get('entry_line') else None,
            'exit':  scale_line('exit_line',  [[0.15, 0.95], [0.85, 0.95]]) if q_cfg.get('exit_line')  else None,
        }
        self._geo_cache = {'hash': cfg_hash, 'data': data}
        return data

    # ------------------------------------------------------------------
    # Update principal
    # ------------------------------------------------------------------
    def update(self, tracks, frame_shape):
        h, w = frame_shape[:2]
        geo = self._get_geo(w, h)
        poly = geo['poly']          # np.int32 shape (N, 2)
        current_time = time.time()

        has_polygon = len(poly) >= 3

        active_ids = set()

        for track in tracks:
            track_id = track['id']
            box = track['box']          # [x1, y1, x2, y2]
            x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])

            # Ponto de referência: base central da bounding box (toca o chão)
            foot = (int((x1 + x2) / 2), y2)
            active_ids.add(track_id)

            # Inicializar estado
            if track_id not in self.waiting_vehicles:
                self.waiting_vehicles[track_id] = {
                    'state':          'IDLE',
                    'entry_time':     0,
                    'current_wait':   0,
                    'last_pos':       foot,
                    'history':        deque(maxlen=60),
                    'class':          track.get('label', '?'),
                    'frames_inside':  0,
                    'frames_outside': 0,
                }

            vehicle = self.waiting_vehicles[track_id]
            vehicle['last_pos'] = foot
            vehicle['history'].append(foot)

            # ---- Point-in-Polygon ----
            if has_polygon:
                inside = cv2.pointPolygonTest(
                    poly, (float(foot[0]), float(foot[1])), False
                ) >= 0
            else:
                inside = False

            # ---- Máquina de Estados ----
            if vehicle['state'] == 'IDLE':
                if inside:
                    vehicle['frames_inside'] += 1
                    vehicle['frames_outside'] = 0
                    if vehicle['frames_inside'] >= ENTER_FRAMES:
                        vehicle['state'] = 'IN_QUEUE'
                        vehicle['entry_time'] = current_time
                        vehicle['frames_inside'] = 0
                else:
                    vehicle['frames_inside'] = 0

            elif vehicle['state'] == 'IN_QUEUE':
                vehicle['current_wait'] = current_time - vehicle['entry_time']

                if not inside:
                    vehicle['frames_outside'] += 1
                    vehicle['frames_inside'] = 0
                    if vehicle['frames_outside'] >= EXIT_FRAMES:
                        self._finalize_vehicle(vehicle, track_id, current_time)
                else:
                    vehicle['frames_outside'] = 0
                    vehicle['frames_inside'] += 1

            # Injetar dados no track para renderização (usado pelo SceneDrawer via draw_tracks)
            if vehicle['state'] == 'IN_QUEUE':
                track['queue_info'] = {
                    'wait_time':  vehicle['current_wait'],
                    'is_waiting': True,
                }

        # Cleanup: remover veículos ausentes e finalizados
        gone = [tid for tid in self.waiting_vehicles if tid not in active_ids]
        for tid in gone:
            v = self.waiting_vehicles[tid]
            # Se estava na fila ao desaparecer, registrar como saída
            if v['state'] == 'IN_QUEUE':
                self._finalize_vehicle(v, tid, current_time)
            del self.waiting_vehicles[tid]

        finished = [tid for tid, v in self.waiting_vehicles.items() if v['state'] == 'FINISHED']
        for tid in finished:
            del self.waiting_vehicles[tid]

        # ---- Métricas ----
        in_queue = [v for v in self.waiting_vehicles.values() if v['state'] == 'IN_QUEUE']
        self.current_queue_size = len(in_queue)
        self.max_wait_current = max((v['current_wait'] for v in in_queue), default=0)

        threshold = self.config.get('queue_config', {}).get('threshold_seconds', 60)
        if self.max_wait_current > threshold:
            self.status = "Critico"
        elif self.max_wait_current > threshold * 0.5:
            self.status = "Atencao"
        else:
            self.status = "Normal"

    def _finalize_vehicle(self, vehicle, track_id, current_time):
        """Registra saída de fila e move para histórico."""
        wait_time = vehicle.get('current_wait', 0)
        if wait_time < self.config.get('queue_config', {}).get('min_wait_time', 2.0):
            vehicle['state'] = 'FINISHED'
            return  # Descarta esperas muito curtas (provavelmente falso positivo)

        entry_time_str = datetime.fromtimestamp(vehicle['entry_time']).strftime('%Y-%m-%d %H:%M:%S')
        exit_time_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        vehicle_class = vehicle.get('class', '?')
        wait_rounded = round(wait_time, 2)

        self.completed_waits.append((wait_time, current_time))
        self.session_history.append({
            'track_id':          track_id,
            'entry_time':        entry_time_str,
            'exit_time':         exit_time_str,
            'wait_duration_sec': wait_rounded,
            'vehicle_class':     vehicle_class,
        })

        # Persistir no QueueDatabase de forma assíncrona (não bloqueia o loop de vídeo)
        if self.database is not None:
            try:
                self.database.save_event(
                    track_id=track_id,
                    entry_time=entry_time_str,
                    exit_time=exit_time_str,
                    wait_duration_sec=wait_rounded,
                    vehicle_class=vehicle_class,
                    rtsp_url=self.rtsp_url,
                )
            except Exception as e:
                import logging
                logging.error(f"QueueManager: erro ao enfileirar evento: {e}")

        vehicle['state'] = 'FINISHED'

    # ------------------------------------------------------------------
    # Dados para renderização
    # ------------------------------------------------------------------
    def get_render_data(self):
        """Retorna dados para o SceneDrawer."""
        if not self._geo_cache:
            return {}

        return {
            'polygon':    self._geo_cache['data']['poly'],
            'entry_line': self._geo_cache['data'].get('entry'),
            'exit_line':  self._geo_cache['data'].get('exit'),
            'status':     self.status,
            'vehicles':   self.waiting_vehicles,
        }

    def get_stats(self):
        """Retorna estatísticas atuais para o dashboard."""
        current_time = time.time()
        recent_waits = [w for w, t in self.completed_waits if current_time - t <= 300]
        avg_wait = float(np.mean(recent_waits)) if recent_waits else 0.0
        max_wait_session = max((w for w, _ in self.completed_waits), default=0)

        return {
            'waiting_count':     self.current_queue_size,
            'avg_wait_5min':     avg_wait,
            'max_wait_session':  max(max_wait_session, self.max_wait_current),
            'status':            self.status,
            'max_wait_current':  self.max_wait_current,
        }
