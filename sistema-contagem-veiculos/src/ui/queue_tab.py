#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aba de Tempo de Fila (Queue Management)
"""
import os
import cv2
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QSlider, QCheckBox, QPushButton, QFileDialog,
    QScrollArea, QSizePolicy, QGroupBox, QLineEdit, QSplitter, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap, QIcon

from .styles import Styles, ThemeColors

from ..core.detector import VideoThread

class QueueTab(QWidget):
    """
    Aba dedicada ao monitoramento de filas e tempos de espera.
    Sistema independente com sua própria Thread de Vídeo.
    """
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.main_window = parent
        self.queue_thread = None  # Thread independente
        self.queue_model = config.get('queue_modelo_yolo', '') or 'yolo11n.pt'
        self._dying_threads = []  # Mantém referências até cleanup terminar

        self.init_ui()

    def init_ui(self):
        """Inicializa a interface gráfica"""
        # QSplitter horizontal substituindo o QHBoxLayout fixo
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #3B3B3B;
            }
            QSplitter::handle:hover {
                background: #4A90E2;
            }
        """)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(splitter)

        # --- Lado Esquerdo: Vídeo + Overlay ---
        self.video_container = QFrame()
        self.video_container.setStyleSheet(f"background-color: {ThemeColors.BACKGROUND};")
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(10, 10, 10, 10)

        # Label do Vídeo
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet(f"background-color: #000; border-radius: 8px;")
        self.video_label.setText("Aguardando Conexão...")
        video_layout.addWidget(self.video_label)

        splitter.addWidget(self.video_container)

        # --- Lado Direito: Dashboard + Config (COM SCROLL) ---
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {ThemeColors.PANEL_BG};
                border: none;
                border-left: 1px solid {ThemeColors.BORDER};
            }}
            QWidget {{
                background-color: {ThemeColors.PANEL_BG};
            }}
        """)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(20)

        # 1. Título
        title_lbl = QLabel("Métricas de Fila")
        title_lbl.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY};")
        right_layout.addWidget(title_lbl)

        # 2. Cards de Métricas
        cards_grid = QGridLayout()
        cards_grid.setSpacing(15)

        # Card 1: Tempo Médio (5 min)
        self.card_avg_wait = self._create_metric_card("Tempo Médio (5min)", "--:--", "icons/clock.png", ThemeColors.PRIMARY)
        cards_grid.addWidget(self.card_avg_wait, 0, 0)

        # Card 2: Veículos em Espera
        self.card_waiting = self._create_metric_card("Veículos em Espera", "0", "icons/car.png", ThemeColors.SECONDARY)
        cards_grid.addWidget(self.card_waiting, 0, 1)

        # Card 3: Status
        self.card_status = self._create_status_card()
        cards_grid.addWidget(self.card_status, 1, 0)

        # Card 4: Máximo Sessão
        self.card_max_wait = self._create_metric_card("Tempo Máximo", "--:--", "icons/trend_up.png", ThemeColors.WARNING)
        cards_grid.addWidget(self.card_max_wait, 1, 1)

        right_layout.addLayout(cards_grid)

        # 3. Separador
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(f"background-color: {ThemeColors.BORDER};")
        right_layout.addWidget(line)

        # 4. Parâmetros (Sidebar)
        params_title = QLabel("Parâmetros de Alerta")
        params_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY};")
        right_layout.addWidget(params_title)

        # 0. Conexão RTSP (Independente)
        conn_group = QGroupBox("Conexão Câmera")
        conn_layout = QVBoxLayout()

        self.rtsp_input = QLineEdit()
        self.rtsp_input.setPlaceholderText("rtsp://...")
        self.rtsp_input.setText(self.config.get('rtsp_url_queue', ''))
        self.rtsp_input.setStyleSheet(Styles.INPUT)
        conn_layout.addWidget(QLabel("URL RTSP:"))
        conn_layout.addWidget(self.rtsp_input)

        # Seleção de modelo independente
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Modelo YOLO:"))
        self.queue_model_label = QLabel(os.path.basename(self.queue_model))
        self.queue_model_label.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-style: italic;")
        model_row.addWidget(self.queue_model_label)
        model_row.addStretch()

        btn_model = QPushButton("Modelo")
        btn_model.setStyleSheet(Styles.BUTTON_SECONDARY)
        btn_model.clicked.connect(self._select_model)
        model_row.addWidget(btn_model)

        conn_layout.addLayout(model_row)

        # Confiança do modelo
        conf_header = QHBoxLayout()
        conf_header.addWidget(QLabel("Confiança:"))
        self.queue_conf_label = QLabel(f"{int(self.config.get('queue_confianca', 0.40) * 100)}%")
        self.queue_conf_label.setStyleSheet(f"font-weight: bold; color: {ThemeColors.PRIMARY};")
        conf_header.addWidget(self.queue_conf_label)
        conf_header.addStretch()
        conn_layout.addLayout(conf_header)

        self.queue_conf_slider = QSlider(Qt.Horizontal)
        self.queue_conf_slider.setRange(10, 90)
        self.queue_conf_slider.setValue(int(self.config.get('queue_confianca', 0.40) * 100))
        self.queue_conf_slider.setStyleSheet(Styles.SLIDER)
        self.queue_conf_slider.valueChanged.connect(self._on_conf_change)
        conn_layout.addWidget(self.queue_conf_slider)

        conn_btns = QHBoxLayout()
        self.btn_connect = QPushButton("Conectar Câmera")
        self.btn_connect.setStyleSheet(Styles.BUTTON_PRIMARY)
        self.btn_connect.clicked.connect(self._connect_camera)
        conn_btns.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Desconectar")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.setMinimumHeight(self.btn_connect.sizeHint().height())
        self.btn_disconnect.setStyleSheet("""
            QPushButton {
                background-color: #dc3545; color: white;
                font-weight: bold; padding: 8px 16px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #c82333; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self.btn_disconnect.clicked.connect(self._disconnect_camera)
        conn_btns.addWidget(self.btn_disconnect)

        conn_layout.addLayout(conn_btns)
        conn_group.setLayout(conn_layout)
        right_layout.addWidget(conn_group)

        # ... (Threshold slider) ...
        thresh_group = QGroupBox("Limiares") # Agrupando para ficar melhor visualmente
        thresh_layout = QVBoxLayout()

        # Tempo Crítico
        thresh_header = QHBoxLayout()
        thresh_header.addWidget(QLabel("Tempo Crítico:"))
        self.thresh_val_label = QLabel(f"{self.config.get('queue_config', {}).get('threshold_seconds', 60)}s")
        self.thresh_val_label.setStyleSheet(f"font-weight: bold; color: {ThemeColors.PRIMARY};")
        thresh_header.addWidget(self.thresh_val_label)
        thresh_header.addStretch()
        thresh_layout.addLayout(thresh_header)

        self.thresh_slider = QSlider(Qt.Horizontal)
        self.thresh_slider.setRange(10, 300)
        self.thresh_slider.setValue(int(self.config.get('queue_config', {}).get('threshold_seconds', 60)))
        self.thresh_slider.setStyleSheet(Styles.SLIDER)
        self.thresh_slider.valueChanged.connect(self._on_threshold_change)
        thresh_layout.addWidget(self.thresh_slider)

        # Tempo Mínimo de Espera
        min_wait_row = QHBoxLayout()
        min_wait_row.addWidget(QLabel("Espera mínima:"))
        self.min_wait_spin = QSpinBox()
        self.min_wait_spin.setRange(0, 60)
        self.min_wait_spin.setValue(int(self.config.get('queue_config', {}).get('min_wait_time', 5)))
        self.min_wait_spin.setSuffix("s")
        self.min_wait_spin.setMaximumWidth(72)
        self.min_wait_spin.setStyleSheet(Styles.INPUT)
        self.min_wait_spin.setToolTip(
            "Tempo mínimo (segundos) que um veículo deve permanecer na zona\n"
            "para ser registrado. Use 0 para registrar todos."
        )
        self.min_wait_spin.valueChanged.connect(lambda v: self._update_config('min_wait_time', float(v)))
        min_wait_row.addWidget(self.min_wait_spin)
        min_wait_row.addStretch()
        thresh_layout.addLayout(min_wait_row)

        thresh_group.setLayout(thresh_layout)
        right_layout.addWidget(thresh_group)

        # Visual Toggles
        vis_group = QGroupBox("Visualização")
        vis_layout = QVBoxLayout()

        self.cb_show_labels = QCheckBox("Mostrar Labels/IDs")
        self.cb_show_labels.setChecked(self.config.get('show_labels', False))
        self.cb_show_labels.setStyleSheet(Styles.CHECKBOX)
        self.cb_show_labels.toggled.connect(self._update_visuals)
        vis_layout.addWidget(self.cb_show_labels)

        self.cb_show_zones = QCheckBox("Mostrar Zonas")
        self.cb_show_zones.setChecked(self.config.get('show_zone_tags', True))
        self.cb_show_zones.setStyleSheet(Styles.CHECKBOX)
        self.cb_show_zones.toggled.connect(self._update_visuals)
        vis_layout.addWidget(self.cb_show_zones)

        # Queue specifics
        self.cb_show_timers = QCheckBox("Mostrar Timers")
        self.cb_show_timers.setChecked(self.config.get('queue_config', {}).get('show_timers', True))
        self.cb_show_timers.setStyleSheet(Styles.CHECKBOX)
        self.cb_show_timers.toggled.connect(lambda v: self._update_config('show_timers', v))
        vis_layout.addWidget(self.cb_show_timers)

        self.cb_show_trail = QCheckBox("Mostrar Rastro")
        self.cb_show_trail.setChecked(self.config.get('queue_config', {}).get('show_trail', True))
        self.cb_show_trail.setStyleSheet(Styles.CHECKBOX)
        self.cb_show_trail.toggled.connect(lambda v: self._update_config('show_trail', v))
        vis_layout.addWidget(self.cb_show_trail)

        vis_group.setLayout(vis_layout)
        right_layout.addWidget(vis_group)

        # 5. Botões de Ação

        # Grupo Controle
        ctrl_group = QGroupBox("Controle")
        ctrl_layout = QVBoxLayout()

        # Dois botões separados: Start / Stop
        btn_row = QHBoxLayout()

        self.btn_start_queue = QPushButton("▶ Iniciar Fila")
        self.btn_start_queue.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)
        self.btn_start_queue.clicked.connect(self._start_queue)
        btn_row.addWidget(self.btn_start_queue)

        self.btn_stop_queue = QPushButton("■ Parar Fila")
        self.btn_stop_queue.setEnabled(False)
        self.btn_stop_queue.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)
        self.btn_stop_queue.clicked.connect(self._stop_queue)
        btn_row.addWidget(self.btn_stop_queue)

        ctrl_layout.addLayout(btn_row)

        ctrl_group.setEnabled(False)  # Só habilita após conectar
        self.ctrl_group = ctrl_group

        self.btn_config_zones = QPushButton("Configurar Zonas")
        self.btn_config_zones.setStyleSheet(Styles.BUTTON_SECONDARY)
        self.btn_config_zones.clicked.connect(self._open_zone_config)
        ctrl_layout.addWidget(self.btn_config_zones)

        ctrl_group.setLayout(ctrl_layout)
        right_layout.addWidget(ctrl_group)

        self.btn_export = QPushButton(" Exportar CSV")
        self.btn_export.setStyleSheet(Styles.ACTION_BUTTON_EMERALD)
        self.btn_export.clicked.connect(self.export_csv)
        right_layout.addWidget(self.btn_export)

        # Add Stretch to push everything up
        right_layout.addStretch()

        right_scroll.setWidget(right_panel)
        splitter.addWidget(right_scroll)

        # Tamanhos iniciais: 70% vídeo / 30% config
        splitter.setSizes([700, 300])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, True)
        self.video_container.setMinimumWidth(200)
        right_scroll.setMinimumWidth(0)

    def _start_queue(self):
        if self.queue_thread:
            self.queue_thread.set_queue_active(True)
            self.btn_start_queue.setEnabled(False)
            self.btn_stop_queue.setEnabled(True)

    def _stop_queue(self):
        if self.queue_thread:
            self.queue_thread.set_queue_active(False)
            self.btn_start_queue.setEnabled(True)
            self.btn_stop_queue.setEnabled(False)

    def _select_model(self):
        """Abre diálogo para seleção de modelo independente da fila"""
        from .model_dialog import PersonalizedModelDialog
        dlg = PersonalizedModelDialog(self, current_model=self.queue_model)
        if dlg.exec_():
            selected = dlg.get_selected_model()
            if selected:
                self.queue_model = selected
                self.config.set('queue_modelo_yolo', selected)
                self.queue_model_label.setText(os.path.basename(selected))

    def _connect_camera(self):
        url = self.rtsp_input.text().strip()
        if not url:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Aviso", "Digite uma URL RTSP válida.")
            return

        # Salvar config
        self.config.set('rtsp_url_queue', url)

        # Encerrar thread anterior se existir
        self._stop_thread()

        # Iniciar Nova Thread LOCAL com modelo e confiança independentes
        # conf_override e model_override isolam a thread de fila do config compartilhado
        try:
            queue_model = self.queue_model or 'yolo11n.pt'
            queue_conf = float(self.config.get('queue_confianca', 0.40))

            self.queue_thread = VideoThread(
                self.config,
                rtsp_url=url,
                model_override=queue_model,
                conf_override=queue_conf,
            )
            self.queue_thread.change_pixmap_signal.connect(self.update_video)
            self.queue_thread.update_queue_stats.connect(self.update_stats)

            self.queue_thread.start()

            # Habilitar controles e resetar botões
            self.ctrl_group.setEnabled(True)
            self.btn_start_queue.setEnabled(True)
            self.btn_stop_queue.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.btn_connect.setText("Reconectar")

            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Conexão", "Câmera conectada com sucesso!")

        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Erro", f"Erro ao conectar: {e}")

    def _disconnect_camera(self):
        """Para a thread de câmera e reseta o estado da UI."""
        self._stop_thread()
        self.ctrl_group.setEnabled(False)
        self.btn_start_queue.setEnabled(True)
        self.btn_stop_queue.setEnabled(False)
        self.btn_disconnect.setEnabled(False)
        self.btn_connect.setText("Conectar Câmera")
        self.video_label.setText("Câmera desconectada.")
        self.video_label.setPixmap(QPixmap())

    def _stop_thread(self):
        """Sinaliza parada da queue_thread. Totalmente não-bloqueante.

        Fluxo:
          1. running=False + _stop_requested.set() → VideoThread.run() encerra
          2. QThread.finished → _cleanup_thread() é chamado via signal
          3. _cleanup_thread() lança daemon thread Python para cap.release()
             (que pode bloquear até 8s no join do _read_loop) sem travar a UI.

        NÃO usa terminate() — terminate() mata a thread em C-code (YOLO/FFMPEG)
        causando corrupção de estado e crash."""
        if self.queue_thread:
            thread = self.queue_thread
            self.queue_thread = None
            try:
                thread.running = False
                thread._stop_requested.set()
                self._dying_threads.append(thread)
                thread.finished.connect(lambda: self._cleanup_thread(thread))
            except Exception:
                pass

    def _cleanup_thread(self, thread):
        """Executa cleanup (cap.release + save DB) em daemon thread para
        não bloquear a UI (cap.release pode levar até 8s no join do _read_loop)."""
        import threading as _threading
        def _do():
            try:
                thread.cleanup()
            except Exception:
                pass
            try:
                self._dying_threads.remove(thread)
            except (ValueError, RuntimeError, AttributeError):
                pass
        _threading.Thread(target=_do, daemon=True).start()

    def _open_zone_config(self):
        from .queue_config_dialog import QueueConfigDialog
        dlg = QueueConfigDialog(self.config, self)
        if dlg.exec_():
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Sucesso", "Configuração de zonas salva!")

    def _update_visuals(self):
        show_labels = self.cb_show_labels.isChecked()
        show_zones = self.cb_show_zones.isChecked()

        # Atualizar Thread LOCAL
        if self.queue_thread:
            self.queue_thread.set_visual_config(show_labels, show_zones, self.config.get('hide_detection_lines', False))

    def _create_metric_card(self, title, value, icon, color):
        frame = QFrame()
        frame.setStyleSheet(f"""
            background-color: {ThemeColors.SURFACE};
            border-radius: 10px;
            border: 1px solid {ThemeColors.SURFACE_LIGHT};
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(15, 15, 15, 15)

        # Icon + Title
        head = QHBoxLayout()

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; font-weight: 600;")
        head.addWidget(lbl_title)
        head.addStretch()
        lay.addLayout(head)

        # Value
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 24px; font-weight: bold;")
        lay.addWidget(lbl_val)

        frame.val_label = lbl_val
        return frame

    def _create_status_card(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            background-color: {ThemeColors.SURFACE};
            border-radius: 10px;
            border: 1px solid {ThemeColors.SURFACE_LIGHT};
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(15, 15, 15, 15)

        lbl_title = QLabel("Status da Operação")
        lbl_title.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; font-weight: 600;")
        lay.addWidget(lbl_title)

        lbl_status = QLabel("Normal")
        lbl_status.setStyleSheet(f"color: {ThemeColors.SUCCESS}; font-size: 20px; font-weight: bold;")
        lay.addWidget(lbl_status)

        lbl_desc = QLabel("Fluxo normal")
        lbl_desc.setStyleSheet(f"color: {ThemeColors.TEXT_TERTIARY}; font-size: 11px;")
        lay.addWidget(lbl_desc)

        frame.status_label = lbl_status
        frame.desc_label = lbl_desc
        return frame

    def _on_conf_change(self, value):
        self.queue_conf_label.setText(f"{value}%")
        new_conf = value / 100.0
        self.config.set('queue_confianca', new_conf)
        # Atualiza a thread em execução se existir
        if self.queue_thread:
            self.queue_thread.conf_override = new_conf

    def _on_threshold_change(self, value):
        self.thresh_val_label.setText(f"{value}s")
        self._update_config('threshold_seconds', value)

    def _update_config(self, key, value):
        q_cfg = self.config.get('queue_config', {})
        q_cfg[key] = value
        self.config.set('queue_config', q_cfg)

    def update_stats(self, stats):
        """Chamado pelo MainWindow quando recebe sinal do detector"""
        # Formatar tempos
        def fmt_time(s):
            m, s = divmod(int(s), 60)
            return f"{m:02d}:{s:02d}"

        self.card_avg_wait.val_label.setText(fmt_time(stats.get('avg_wait_5min', 0)))
        self.card_waiting.val_label.setText(str(stats.get('waiting_count', 0)))
        self.card_max_wait.val_label.setText(fmt_time(stats.get('max_wait_session', 0)))

        status = stats.get('status', 'Normal')
        if status == 'Critico':
            self.card_status.status_label.setText("CRÍTICO")
            self.card_status.status_label.setStyleSheet(f"color: {ThemeColors.DANGER}; font-size: 20px; font-weight: bold;")
            self.card_status.desc_label.setText("Gargalo detectado!")
        elif status == 'Atencao':
            self.card_status.status_label.setText("ATENÇÃO")
            self.card_status.status_label.setStyleSheet(f"color: {ThemeColors.WARNING}; font-size: 20px; font-weight: bold;")
            self.card_status.desc_label.setText("Fila moderada")
        else:
            self.card_status.status_label.setText("Normal")
            self.card_status.status_label.setStyleSheet(f"color: {ThemeColors.SUCCESS}; font-size: 20px; font-weight: bold;")
            self.card_status.desc_label.setText("Fluxo livre")

    def update_video(self, image: QImage):
        """Atualiza o frame de vídeo"""
        if self.isVisible():
            pixmap = QPixmap.fromImage(image)
            # Escalonar mantendo proporção
            w = self.video_container.width() - 20
            h = self.video_container.height() - 20
            scaled = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.video_label.setPixmap(scaled)

    def set_rtsp_url(self, url):
        # Placeholder se precisar reiniciar algo específico
        pass

    def export_csv(self):
        """Exporta o histórico de fila para CSV"""
        from PyQt5.QtWidgets import QMessageBox
        if self.queue_thread is None or not self.queue_thread.isRunning():
            QMessageBox.information(self, "Exportar", "Nenhuma câmera de fila conectada.")
            return

        qm = self.queue_thread.queue_manager
        if not qm or not qm.session_history:
            QMessageBox.information(self, "Exportar", "Não há dados de fila para exportar nesta sessão.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Relatório de Fila",
            f"fila_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "Arquivo CSV (*.csv)"
        )

        if path:
            try:
                import pandas as pd
                df = pd.DataFrame(qm.session_history)
                df.to_csv(path, index=False, sep=';', encoding='utf-8-sig')
                QMessageBox.information(self, "Sucesso", f"Relatório salvo em:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao salvar arquivo:\n{str(e)}")
