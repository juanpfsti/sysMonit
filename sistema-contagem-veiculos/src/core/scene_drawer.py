#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo responsável por desenhar elementos na cena (linhas, zonas, caixas, fila)
"""

import cv2
import numpy as np

class SceneDrawer:
    """
    Classe utilitária para desenhar overlays no frame de vídeo.
    """
    def __init__(self, config):
        self.config = config

    def draw_overlays(self, frame):
        """Desenha linhas de contagem e zonas de interesse (Layout Original)"""
        # Verificar se deve ocultar linhas de detecção
        hide_lines = bool(self.config.get('hide_detection_lines', False))
        if hide_lines:
            return  # Não desenhar nada se a opção estiver marcada

        h, w = frame.shape[:2]

        # Desenhar Linha
        if self.config.get('counting_mode') == 'line':
            lc = self.config.get('line_config', {})
            if not lc: return

            x1    = int(w * lc.get('x1_ratio',  0.10))
            x2    = int(w * lc.get('x2_ratio',  0.90))
            y     = int(h * lc.get('y_ratio',   0.55))
            invert = bool(lc.get('invert_direction', False))
            dmode  = lc.get('direction_mode', 'both')

            x_mid_ratio = lc.get('x_mid_ratio')
            if x_mid_ratio is not None:
                x_mid = int(w * x_mid_ratio)

                # cores BGR
                ida_bgr   = (80, 220, 80)
                volta_bgr = (80, 80, 220)
                left_color  = volta_bgr if invert else ida_bgr
                right_color = ida_bgr   if invert else volta_bgr
                left_label  = "VOLTA" if invert else "IDA"
                right_label = "IDA"   if invert else "VOLTA"

                if invert:
                    show_left  = dmode != 'ida_only'
                    show_right = dmode != 'volta_only'
                else:
                    show_left  = dmode != 'volta_only'
                    show_right = dmode != 'ida_only'

                dim = (120, 120, 120)
                lc_draw = left_color  if show_left  else dim
                rc_draw = right_color if show_right else dim

                cv2.line(frame, (x1, y), (x_mid, y), lc_draw, 2)
                cv2.line(frame, (x_mid, y), (x2, y), rc_draw, 2)
                cv2.circle(frame, (x1, y),    4, lc_draw, -1)
                cv2.circle(frame, (x_mid, y), 5, (255, 180, 0), -1)  # handle M laranja
                cv2.circle(frame, (x2, y),    4, rc_draw, -1)

                font = cv2.FONT_HERSHEY_SIMPLEX
                if show_left and x_mid > x1:
                    lx = (x1 + x_mid) // 2
                    cv2.putText(frame, left_label,  (lx - 20, y - 8), font, 0.55, left_color,  2)
                if show_right and x2 > x_mid:
                    rx = (x_mid + x2) // 2
                    cv2.putText(frame, right_label, (rx - 26, y - 8), font, 0.55, right_color, 2)
            else:
                # Sem divisão por faixa: linha única ciano
                cv2.line(frame, (x1, y), (x2, y), (0, 255, 255), 2)
                cv2.circle(frame, (x1, y), 4, (0, 255, 255), -1)
                cv2.circle(frame, (x2, y), 4, (0, 255, 255), -1)

        # Desenhar Zonas
        elif self.config.get('counting_mode') == 'zone':
            zc = self.config.get('zones_config', {})
            if not zc: return

            # Zona Down (Ida)
            if 'down' in zc:
                r = zc['down']
                x1, y1 = int(r[0]*w), int(r[1]*h)
                x2, y2 = int(r[2]*w), int(r[3]*h)

                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), -1)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # Zona Up (Volta)
            if 'up' in zc:
                r = zc['up']
                x1, y1 = int(r[0]*w), int(r[1]*h)
                x2, y2 = int(r[2]*w), int(r[3]*h)

                overlay = frame.copy()
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)

    def draw_queue_overlays(self, frame, render_data):
        """
        Desenha elementos da fila: Polígono (fill dinâmico), Linhas de Entrada/Saída,
        Timers individuais e Rastros de movimento.

        Args:
            frame: Imagem BGR (modificada in-place)
            render_data: dict retornado por QueueManager.get_render_data()
        """
        if not render_data:
            return

        polygon   = render_data.get('polygon')
        entry_line = render_data.get('entry_line')
        exit_line  = render_data.get('exit_line')
        status    = render_data.get('status', 'Normal')
        vehicles  = render_data.get('vehicles', {})

        q_cfg = self.config.get('queue_config', {})
        show_timers = q_cfg.get('show_timers', True)
        show_trail  = q_cfg.get('show_trail', True)
        threshold   = q_cfg.get('threshold_seconds', 60)

        # ── Cor dinâmica baseada no status ──────────────────────────────
        if status == 'Critico':
            border_color = (0, 0, 255)       # Vermelho
            fill_bgr     = (0, 0, 220)
        elif status == 'Atencao':
            border_color = (0, 140, 255)     # Laranja
            fill_bgr     = (0, 120, 200)
        else:
            border_color = (0, 200, 80)      # Verde
            fill_bgr     = (0, 180, 60)

        # Respeita toggle "Mostrar Zonas" da UI
        show_zones = self.config.get('show_zone_tags', True)

        # ── 1. Polígono com fill semitransparente ────────────────────────
        if show_zones and polygon is not None and len(polygon) >= 3:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [polygon], fill_bgr)
            cv2.addWeighted(overlay, 0.20, frame, 0.80, 0, frame)

            # Borda espessa
            cv2.polylines(frame, [polygon], True, border_color, 2)

            # Label no vértice superior-esquerdo
            top_pt = tuple(polygon[np.argmin(polygon[:, 1])])
            label_pos = (top_pt[0], max(top_pt[1] - 10, 15))
            (tw, th), _ = cv2.getTextSize("ZONA FILA", cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame,
                          (label_pos[0] - 3, label_pos[1] - th - 3),
                          (label_pos[0] + tw + 3, label_pos[1] + 3),
                          (0, 0, 0), -1)
            cv2.putText(frame, "ZONA FILA", label_pos,
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, border_color, 2)

        # ── 2. Linhas de Entrada / Saída (opcionais) ────────────────────
        if show_zones and entry_line is not None and len(entry_line) == 2:
            p1, p2 = tuple(entry_line[0]), tuple(entry_line[1])
            cv2.line(frame, p1, p2, (0, 255, 255), 2)
            cv2.circle(frame, p1, 5, (0, 255, 255), -1)
            cv2.circle(frame, p2, 5, (0, 255, 255), -1)
            cv2.putText(frame, "ENTRADA", (p1[0] + 4, p1[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

        if show_zones and exit_line is not None and len(exit_line) == 2:
            p1, p2 = tuple(exit_line[0]), tuple(exit_line[1])
            cv2.line(frame, p1, p2, (0, 0, 255), 2)
            cv2.circle(frame, p1, 5, (0, 0, 255), -1)
            cv2.circle(frame, p2, 5, (0, 0, 255), -1)
            cv2.putText(frame, "SAIDA", (p1[0] + 4, p1[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        # ── 3. Veículos em fila: Rastros e Timers ───────────────────────
        for tid, v_data in vehicles.items():
            if v_data.get('state') != 'IN_QUEUE':
                continue

            wait_time = v_data.get('current_wait', 0)
            history   = list(v_data.get('history', []))

            # Cor do timer: branco → laranja → vermelho conforme urgência
            ratio = min(wait_time / max(threshold, 1), 1.0)
            if ratio < 0.5:
                timer_color = (255, 255, 255)
            elif ratio < 1.0:
                timer_color = (0, 165, 255)   # Laranja
            else:
                timer_color = (0, 0, 255)     # Vermelho

            # Rastro (Trail)
            if show_trail and len(history) > 1:
                pts = np.array(history, np.int32).reshape((-1, 1, 2))
                cv2.polylines(frame, [pts], False, border_color, 1)

            # Ponto base: last_pos armazena o bottom-center do veículo
            foot = v_data.get('last_pos') or (history[-1] if history else None)

            # Timer individual
            if show_timers and foot:
                cx, cy = foot
                mins, secs = divmod(int(wait_time), 60)
                text = f"ID:{tid}  {mins:02d}:{secs:02d}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
                rx1, ry1 = cx - tw // 2 - 4, cy - th - 18
                rx2, ry2 = cx + tw // 2 + 4, cy - 10
                cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), (0, 0, 0), -1)
                cv2.rectangle(frame, (rx1, ry1), (rx2, ry2), border_color, 1)
                cv2.putText(frame, text, (cx - tw // 2, cy - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, timer_color, 1)

            # Ponto base (foot marker)
            if foot:
                cv2.circle(frame, foot, 4, border_color, -1)

    def draw_tracks(self, frame, tracks):
        """Desenha caixas delimitadoras e labels dos objetos rastreados"""
        if not tracks:
            return

        # Verificar se deve mostrar labels
        show_labels = bool(self.config.get('show_labels', False))

        for track in tracks:
            x1, y1, x2, y2 = track['box']
            label = track['label']
            color = track['color']

            # Box (sempre desenhar a caixa, a menos que configurado para ocultar)
            if not self.config.get('hide_detection_boxes', False):
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Label (apenas se show_labels estiver ativo)
            if show_labels:
                # Label background
                (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), color, -1)

                # Text
                cv2.putText(frame, label, (x1, y1 - 5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
