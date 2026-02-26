#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diálogo de Configuração de Zonas da Fila

Ferramentas de desenho:
  • Linha de Entrada / Saída:
    - Clique e arraste para desenhar a linha
    - Solta o botão → linha travada
    - Clique "Limpar" para recomeçar

  • Polígono de Área da Fila:
    - Clique esquerdo → adiciona vértice
    - Clique direito  → desfaz último vértice
    - Botão "Fechar Polígono" (ou duplo-clique) → finaliza
    - Botão "Limpar" → apaga tudo e recomeça
"""
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QRadioButton, QButtonGroup, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap

from .styles import ThemeColors, Styles


class QueueConfigDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuração de Zonas da Fila")
        self.setModal(True)
        self.resize(1050, 720)
        self.setStyleSheet(f"QDialog {{ background-color: {ThemeColors.BACKGROUND}; }}")
        self.config = config

        # ── Geometria normalizada 0-1 ─────────────────────────────────
        q_cfg = self.config.get('queue_config', {})
        self.entry_line    = list(q_cfg.get('entry_line', []))
        self.queue_polygon = list(q_cfg.get('polygon',    []))
        self.exit_line     = list(q_cfg.get('exit_line',  []))

        # ── Estado interno ────────────────────────────────────────────
        self.current_frame = None
        self.scale_factor  = 1.0
        self.offset_x      = 0.0
        self.offset_y      = 0.0

        # Modo: 0=nenhum, 1=entrada, 2=polígono, 3=saída
        self.draw_mode     = 0
        self.temp_points   = []   # vértices provisórios do polígono em curso
        self.is_dragging   = False  # true enquanto arrasta uma linha

        self.init_ui()
        self.capture_frame()

    # ──────────────────────────────────────────────────────────────────
    # Frame capture
    # ──────────────────────────────────────────────────────────────────
    def _get_last_frame(self):
        parent = self.parent()
        if parent is None:
            return None
        # QueueTab → tem queue_thread
        if hasattr(parent, 'queue_thread') and parent.queue_thread is not None:
            f = parent.queue_thread.last_frame
            if f is not None:
                return f
        # MainWindow → tem video_thread
        if hasattr(parent, 'video_thread') and parent.video_thread is not None:
            f = parent.video_thread.last_frame
            if f is not None:
                return f
        # QueueTab cujo parent é MainWindow
        if hasattr(parent, 'main_window') and parent.main_window is not None:
            mw = parent.main_window
            if hasattr(mw, 'video_thread') and mw.video_thread is not None:
                f = mw.video_thread.last_frame
                if f is not None:
                    return f
        return None

    def capture_frame(self):
        frame = self._get_last_frame()
        if frame is not None:
            self.current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        else:
            # Tela escura indicando câmera offline
            self.current_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            self.current_frame[:] = (18, 28, 48)
            cv2.putText(
                self.current_frame,
                "Camera offline — inicie a camera e clique Atualizar Frame",
                (100, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (180, 180, 180), 2
            )
        self.update_preview()

    def refresh_frame(self):
        frame = self._get_last_frame()
        if frame is not None:
            self.current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.update_preview()
            self.preview_lbl.setStyleSheet("background:#000; border:2px solid #10B981; border-radius:4px;")
            QTimer.singleShot(600, lambda: self.preview_lbl.setStyleSheet("background:#000;"))
        else:
            QMessageBox.warning(self, "Aviso", "Câmera offline — conecte a câmera primeiro.")

    # ──────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────
    def init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Preview ───────────────────────────────────────────────────
        self.preview_lbl = QLabel()
        self.preview_lbl.setAlignment(Qt.AlignCenter)
        self.preview_lbl.setStyleSheet("background:#000;")
        self.preview_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_lbl.setMouseTracking(True)
        # Atribuir handlers de evento
        self.preview_lbl.mousePressEvent      = self.on_mouse_press
        self.preview_lbl.mouseMoveEvent       = self.on_mouse_move
        self.preview_lbl.mouseReleaseEvent    = self.on_mouse_release
        self.preview_lbl.mouseDoubleClickEvent = self.on_double_click
        root.addWidget(self.preview_lbl, stretch=3)

        # ── Painel de Controle ────────────────────────────────────────
        ctrl = QFrame()
        ctrl.setStyleSheet(
            f"background:{ThemeColors.PANEL_BG}; border-left:1px solid {ThemeColors.BORDER};"
        )
        ctrl.setFixedWidth(280)
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(18, 18, 18, 18)
        cl.setSpacing(12)

        # Título
        t = QLabel("<b style='font-size:16px'>Configurar Zonas</b>")
        t.setStyleSheet(f"color:{ThemeColors.TEXT_PRIMARY};")
        cl.addWidget(t)

        # Status dinâmico
        self.lbl_status = QLabel("Selecione uma ferramenta.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet(
            f"color:{ThemeColors.TEXT_SECONDARY}; font-size:12px; "
            f"background:{ThemeColors.SURFACE}; border-radius:6px; padding:8px;"
        )
        cl.addWidget(self.lbl_status)

        # Ferramentas
        self.tool_group = QButtonGroup()
        self.rb_entry = QRadioButton("1. Linha de Entrada  [opcional]")
        self.rb_entry.setStyleSheet("color:#06b6d4; font-weight:bold;")
        self.rb_poly  = QRadioButton("2. Polígono da Fila  [obrigatório]")
        self.rb_poly.setStyleSheet("color:#fbbf24; font-weight:bold;")
        self.rb_exit  = QRadioButton("3. Linha de Saída    [opcional]")
        self.rb_exit.setStyleSheet("color:#ef4444; font-weight:bold;")
        for i, rb in enumerate([self.rb_entry, self.rb_poly, self.rb_exit], 1):
            self.tool_group.addButton(rb, i)
            cl.addWidget(rb)

        self.tool_group.buttonClicked.connect(self._on_tool_selected)

        cl.addSpacing(4)

        # Botão fechar polígono (aparece só no modo polígono)
        self.btn_close_poly = QPushButton("✔ Fechar Polígono")
        self.btn_close_poly.setStyleSheet("""
            QPushButton {
                background:#16a34a; color:white; font-weight:bold;
                border-radius:6px; padding:8px; border:none;
            }
            QPushButton:hover { background:#15803d; }
            QPushButton:disabled { background:#555; color:#999; }
        """)
        self.btn_close_poly.setEnabled(False)
        self.btn_close_poly.clicked.connect(self._close_polygon)
        cl.addWidget(self.btn_close_poly)

        # Botão limpar seleção atual
        self.btn_clear = QPushButton("✖ Limpar Seleção")
        self.btn_clear.setStyleSheet(Styles.BUTTON_SECONDARY)
        self.btn_clear.clicked.connect(self._clear_current)
        cl.addWidget(self.btn_clear)

        cl.addStretch()

        # Atualizar frame
        btn_refresh = QPushButton("↺  Atualizar Frame")
        btn_refresh.setStyleSheet(Styles.BUTTON_SECONDARY)
        btn_refresh.clicked.connect(self.refresh_frame)
        cl.addWidget(btn_refresh)

        # Salvar
        btn_save = QPushButton("💾  Salvar Configuração")
        btn_save.setStyleSheet(Styles.ACTION_BUTTON_EMERALD)
        btn_save.clicked.connect(self.save_config)
        cl.addWidget(btn_save)

        # Cancelar
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet(Styles.BUTTON_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        cl.addWidget(btn_cancel)

        root.addWidget(ctrl)

    # ──────────────────────────────────────────────────────────────────
    # Conversão de coordenadas
    # ──────────────────────────────────────────────────────────────────
    def _widget_to_norm(self, wx, wy):
        """Converte coordenadas do widget para normalizadas [0-1]."""
        if self.current_frame is None:
            return 0.0, 0.0
        h, w = self.current_frame.shape[:2]
        ix = (wx - self.offset_x) / self.scale_factor
        iy = (wy - self.offset_y) / self.scale_factor
        return max(0.0, min(1.0, ix / w)), max(0.0, min(1.0, iy / h))

    # ──────────────────────────────────────────────────────────────────
    # Seleção de ferramenta
    # ──────────────────────────────────────────────────────────────────
    def _on_tool_selected(self, btn):
        self.draw_mode  = self.tool_group.id(btn)
        self.is_dragging = False
        self.temp_points = []
        self.btn_close_poly.setEnabled(False)
        self._refresh_status()
        self.update_preview()

    def _refresh_status(self):
        msgs = {
            0: "Selecione uma ferramenta.",
            1: (
                "<b style='color:#06b6d4'>Linha de Entrada</b><br>"
                "• Clique e arraste para desenhar.<br>"
                "• Solte o botão para travar."
            ),
            2: (
                "<b style='color:#fbbf24'>Polígono da Fila</b><br>"
                f"• {len(self.temp_points)} ponto(s) adicionado(s).<br>"
                "• <b>Clique esquerdo</b> → adicionar vértice.<br>"
                "• <b>Clique direito</b> → desfazer último.<br>"
                "• <b>Duplo-clique</b> ou botão ✔ para fechar."
            ),
            3: (
                "<b style='color:#ef4444'>Linha de Saída</b><br>"
                "• Clique e arraste para desenhar.<br>"
                "• Solte o botão para travar."
            ),
        }
        self.lbl_status.setText(msgs.get(self.draw_mode, ""))

    # ──────────────────────────────────────────────────────────────────
    # Eventos de mouse
    # ──────────────────────────────────────────────────────────────────
    def on_mouse_press(self, event):
        if self.draw_mode == 0 or self.current_frame is None:
            return
        nx, ny = self._widget_to_norm(event.x(), event.y())

        if self.draw_mode in (1, 3):  # Linhas
            if event.button() == Qt.LeftButton:
                self.temp_points = [[nx, ny], [nx, ny]]
                self.is_dragging = True

        elif self.draw_mode == 2:  # Polígono
            if event.button() == Qt.LeftButton:
                self.temp_points.append([nx, ny])
                self.btn_close_poly.setEnabled(len(self.temp_points) >= 3)
                self._refresh_status()
            elif event.button() == Qt.RightButton:
                if self.temp_points:
                    self.temp_points.pop()
                    self.btn_close_poly.setEnabled(len(self.temp_points) >= 3)
                    self._refresh_status()

        self.update_preview()

    def on_mouse_move(self, event):
        if self.draw_mode not in (1, 3) or not self.is_dragging:
            return
        nx, ny = self._widget_to_norm(event.x(), event.y())
        if len(self.temp_points) >= 2:
            self.temp_points[1] = [nx, ny]
        self.update_preview()

    def on_mouse_release(self, event):
        if self.draw_mode not in (1, 3) or not self.is_dragging:
            return
        if event.button() == Qt.LeftButton:
            nx, ny = self._widget_to_norm(event.x(), event.y())
            if len(self.temp_points) >= 2:
                self.temp_points[1] = [nx, ny]
            # Travar: copiar para geometria oficial
            if self.draw_mode == 1:
                self.entry_line = list(self.temp_points)
            else:
                self.exit_line = list(self.temp_points)
            self.is_dragging = False
            self.update_preview()

    def on_double_click(self, event):
        """Duplo-clique no modo polígono fecha o polígono."""
        if self.draw_mode == 2 and event.button() == Qt.LeftButton:
            self._close_polygon()

    # ──────────────────────────────────────────────────────────────────
    # Ações de ferramentas
    # ──────────────────────────────────────────────────────────────────
    def _close_polygon(self):
        if len(self.temp_points) < 3:
            QMessageBox.warning(self, "Aviso", "Adicione pelo menos 3 pontos antes de fechar o polígono.")
            return
        self.queue_polygon = list(self.temp_points)
        self.temp_points   = []
        self.btn_close_poly.setEnabled(False)
        self._refresh_status()
        self.update_preview()
        # Feedback visual
        self.lbl_status.setText(
            f"<b style='color:#10B981'>✔ Polígono fechado</b> com "
            f"{len(self.queue_polygon)} pontos.<br>Clique 'Limpar' para refazer."
        )

    def _clear_current(self):
        self.temp_points  = []
        self.is_dragging  = False
        self.btn_close_poly.setEnabled(False)
        if self.draw_mode == 1:
            self.entry_line    = []
        elif self.draw_mode == 2:
            self.queue_polygon = []
        elif self.draw_mode == 3:
            self.exit_line     = []
        self._refresh_status()
        self.update_preview()

    # ──────────────────────────────────────────────────────────────────
    # Render do preview
    # ──────────────────────────────────────────────────────────────────
    def update_preview(self):
        if self.current_frame is None:
            return

        h, w = self.current_frame.shape[:2]
        img = self.current_frame.copy()

        # ── Polígono salvo (amarelo) ──────────────────────────────────
        if self.queue_polygon and len(self.queue_polygon) >= 3:
            pts = self._norm_to_px(self.queue_polygon, w, h)
            overlay = img.copy()
            cv2.fillPoly(overlay, [pts], (200, 160, 0))
            cv2.addWeighted(overlay, 0.22, img, 0.78, 0, img)
            cv2.polylines(img, [pts], True, (255, 215, 0), 2)
            for i, pt in enumerate(pts):
                cv2.circle(img, tuple(pt), 6, (0, 255, 0) if i == 0 else (255, 215, 0), -1)
                cv2.circle(img, tuple(pt), 8, (255, 255, 255), 1)
            self._label(img, "AREA FILA", pts[0], (255, 215, 0))

        # ── Polígono em construção (pontilhado esbranquiçado) ─────────
        if self.temp_points and self.draw_mode == 2:
            pts_tmp = self._norm_to_px(self.temp_points, w, h)
            cv2.polylines(img, [pts_tmp], False, (255, 200, 60), 1)
            for i, pt in enumerate(pts_tmp):
                color = (0, 255, 0) if i == 0 else (255, 200, 60)
                cv2.circle(img, tuple(pt), 7, color, -1)
                cv2.circle(img, tuple(pt), 9, (255, 255, 255), 1)
                cv2.putText(img, str(i + 1), (pt[0] + 6, pt[1] - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            if len(pts_tmp) >= 3:
                # Linha tracejada do último ao primeiro para indicar fechamento possível
                p_last = tuple(pts_tmp[-1])
                p_first = tuple(pts_tmp[0])
                self._dashed_line(img, p_last, p_first, (0, 255, 0), 1)
                cv2.putText(img, "duplo-clique ou botao para fechar",
                            (pts_tmp[0][0] + 10, pts_tmp[0][1] - 12),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 1)

        # ── Linha de Entrada (Cyan) ───────────────────────────────────
        self._draw_line(img, self.entry_line, w, h, (0, 255, 255), "ENTRADA")

        # ── Linha de Saída (Vermelho) ─────────────────────────────────
        self._draw_line(img, self.exit_line, w, h, (60, 60, 255), "SAIDA")

        # ── Linha sendo arrastada (preview vivo) ──────────────────────
        if self.is_dragging and len(self.temp_points) == 2:
            color = (0, 255, 255) if self.draw_mode == 1 else (60, 60, 255)
            self._draw_line(img, self.temp_points, w, h, color, "")

        # ── Exibir no QLabel ──────────────────────────────────────────
        qt_img  = QImage(img.data, w, h, w * 3, QImage.Format_RGB888)
        pixmap  = QPixmap.fromImage(qt_img)
        lbl_w   = self.preview_lbl.width()
        lbl_h   = self.preview_lbl.height()
        if lbl_w > 0 and lbl_h > 0:
            scaled = pixmap.scaled(lbl_w, lbl_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.scale_factor = min(lbl_w / w, lbl_h / h)
            self.offset_x     = (lbl_w - w * self.scale_factor) / 2
            self.offset_y     = (lbl_h - h * self.scale_factor) / 2
            self.preview_lbl.setPixmap(scaled)

    # ── Helpers de desenho ────────────────────────────────────────────
    def _norm_to_px(self, pts_norm, w, h):
        arr = np.array(pts_norm, np.float32)
        arr[:, 0] *= w
        arr[:, 1] *= h
        return arr.astype(np.int32)

    def _draw_line(self, img, line, w, h, color, label):
        if not line or len(line) != 2:
            return
        p1 = (int(line[0][0] * w), int(line[0][1] * h))
        p2 = (int(line[1][0] * w), int(line[1][1] * h))
        cv2.line(img, p1, p2, color, 3)
        cv2.circle(img, p1, 7, color, -1)
        cv2.circle(img, p2, 7, color, -1)
        cv2.circle(img, p1, 9, (255, 255, 255), 1)
        cv2.circle(img, p2, 9, (255, 255, 255), 1)
        if label:
            self._label(img, label, p1, color)

    def _label(self, img, text, pt, color):
        x, y = pt[0], max(pt[1] - 10, 15)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        cv2.rectangle(img, (x - 2, y - th - 4), (x + tw + 2, y + 4), (0, 0, 0), -1)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    @staticmethod
    def _dashed_line(img, p1, p2, color, thickness, gap=8):
        """Linha tracejada entre p1 e p2."""
        dist = ((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2) ** 0.5
        if dist < 1:
            return
        steps = int(dist / gap)
        for i in range(0, steps, 2):
            t0 = i / steps
            t1 = min((i + 1) / steps, 1.0)
            a = (int(p1[0] + t0*(p2[0]-p1[0])), int(p1[1] + t0*(p2[1]-p1[1])))
            b = (int(p1[0] + t1*(p2[0]-p1[0])), int(p1[1] + t1*(p2[1]-p1[1])))
            cv2.line(img, a, b, color, thickness)

    # ──────────────────────────────────────────────────────────────────
    # Salvar
    # ──────────────────────────────────────────────────────────────────
    def save_config(self):
        # Polígono em construção não finalizado → tentar fechar automaticamente
        if not self.queue_polygon and len(self.temp_points) >= 3:
            self.queue_polygon = list(self.temp_points)
            self.temp_points   = []

        if not self.queue_polygon or len(self.queue_polygon) < 3:
            QMessageBox.warning(
                self, "Aviso",
                "É necessário definir o <b>Polígono da Área de Fila</b> com pelo menos 3 pontos.\n\n"
                "Selecione '2. Polígono da Fila', clique para adicionar pontos e depois\n"
                "clique '✔ Fechar Polígono' ou dê duplo-clique."
            )
            return

        q_cfg = self.config.get('queue_config', {})
        q_cfg['polygon']    = [list(p) for p in self.queue_polygon]
        q_cfg['entry_line'] = [list(p) for p in self.entry_line]  if len(self.entry_line) == 2  else []
        q_cfg['exit_line']  = [list(p) for p in self.exit_line]   if len(self.exit_line)  == 2  else []
        self.config.set('queue_config', q_cfg)
        self.accept()

    def resizeEvent(self, event):
        self.update_preview()
        super().resizeEvent(event)
