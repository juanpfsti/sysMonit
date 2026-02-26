#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface gráfica principal do sistema
"""

import sys
import cv2
import os
import threading
from datetime import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QSlider, QTextEdit, QFrame, QGridLayout, QComboBox,
    QDialog, QDialogButtonBox, QMessageBox, QCheckBox, QGroupBox, QScrollArea,
    QSizePolicy, QFileDialog, QTabWidget, QTimeEdit, QSplitter, QRadioButton,
    QButtonGroup, QStackedWidget
)
from PyQt5.QtCore import Qt, QEvent, QTimer, pyqtSignal, QSize, QTime
from PyQt5.QtGui import QImage, QPixmap, QKeySequence, QPainter, QPen, QColor, QIcon

from ..core.config import Config
from ..core.detector import VideoThread
from ..core.counter import VehicleCounter
from ..core.database import CounterDatabase
from .history_tab import HistoryTab
from .dashboard_tab import DashboardTab
from .queue_tab import QueueTab
from .queue_reports_tab import QueueReportsTab
from .queue_analysis_tab import QueueAnalysisTab
from .components.navigation_hub import NavigationMenu
from .view_wrapper import wrap_with_header
from .styles import Styles, ThemeColors
from .model_dialog import PersonalizedModelDialog


class MainWindow(QMainWindow):
    # Sinal para comunicação thread-safe com a GUI
    export_completed = pyqtSignal(str)  # Recebe mensagem de log

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.database = CounterDatabase()  # Banco de dados para persistir contagens
        self.video_thread = None
        self._export_in_progress = False  # Flag para evitar múltiplas exportações simultâneas
        self.is_fullscreen = False
        self.current_rtsp_url = ''  # Link RTSP atualmente em uso
        self.selected_model = 'yolo11n.pt'  # Modelo padrão
        
        # 🔒 PROTEÇÃO CONTRA RACE CONDITIONS - Flags de shutdown
        self._is_closing = False  # Flag para indicar que estamos fechando
        self._shutdown_lock = threading.Lock()  # Lock para sincronização thread-safe
        
        self.init_ui()
        self.apply_stylesheet()
        self.setup_shortcuts()

        # Timer para exportação automática periódica
        self.export_timer = QTimer()
        self.export_timer.timeout.connect(self.auto_export_report)

        # Timer para verificação de horário específico (verifica a cada minuto)
        self.export_schedule_timer = QTimer()
        self.export_schedule_timer.timeout.connect(self.check_scheduled_export)
        self.export_schedule_timer.setInterval(60000)  # 60 segundos

        # Controle de última exportação agendada
        self.last_scheduled_export_date = None

        # Conectar sinal de exportação completa ao log
        self.export_completed.connect(self.add_log)

        # NÃO carregar contadores ao abrir - só depois de inserir link RTSP

    def create_icon_label(self, icon_name, size=24):
        """Cria um QLabel com ícone PNG da pasta icons/"""
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'icons', f'{icon_name}.ico')

        label = QLabel()
        if os.path.exists(icon_path):
            # USAR QIcon PARA CARREGAR MELHOR RESOLUÇÃO DO ARQUIVO .ICO
            # QPixmap(path) carrega apenas a primeira imagem (geralmente pequena), causando borrões
            icon = QIcon(icon_path)
            pixmap = icon.pixmap(size, size)
            label.setPixmap(pixmap)
        else:
            # Fallback para texto se ícone não existir
            label.setText(icon_name)

        label.setStyleSheet("background: transparent; border: none;")
        label.setAlignment(Qt.AlignCenter)
        return label

    def setup_shortcuts(self):
        self.addAction(self._make_shortcut(QKeySequence("F11"), self.toggle_fullscreen))
        self.addAction(self._make_shortcut(QKeySequence("Esc"), self.exit_fullscreen))

    def _make_shortcut(self, seq, handler):
        act = self.menuBar().addAction("")
        act.setShortcut(seq)
        act.triggered.connect(handler)
        return act

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
        else:
            self.showFullScreen()
            self.is_fullscreen = True

    def exit_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False

    def _update_left_panel_visibility(self):
        """Atualiza a visibilidade do painel esquerdo baseado na navegação."""
        if not hasattr(self, 'monitor_stack') or not hasattr(self, 'main_tab_widget'):
            return

        main_tab_index = self.main_tab_widget.currentIndex()
        monitor_stack_index = self.monitor_stack.currentIndex()
        
        # O painel esquerdo só deve aparecer se:
        # 1. Estiver na aba Principal (Monitoramento, index 0)
        # 2. Estiver na página "Visão Geral" (index 1 do Stack)
        should_show = (main_tab_index == 0) and (monitor_stack_index == 1)
        
        if should_show:
            if not self.left_scroll.isVisible():
                self.left_scroll.show()
                # Tentar restaurar tamanho anterior ou usar padrão
                sizes = getattr(self, '_saved_splitter_sizes', None)
                if sizes and sizes[0] > 50:
                    self.main_splitter.setSizes(sizes)
                else:
                    self.main_splitter.setSizes([450, 1150]) # Tamanho padrão razoável
        else:
            if self.left_scroll.isVisible():
                self._saved_splitter_sizes = self.main_splitter.sizes()
                self.left_scroll.hide()

    def _on_main_tab_changed(self, index):
        """Handler para mudança de aba principal."""
        self._update_left_panel_visibility()

    def init_ui(self):
        self.setWindowTitle("Sistema Monitoramento")
        self.setGeometry(100, 100, 1600, 950)
        self.setMinimumSize(1400, 800)

        # Definir ícone da janela
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'icons', 'app.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0,0,0,0)

        # Usar QSplitter para permitir ajuste manual da largura dos painéis
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(4)  # Largura da barra de divisão
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background: #3B3B3B;
            }
            QSplitter::handle:hover {
                background: #4A90E2;
            }
        """)

        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_scroll.setMinimumWidth(0) # Permitir ocultar completamente

        left = self.create_left_panel()
        self.left_scroll.setWidget(left)
        self.main_splitter.addWidget(self.left_scroll)

        # Sistema de abas no painel direito (Agora Hierárquico)
        self.tabs = self.create_tabs_panel()
        self.tabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.tabs.setMinimumWidth(0) # Permitir encolher totalmente
        self.main_splitter.addWidget(self.tabs)

        # Definir proporção inicial
        self.main_splitter.setSizes([0, 1600]) # Começa fechado por padrão
        self.main_splitter.setCollapsible(0, True)
        self.main_splitter.setCollapsible(1, True)

        # Atualizar estado inicial
        QTimer.singleShot(100, self._update_left_panel_visibility)

        main_layout.addWidget(self.main_splitter)

        # Ocultar painel esquerdo quando estiver na aba de Fila
        self.main_tab_widget.currentChanged.connect(self._on_main_tab_changed)

    def create_left_panel(self):
        panel = QWidget()
        panel.setObjectName("leftPanel")
        layout = QVBoxLayout(panel)
        layout.setSpacing(16)  # Aumentado de 12 para melhor separação
        layout.setContentsMargins(20, 16, 20, 16)  # Reduzido para aproveitar melhor o espaço

        # Cabeçalho (Horizontal com Logo | Título + Subtítulo)
        # Container do cabeçalho
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(15)

        # 1. Logo (Esquerda)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        logo_path = os.path.join(project_root, 'icons', 'logo.ico')

        if os.path.exists(logo_path):
            logo_label = QLabel()
            # USAR QIcon PARA CARREGAR MELHOR RESOLUÇÃO DO ARQUIVO .ICO
            # QPixmap(path) carrega apenas a primeira imagem (geralmente pequena), causando borrões
            icon = QIcon(logo_path)
            # Solicitar um pixmap grande (ex: 512x512) para garantir que o Qt pegue a versão de alta resolução
            logo_pixmap = icon.pixmap(512, 512)
            
            # Redimensionar logo para um tamanho menor e fixo para caber no header horizontal
            if not logo_pixmap.isNull():
                logo_pixmap = logo_pixmap.scaledToHeight(72, Qt.SmoothTransformation)
                logo_label.setPixmap(logo_pixmap)
                logo_label.setAlignment(Qt.AlignCenter)
                header_layout.addWidget(logo_label)

        # 2. Separador Vertical
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet(f"background-color: {ThemeColors.BORDER}; width: 1px;")
        separator.setFixedHeight(62)
        header_layout.addWidget(separator)

        # 3. Título + Subtítulo (Direita, Vertical Stack)
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        title = QLabel("Sistema Monitoramento")
        title.setObjectName("panelTitle")
        title.setStyleSheet(f"font-size: 21px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY};")
        title.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        
        subtitle = QLabel("Detecção e Análise em Tempo Real")
        subtitle.setObjectName("panelSubtitle")
        subtitle.setStyleSheet(f"font-size: 15px; color: {ThemeColors.TEXT_SECONDARY};")
        subtitle.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        
        header_layout.addWidget(text_container)
        header_layout.addStretch()

        layout.addWidget(header_widget)

        # GRUPO: Configurações Básicas
        basic_group = QGroupBox("Configurações Básicas")
        basic_layout = QVBoxLayout()
        basic_layout.setSpacing(10)

        basic_layout.addWidget(QLabel("URL RTSP:"))
        self.rtsp_input = QLineEdit(self.config.get('rtsp_url'))
        self.rtsp_input.setPlaceholderText("rtsp://usuario:senha@ip:porta/caminho")
        basic_layout.addWidget(self.rtsp_input)

        basic_layout.addWidget(QLabel("Modelo YOLO:"))
        
        # Layout para modelo com botão de configuração
        model_layout = QHBoxLayout()
        
        self.modelo_combo = QComboBox()
        self.modelo_combo.addItems([
            'Modelo Padrão (yolo11n.pt)',
            'Modelo Personalizado'
        ])
        self.modelo_combo.currentIndexChanged.connect(self._on_model_selection_changed)

        # Forçar estilo escuro no dropdown (remove fundo branco)
        self.modelo_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)

        # Define modelo atual
        modelo_atual = self.config.get('modelo_yolo', 'yolo11n.pt')
        
        # Bloquear sinais durante inicialização para evitar popup de diálogo
        self.modelo_combo.blockSignals(True)
        
        # Determinar índice e label baseado no modelo salvo
        if 'yolo11n' in modelo_atual:
            self.modelo_combo.setCurrentIndex(0)
            self.modelo_label = QLabel("yolo11n.pt")
            self.selected_model = 'yolo11n.pt'
        else:
            # Modelo personalizado
            self.modelo_combo.setCurrentIndex(1)
            # Exibir caminho do modelo personalizado
            display_name = os.path.basename(modelo_atual) if os.path.isabs(modelo_atual) else modelo_atual
            self.modelo_label = QLabel(display_name)
            self.selected_model = modelo_atual
            
        self.modelo_combo.blockSignals(False)
        
        self.modelo_label.setStyleSheet("color: #888888; font-style: italic;")
        
        model_layout.addWidget(self.modelo_combo)
        model_layout.addWidget(self.modelo_label)
        model_layout.addStretch()
        
        basic_layout.addLayout(model_layout)

        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("Confiança mínima:"))
        self.conf_label = QLabel(f"{int(self.config.get('confianca_minima')*100)}%")
        conf_row.addWidget(self.conf_label)
        conf_row.addStretch()
        basic_layout.addLayout(conf_row)

        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(10, 99)
        self.conf_slider.setValue(int(self.config.get('confianca_minima')*100))
        self.conf_slider.valueChanged.connect(lambda v: self.conf_label.setText(f"{v}%"))
        basic_layout.addWidget(self.conf_slider)

        basic_group.setLayout(basic_layout)
        layout.addWidget(basic_group)

        # GRUPO: Otimização de Desempenho
        perf_group = QGroupBox("Otimização de Desempenho")
        perf_layout = QVBoxLayout()
        perf_layout.setSpacing(10)

        # ROI
        perf_layout.addSpacing(10)
        self.cb_roi = QCheckBox("Ativar Corte de ROI (Remove áreas desnecessárias)")
        self.cb_roi.setChecked(bool(self.config.get('use_roi_crop', False)))
        self.cb_roi.toggled.connect(self.update_roi_preview)
        perf_layout.addWidget(self.cb_roi)

        roi_controls = QWidget()
        roi_controls_layout = QVBoxLayout()
        roi_controls_layout.setSpacing(8)
        roi_controls_layout.setContentsMargins(15, 5, 0, 5)

        # Topo
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Cortar topo:"))
        self.roi_top_label = QLabel(f"{self.config.get('roi_crop',{}).get('top_percent', 0)}%")
        top_row.addWidget(self.roi_top_label)
        top_row.addStretch()
        roi_controls_layout.addLayout(top_row)

        self.roi_top_slider = QSlider(Qt.Horizontal)
        self.roi_top_slider.setRange(0, 50)
        self.roi_top_slider.setValue(int(self.config.get('roi_crop',{}).get('top_percent', 0)))
        self.roi_top_slider.valueChanged.connect(lambda v: (self.roi_top_label.setText(f"{v}%"), self.update_roi_preview()))
        roi_controls_layout.addWidget(self.roi_top_slider)

        # Base
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(QLabel("Cortar base:"))
        self.roi_bot_label = QLabel(f"{self.config.get('roi_crop',{}).get('bottom_percent', 0)}%")
        bottom_row.addWidget(self.roi_bot_label)
        bottom_row.addStretch()
        roi_controls_layout.addLayout(bottom_row)

        self.roi_bot_slider = QSlider(Qt.Horizontal)
        self.roi_bot_slider.setRange(0, 50)
        self.roi_bot_slider.setValue(int(self.config.get('roi_crop',{}).get('bottom_percent', 0)))
        self.roi_bot_slider.valueChanged.connect(lambda v: (self.roi_bot_label.setText(f"{v}%"), self.update_roi_preview()))
        roi_controls_layout.addWidget(self.roi_bot_slider)

        # Esquerda
        left_row = QHBoxLayout()
        left_row.addWidget(QLabel("Cortar esquerda:"))
        self.roi_left_label = QLabel(f"{self.config.get('roi_crop',{}).get('left_percent', 0)}%")
        left_row.addWidget(self.roi_left_label)
        left_row.addStretch()
        roi_controls_layout.addLayout(left_row)

        self.roi_left_slider = QSlider(Qt.Horizontal)
        self.roi_left_slider.setRange(0, 50)
        self.roi_left_slider.setValue(int(self.config.get('roi_crop',{}).get('left_percent', 0)))
        self.roi_left_slider.valueChanged.connect(lambda v: (self.roi_left_label.setText(f"{v}%"), self.update_roi_preview()))
        roi_controls_layout.addWidget(self.roi_left_slider)

        # Direita
        right_row = QHBoxLayout()
        right_row.addWidget(QLabel("Cortar direita:"))
        self.roi_right_label = QLabel(f"{self.config.get('roi_crop',{}).get('right_percent', 0)}%")
        right_row.addWidget(self.roi_right_label)
        right_row.addStretch()
        roi_controls_layout.addLayout(right_row)

        self.roi_right_slider = QSlider(Qt.Horizontal)
        self.roi_right_slider.setRange(0, 50)
        self.roi_right_slider.setValue(int(self.config.get('roi_crop',{}).get('right_percent', 0)))
        self.roi_right_slider.valueChanged.connect(lambda v: (self.roi_right_label.setText(f"{v}%"), self.update_roi_preview()))
        roi_controls_layout.addWidget(self.roi_right_slider)

        # Preview ROI
        self.roi_preview = QLabel()
        self.roi_preview.setFixedHeight(100)
        self.roi_preview.setAlignment(Qt.AlignCenter)
        self.roi_preview.setStyleSheet(Styles.ROI_PREVIEW)
        roi_controls_layout.addWidget(self.roi_preview)
        self.update_roi_preview()

        roi_controls.setLayout(roi_controls_layout)
        perf_layout.addWidget(roi_controls)

        help_label2 = QLabel("↑ Remove bordas desnecessárias para focar na via")
        help_label2.setWordWrap(True)
        help_label2.setStyleSheet(f"color: {ThemeColors.TEXT_TERTIARY}; font-size: 11px; font-style: italic;")
        perf_layout.addWidget(help_label2)

        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)

        # GRUPO: Visualização
        visual_group = QGroupBox("Opções de Visualização")
        visual_layout = QVBoxLayout()
        visual_layout.setSpacing(8)

        self.cb_hide_labels = QCheckBox("Ocultar rótulos (ID e classe)")
        self.cb_hide_labels.setChecked(not bool(self.config.get('show_labels', False)))
        self.cb_hide_labels.toggled.connect(lambda v: self.config.set('show_labels', not v))
        visual_layout.addWidget(self.cb_hide_labels)

        self.cb_hide_lines = QCheckBox("Ocultar linha de contagem")
        self.cb_hide_lines.setChecked(bool(self.config.get('hide_detection_lines', False)))
        self.cb_hide_lines.toggled.connect(lambda v: self.config.set('hide_detection_lines', v))
        visual_layout.addWidget(self.cb_hide_lines)

        self.cb_hide_boxes = QCheckBox("Ocultar caixas de detecção")
        self.cb_hide_boxes.setChecked(bool(self.config.get('hide_detection_boxes', False)))
        self.cb_hide_boxes.toggled.connect(lambda v: self.config.set('hide_detection_boxes', v))
        visual_layout.addWidget(self.cb_hide_boxes)

        visual_group.setLayout(visual_layout)
        layout.addWidget(visual_group)

        # GRUPO: Exportação
        export_group = QGroupBox("Configurações de Exportação")
        export_layout = QVBoxLayout()
        export_layout.setSpacing(10)

        export_layout.addWidget(QLabel("Pasta padrão para relatórios:"))

        folder_row = QHBoxLayout()
        self.export_folder_input = QLineEdit(self.config.get('export_folder', ''))
        self.export_folder_input.setPlaceholderText("Selecione uma pasta...")
        self.export_folder_input.setReadOnly(True)
        folder_row.addWidget(self.export_folder_input)

        self.btn_select_folder = QPushButton()
        self.btn_select_folder.setMinimumSize(50, 45)
        self.btn_select_folder.setMaximumWidth(50)
        self.btn_select_folder.setToolTip("Selecionar pasta")
        # Adicionar ícone PNG ao botão
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'icons', 'pasta.ico')
        if os.path.exists(icon_path):
            self.btn_select_folder.setIcon(QIcon(icon_path))
            self.btn_select_folder.setIconSize(QSize(26, 26))
        # Estilo mais escuro harmonizando com a UI
        self.btn_select_folder.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeColors.SURFACE_LIGHT}, stop:1 {ThemeColors.SURFACE});
                border: 2px solid {ThemeColors.PRIMARY};
                border-radius: 8px;
                padding: 4px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #3d5a7f, stop:1 {ThemeColors.SURFACE_LIGHT});
                border: 2px solid {ThemeColors.PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {ThemeColors.SURFACE}, stop:1 #1a2f4f);
                border: 2px solid {ThemeColors.PRIMARY_PRESSED};
            }}
        """)
        self.btn_select_folder.clicked.connect(self.select_export_folder)
        folder_row.addWidget(self.btn_select_folder)

        export_layout.addLayout(folder_row)

        help_label3 = QLabel("↑ Relatórios serão salvos nesta pasta automaticamente")
        help_label3.setWordWrap(True)
        help_label3.setStyleSheet(f"color: {ThemeColors.TEXT_TERTIARY}; font-size: 11px; font-style: italic;")
        export_layout.addWidget(help_label3)

        export_layout.addSpacing(10)

        # Exportação automática
        auto_export_row = QHBoxLayout()
        auto_export_row.addWidget(QLabel("Exportação automática:"))
        self.auto_export_combo = QComboBox()
        self.auto_export_combo.addItems(["Desativado", "5 min", "10 min", "30 min", "60 min", "Horário Específico"])
        self.auto_export_combo.setMaximumWidth(170)
        self.auto_export_combo.currentIndexChanged.connect(self.update_auto_export)
        self.auto_export_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        auto_export_row.addWidget(self.auto_export_combo)

        # Seletor de horário (inicialmente oculto)
        self.export_time_label = QLabel("às")
        self.export_time_label.setVisible(False)  # Oculto por padrão
        auto_export_row.addWidget(self.export_time_label)

        self.export_time_edit = QTimeEdit()
        self.export_time_edit.setTime(QTime(18, 0))  # Padrão: 18:00
        self.export_time_edit.setDisplayFormat("HH:mm")
        self.export_time_edit.setMaximumWidth(80)
        self.export_time_edit.setToolTip("Horário diário para exportação automática de relatório")
        self.export_time_edit.setVisible(False)  # Oculto por padrão
        auto_export_row.addWidget(self.export_time_edit)

        auto_export_row.addStretch()
        export_layout.addLayout(auto_export_row)

        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        # Botões
        layout.addSpacing(10)
        
        # Botão Iniciar/Parar
        self.btn_start = QPushButton("Iniciar Contagem")
        self.btn_start.setObjectName("startButton")
        self.btn_start.setMinimumHeight(45)
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.btn_start)

        buttons_row1 = QHBoxLayout()
        buttons_row1.setSpacing(10)
        
        self.btn_reset = QPushButton("↻ Resetar")
        self.btn_reset.setMinimumHeight(40)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.clicked.connect(self.reset_counters)
        # Estilo vermelho para indicar ação destrutiva
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #DC3545;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #C82333;
            }
            QPushButton:pressed {
                background-color: #BD2130;
            }
        """)
        buttons_row1.addWidget(self.btn_reset)

        self.btn_export = QPushButton("Exportar")
        self.btn_export.setMinimumHeight(40)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self.export_report)
        buttons_row1.addWidget(self.btn_export)

        layout.addLayout(buttons_row1)

        self.btn_config_roi = QPushButton("Configurar Linha")
        self.btn_config_roi.setMinimumHeight(40)
        self.btn_config_roi.setCursor(Qt.PointingHandCursor)
        self.btn_config_roi.clicked.connect(self.open_roi_config_dialog)
        layout.addWidget(self.btn_config_roi)

        self.btn_help = QPushButton("Ajuda")
        self.btn_help.setMinimumHeight(40)
        self.btn_help.setCursor(Qt.PointingHandCursor)
        self.btn_help.clicked.connect(self.open_help_dialog)
        layout.addWidget(self.btn_help)

        # Log
        layout.addSpacing(10)
        log_header = QHBoxLayout()
        log_label = QLabel("Log do Sistema")
        log_label.setStyleSheet(f"font-weight: bold; color: {ThemeColors.TEXT_SECONDARY};")
        log_header.addWidget(log_label)
        log_header.addSpacing(8)
        self.btn_toggle_log = QPushButton("▲ Ocultar")
        self.btn_toggle_log.setFixedWidth(100)
        self.btn_toggle_log.setFixedHeight(28)
        self.btn_toggle_log.setCursor(Qt.PointingHandCursor)
        self.btn_toggle_log.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {ThemeColors.TEXT_SECONDARY}; "
            f"border: 1px solid {ThemeColors.TEXT_SECONDARY}; border-radius: 4px; font-size: 11px; padding: 0px 6px; }}"
            f"QPushButton:hover {{ color: {ThemeColors.PRIMARY}; border-color: {ThemeColors.PRIMARY}; }}"
        )
        self.btn_toggle_log.clicked.connect(self._toggle_log)
        log_header.addWidget(self.btn_toggle_log)
        log_header.addStretch()
        layout.addLayout(log_header)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(180)
        self.log_text.setMinimumHeight(120)
        layout.addWidget(self.log_text)

        # Status
        layout.addSpacing(10)
        status_layout = QHBoxLayout()
        self.status_label = QLabel("● Offline")
        self.status_label.setObjectName("statusOffline")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        layout.addStretch()
        return panel

    def update_roi_preview(self):
        """Atualiza preview do ROI"""
        enabled = self.cb_roi.isChecked()
        top = self.roi_top_slider.value()
        bottom = self.roi_bot_slider.value()
        left = self.roi_left_slider.value()
        right = self.roi_right_slider.value()
        
        preview_img = QPixmap(320, 180)
        preview_img.fill(QColor("#1e3a5f"))
        
        painter = QPainter(preview_img)
        
        if enabled and (top > 0 or bottom > 0 or left > 0 or right > 0):
            painter.fillRect(0, 0, 320, int(180 * top / 100), QColor("#0a1628"))
            painter.fillRect(0, int(180 * (100 - bottom) / 100), 320, 180, QColor("#0a1628"))
            painter.fillRect(0, 0, int(320 * left / 100), 180, QColor("#0a1628"))
            painter.fillRect(int(320 * (100 - right) / 100), 0, 320, 180, QColor("#0a1628"))
            
            active_top = int(180 * top / 100)
            active_bottom = int(180 * (100 - bottom) / 100)
            active_left = int(320 * left / 100)
            active_right = int(320 * (100 - right) / 100)
            
            painter.fillRect(active_left, active_top, 
                           active_right - active_left, 
                           active_bottom - active_top, 
                           QColor("#3B82F6"))
            
            pen = QPen(QColor("#EF4444"), 2)
            painter.setPen(pen)
            if top > 0:
                painter.drawLine(0, active_top, 320, active_top)
            if bottom > 0:
                painter.drawLine(0, active_bottom, 320, active_bottom)
            if left > 0:
                painter.drawLine(active_left, 0, active_left, 180)
            if right > 0:
                painter.drawLine(active_right, 0, active_right, 180)
            
            painter.setPen(QColor("#FFFFFF"))
            area_h = 100 - top - bottom
            area_w = 100 - left - right
            painter.drawText(10, 95, f"Área ativa: {area_w}% × {area_h}%")
        else:
            painter.fillRect(0, 0, 320, 180, QColor("#10B981"))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(80, 95, "ROI Desativado - Frame completo")
        
        painter.end()
        self.roi_preview.setPixmap(preview_img)

    def create_tabs_panel(self):
        """Cria o painel de abas principal com Navegação Hub & Spoke"""
        self.main_tab_widget = QTabWidget()
        self.main_tab_widget.setObjectName("mainTabs")
        self.main_tab_widget.setStyleSheet(Styles.TAB_WIDGET)

        # =========================================================================
        # 1. MONITORAMENTO (Hub)
        # =========================================================================
        self.monitor_stack = QStackedWidget()
        self.monitor_stack.setMinimumWidth(0) # Permitir encolher totalmente
        self.monitor_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        
        # --- Página 0: Menu ---
        menu_items_mon = [
            ("Visão Geral", "Monitoramento ao vivo das câmeras e contadores.", "app", ThemeColors.PRIMARY, lambda: self.monitor_stack.setCurrentIndex(1)),
            ("Análise", "Gráficos detalhados e estatísticas de fluxo.", "analise", ThemeColors.SECONDARY, lambda: self.monitor_stack.setCurrentIndex(2)),
            ("Histórico", "Logs completos de veículos e eventos.", "historico", ThemeColors.ACCENT, lambda: self.monitor_stack.setCurrentIndex(3))
        ]
        self.monitor_menu = NavigationMenu(menu_items_mon)
        self.monitor_stack.addWidget(self.monitor_menu)
        
        # --- Página 1: Visão Geral (Wrapped) ---
        self.monitoring_view = self.create_monitoring_view_content()
        
        # Wrap in ScrollArea for splitter flexibility
        scroll = QScrollArea()
        scroll.setWidget(self.monitoring_view)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.monitor_stack.addWidget(wrap_with_header(
            scroll, "Visão Geral", "Monitoramento em Tempo Real", 
            lambda: self.monitor_stack.setCurrentIndex(0)
        ))
        
        # --- Página 2: Dashboard (Wrapped) ---
        self.dashboard_tab = DashboardTab(self.database, self.config, self)
        self.monitor_stack.addWidget(wrap_with_header(
            self.dashboard_tab, "Análise", "Dashboard de Métricas", 
            lambda: self.monitor_stack.setCurrentIndex(0)
        ))
        
        # --- Página 3: Histórico (Wrapped) ---
        self.history_tab = HistoryTab(self.database, self.config, self)
        self.monitor_stack.addWidget(wrap_with_header(
            self.history_tab, "Histórico", "Registro de Eventos", 
            lambda: self.monitor_stack.setCurrentIndex(0)
        ))
        
        # Conectar mudança de página no monitoramento para controlar painel lateral
        self.monitor_stack.currentChanged.connect(lambda i: self._update_left_panel_visibility())
        
        self.main_tab_widget.addTab(self.monitor_stack, "Monitoramento")

        # =========================================================================
        # 2. TEMPO DE FILA (Hub)
        # =========================================================================
        self.queue_stack = QStackedWidget()
        
        # --- Página 0: Menu ---
        menu_items_queue = [
            ("Monitoramento Fila", "Visualização da fila com timers e heatmaps.", "tempofila", ThemeColors.WARNING, lambda: self.queue_stack.setCurrentIndex(1)),
            ("Relatórios", "Histórico de tempos de espera e exportação.", "relatoriofila", ThemeColors.SUCCESS, lambda: (self.queue_reports.refresh_data(), self.queue_stack.setCurrentIndex(2))),
            ("Análise", "Gráficos de tendência e distribuição dos tempos de espera.", "analise", ThemeColors.SECONDARY, lambda: (self.queue_analysis.refresh_data(), self.queue_stack.setCurrentIndex(3))),
        ]
        self.queue_menu = NavigationMenu(menu_items_queue)
        self.queue_stack.addWidget(self.queue_menu)

        # --- Página 1: Queue Tab (Wrapped) ---
        self.queue_tab = QueueTab(self.config, self)
        self.queue_stack.addWidget(wrap_with_header(
            self.queue_tab, "Tempo de Fila", "Monitoramento ao Vivo",
            lambda: self.queue_stack.setCurrentIndex(0)
        ))

        # --- Página 2: Relatórios (Wrapped) ---
        self.queue_reports = QueueReportsTab(self, self)
        self.queue_stack.addWidget(wrap_with_header(
            self.queue_reports, "Relatórios de Fila", "Histórico da Sessão",
            lambda: self.queue_stack.setCurrentIndex(0)
        ))

        # --- Página 3: Análise (Wrapped) ---
        self.queue_analysis = QueueAnalysisTab(self, self)
        self.queue_stack.addWidget(wrap_with_header(
            self.queue_analysis, "Análise de Fila", "Gráficos e Estatísticas",
            lambda: self.queue_stack.setCurrentIndex(0)
        ))
        
        self.main_tab_widget.addTab(self.queue_stack, "Tempo de Fila")

        return self.main_tab_widget

    def create_monitoring_view_content(self):
        """Cria o conteúdo da visão geral (antigo create_monitoring_tab sem o wrapper)"""
        panel = QFrame()
        panel.setObjectName("rightPanel")
        panel.setMinimumWidth(0) # Permitir encolher
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header - Simplificado e compacto
        header = QFrame()
        header.setObjectName("totalFrame")
        header.setMinimumHeight(75)
        hbox = QHBoxLayout(header)
        hbox.setSpacing(20)
        hbox.setContentsMargins(16, 12, 16, 12)

        # Total (mais compacto)
        total_layout = QVBoxLayout()
        total_layout.setSpacing(2)
        total_title = QLabel("Total")
        total_title.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; font-weight: 600;")
        total_layout.addWidget(total_title)

        self.total_label = QLabel("0")
        self.total_label.setObjectName("totalCount")
        self.total_label.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 42px; font-weight: 900;")
        total_layout.addWidget(self.total_label)
        hbox.addLayout(total_layout)

        hbox.addStretch()

        # Ida e Volta (horizontal, mais compacto)
        dir_layout = QHBoxLayout()
        dir_layout.setSpacing(24)

        # Ida
        ida_layout = QVBoxLayout()
        ida_layout.setSpacing(2)
        ida_title = QLabel("↑ Ida")
        ida_title.setStyleSheet(f"color: {ThemeColors.SUCCESS}; font-size: 12px; font-weight: 600;")
        ida_layout.addWidget(ida_title)
        self.ida_total_label = QLabel("0")
        self.ida_total_label.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 28px; font-weight: 700;")
        ida_layout.addWidget(self.ida_total_label)
        dir_layout.addLayout(ida_layout)

        # Volta
        volta_layout = QVBoxLayout()
        volta_layout.setSpacing(2)
        volta_title = QLabel("↓ Volta")
        volta_title.setStyleSheet(f"color: {ThemeColors.DANGER}; font-size: 12px; font-weight: 600;")
        volta_layout.addWidget(volta_title)
        self.volta_total_label = QLabel("0")
        self.volta_total_label.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 28px; font-weight: 700;")
        volta_layout.addWidget(self.volta_total_label)
        dir_layout.addLayout(volta_layout)

        hbox.addLayout(dir_layout)
        layout.addWidget(header)

        # Cards
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)
        
        self.category_cards = {}
        categories = [
            ('Carros','#0d9488','carro'),
            ('Motos','#8b5cf6','moto'),
            ('Caminhões','#dc2626','caminhao'),
            ('Ônibus','#f59e0b','onibus')
        ]
        
        for idx, (cat, color, icon) in enumerate(categories):
            card = self.create_category_card(cat, color, icon)
            self.category_cards[cat] = card
            grid.addWidget(card, 0, idx)
        
        layout.addLayout(grid)

        # Espaçamento
        layout.addSpacing(8)

        # Título do vídeo (com ícone)
        title_container = QHBoxLayout()
        title_container.setSpacing(6)
        camera_icon = self.create_icon_label('camera', size=18)
        title_container.addWidget(camera_icon)
        video_title = QLabel("Visualização da Câmera")
        video_title.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 14px; font-weight: 600;")
        title_container.addWidget(video_title)
        title_container.addStretch()
        title_widget = QWidget()
        title_widget.setLayout(title_container)
        title_widget.setStyleSheet("padding: 12px 0 8px 0;")
        layout.addWidget(title_widget)

        # Vídeo
        # Vídeo
        self.video_container = QFrame()
        self.video_container.setObjectName("videoFrame")
        self.video_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_container.setMinimumWidth(0)
        # self.video_container.setMinimumHeight(400) # Removido para flexibilidade

        v_layout = QVBoxLayout(self.video_container)
        v_layout.setContentsMargins(0, 0, 0, 0)

        self.video_placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self.video_placeholder)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        placeholder_layout.setContentsMargins(30, 30, 30, 30)

        icon = self.create_icon_label('camera', size=64)
        icon.setAlignment(Qt.AlignCenter)
        placeholder_layout.addWidget(icon)

        txt = QLabel("Clique em\nINICIAR\npara monitorar")
        txt.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; line-height: 1.6;")
        txt.setAlignment(Qt.AlignCenter)
        txt.setWordWrap(True)
        placeholder_layout.addWidget(txt, alignment=Qt.AlignCenter)

        v_layout.addWidget(self.video_placeholder)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.video_label.setScaledContents(False)
        self.video_label.setStyleSheet("background-color: #000; border-radius: 8px;")
        self.video_label.hide()
        v_layout.addWidget(self.video_label)

        layout.addWidget(self.video_container, 1)
        
        return panel

    def create_category_card(self, categoria, color, icon):
        card = QFrame()
        card.setObjectName("categoryCard")
        # Usar estilo dinâmico centralizado
        card.setStyleSheet(Styles.get_card_style(color))
        card.setMinimumSize(110, 100)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QVBoxLayout(card)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(4)
        lay.setContentsMargins(10, 10, 10, 10)

        head = QHBoxLayout()
        head.setSpacing(4)
        icon_label = self.create_icon_label(icon, size=32)
        icon_label.setAlignment(Qt.AlignVCenter)
        head.addWidget(icon_label)

        title = QLabel(categoria)
        title.setObjectName("cardTitle")
        title.setStyleSheet("background: transparent; border: none;")
        head.addWidget(title)
        head.addStretch()
        lay.addLayout(head)

        count = QLabel("0")
        count.setObjectName("cardCount")
        count.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(count)

        dir_lay = QHBoxLayout()
        dir_lay.setSpacing(10)

        ida = QLabel("↑ 0")
        ida.setObjectName("cardDirection")
        ida.setStyleSheet("background: transparent; border: none; font-size: 14px; font-weight: 600;")
        dir_lay.addWidget(ida)

        volta = QLabel("↓ 0")
        volta.setObjectName("cardDirection")
        volta.setStyleSheet("background: transparent; border: none; font-size: 14px; font-weight: 600;")
        dir_lay.addWidget(volta)
        
        lay.addLayout(dir_lay)
        
        card.count_label = count
        card.ida_label = ida
        card.volta_label = volta
        
        return card

    def validate_rtsp_url(self, url):
        """
        CORRIGIDO: Valida URL RTSP antes de tentar conectar

        Args:
            url: URL RTSP para validar

        Returns:
            True se válida, False caso contrário
        """
        from PyQt5.QtWidgets import QMessageBox

        # URL vazia ou padrão
        if not url or url == 'rtsp://usuario:senha@ip:porta/caminho':
            QMessageBox.warning(
                self,
                "URL RTSP Inválida",
                "Por favor, configure uma URL RTSP válida.\n\n"
                "Formato esperado:\n"
                "rtsp://usuario:senha@ip:porta/caminho\n\n"
                "Exemplo:\n"
                "rtsp://admin:123456@192.168.1.100:554/stream"
            )
            self.rtsp_input.setFocus()
            return False

        # Validar protocolo
        if not url.startswith('rtsp://') and not url.startswith('http://') and not str(url).isdigit():
            QMessageBox.warning(
                self,
                "URL RTSP Inválida",
                f"URL deve começar com 'rtsp://' ou 'http://'\n"
                f"(ou ser um número para webcam)\n\n"
                f"URL fornecida: {url}"
            )
            self.rtsp_input.setFocus()
            return False

        # Validar formato básico de URL RTSP
        if url.startswith('rtsp://'):
            # Verificar se tem formato mínimo válido
            if url.count('@') > 0:
                # Tem credenciais - validar formato usuario:senha@ip
                if url.count(':') < 2:
                    QMessageBox.warning(
                        self,
                        "URL RTSP Inválida",
                        "Formato de credenciais inválido.\n\n"
                        "Formato esperado:\n"
                        "rtsp://usuario:senha@ip:porta/caminho"
                    )
                    self.rtsp_input.setFocus()
                    return False

        return True

    def _on_model_selection_changed(self, index):
        """Manipula mudança de seleção de modelo"""
        if index == 0:
            # Modelo padrão: yolo11n.pt
            self.modelo_label.setText("yolo11n.pt")
            self.selected_model = 'yolo11n.pt'
        elif index == 1:
            # Modelo personalizado: abrir diálogo
            current_model = self.config.get('modelo_yolo', 'yolo11n.pt')
            
            # Se o modelo atual não é o padrão, usá-lo como base para o diálogo
            if 'yolo11n' not in current_model:
                dialog = PersonalizedModelDialog(self, current_model)
            else:
                dialog = PersonalizedModelDialog(self, None)
            
            if dialog.exec_() == QDialog.Accepted:
                self.selected_model = dialog.get_selected_model()
                if self.selected_model:
                    # Mostrar nome do arquivo no label
                    display_name = os.path.basename(self.selected_model)
                    self.modelo_label.setText(display_name)
                    # ADICIONADO: Persistir imediatamente ao selecionar
                    self.config.set('modelo_yolo', self.selected_model)
                else:
                    # Se o usuário cancelou, voltar para o padrão
                    self.modelo_combo.blockSignals(True)
                    self.modelo_combo.setCurrentIndex(0)
                    self.modelo_label.setText("yolo11n.pt")
                    self.selected_model = 'yolo11n.pt'
                    self.modelo_combo.blockSignals(False)
            else:
                # Usuário cancelou o diálogo, voltar para seleção anterior
                self.modelo_combo.blockSignals(True)
                self.modelo_combo.setCurrentIndex(0)
                self.modelo_label.setText("yolo11n.pt")
                self.selected_model = 'yolo11n.pt'
                self.modelo_combo.blockSignals(False)

    def toggle_monitoring(self):
        # Passo 1: Iniciar Thread se necessário
        if self.video_thread is None or not self.video_thread.running:
            # Salva configurações
            rtsp_url = self.rtsp_input.text().strip()

            # CORRIGIDO: Validar URL antes de continuar
            if not self.validate_rtsp_url(rtsp_url):
                return  # Não iniciar se URL inválida

            self.config.set('rtsp_url', rtsp_url)

            # Usar o modelo selecionado (armazenado em self.selected_model)
            modelo_selecionado = getattr(self, 'selected_model', 'yolo11n.pt')
            self.add_log(f"[DEBUG] Iniciando com modelo: {modelo_selecionado}")
            self.config.set('modelo_yolo', modelo_selecionado)
            
            # Verificação imediata do que foi salvo
            salvo = self.config.get('modelo_yolo')
            if salvo != modelo_selecionado:
                self.add_log(f"[ERRO] Falha ao salvar config! Salvo: {salvo}")

            self.config.set('tracker', 'bytetrack.yaml')  # Sempre usar ByteTrack
            self.config.set('confianca_minima', self.conf_slider.value()/100.0)

            # Desempenho
            self.config.set('use_roi_crop', bool(self.cb_roi.isChecked()))

            roi_crop = {
                'top_percent': int(self.roi_top_slider.value()),
                'bottom_percent': int(self.roi_bot_slider.value()),
                'left_percent': int(self.roi_left_slider.value()),
                'right_percent': int(self.roi_right_slider.value())
            }
            self.config.set('roi_crop', roi_crop)

            # Visualização
            self.config.set('counting_mode', 'line')  # Sempre usar linha
            self.config.set('show_labels', not bool(self.cb_hide_labels.isChecked()))
            self.config.set('hide_detection_lines', bool(self.cb_hide_lines.isChecked()))

            # Exportação
            self.config.set('export_folder', self.export_folder_input.text())

            # Armazenar link RTSP atual
            self.current_rtsp_url = rtsp_url

            # Atualizar abas com o novo RTSP URL
            self.history_tab.set_rtsp_url(rtsp_url)
            self.dashboard_tab.set_rtsp_url(rtsp_url)

            # Carregar contadores DESTE link RTSP específico
            saved_counters = self.database.load_counters(rtsp_url=rtsp_url)
            total = sum(saved_counters['total'].values())
            if total > 0:
                self.add_log(f"Restaurados {total} veículos contados anteriormente neste link")
                # Atualizar interface com contadores carregados
                self.update_counters(saved_counters)

            # Inicia thread (com banco de dados E link RTSP para persistir contagens)
            self.video_thread = VideoThread(self.config, database=self.database, rtsp_url=rtsp_url)
            self.video_thread.change_pixmap_signal.connect(self.update_video)
            self.video_thread.update_counters.connect(self.update_counters)
            self.video_thread.update_status.connect(self.update_status)
            self.video_thread.log_message.connect(self.add_log)
            
            self.video_thread.start()

        # Passo 2: Alternar Estado de Monitoramento
        # Se estava ativo, desativa. Se inativo, ativa.
        # Porém, precisamos saber o estado ATUAL.
        # Ao criar a thread, ambos nascem False.
        
        new_state = not self.video_thread.monitoring_active
        self.video_thread.set_monitoring_active(new_state)

        # Passo 3: Atualizar Interface
        if new_state:
            self.btn_start.setText("Parar Contagem")
            self.btn_start.setStyleSheet(Styles.BUTTON_PRIMARY.replace(ThemeColors.PRIMARY, ThemeColors.DANGER))
            self.add_log("Sistema iniciado")
        else:
            self.btn_start.setText("Iniciar Contagem")
            self.btn_start.setStyleSheet(Styles.BUTTON_PRIMARY)
            
        # Passo 4: Verificar se devemos parar a thread completamente
        # (Apenas se ambos estiverem parados)
        if not new_state and not self.video_thread.queue_active:
            # Parada não-bloqueante: sinaliza stop e faz cleanup em daemon thread.
            # NÃO usa terminate() — mata thread em C-code (YOLO) e causa crash.
            # cleanup() (cap.release → join 8s) roda em daemon thread Python,
            # nunca na UI thread.
            thread = self.video_thread
            self.video_thread = None
            thread.running = False
            thread._stop_requested.set()
            if not hasattr(self, '_dying_threads'):
                self._dying_threads = []
            self._dying_threads.append(thread)
            def _bg_cleanup(t=thread):
                import threading as _th
                def _do():
                    try:
                        t.cleanup()
                    except Exception:
                        pass
                    try:
                        self._dying_threads.remove(t)
                    except (ValueError, AttributeError):
                        pass
                t.finished.connect(lambda: _th.Thread(target=_do, daemon=True).start())
            _bg_cleanup()
            self.video_label.hide()
            self.video_label.clear()
            self.video_placeholder.show()
            self.add_log("Sistema parado")
        elif not new_state:
            self.add_log("Contagem pausada. Câmera continua ativa.")

    def update_video(self, image: QImage):
        if self.video_placeholder.isVisible():
            self.video_placeholder.hide()
            self.video_label.show()
        
        pixmap = QPixmap.fromImage(image)
        container_w = self.video_container.width()
        container_h = self.video_container.height()
        scaled = pixmap.scaled(container_w, container_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'video_label') and self.video_label.pixmap() and not self.video_label.pixmap().isNull():
            pixmap = self.video_label.pixmap()
            container_w = self.video_container.width()
            container_h = self.video_container.height()
            scaled = pixmap.scaled(container_w, container_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.video_label.setPixmap(scaled)

    def is_shutting_down(self):
        """Verifica se o sistema está encerrando (thread-safe)"""
        with self._shutdown_lock:
            return self._is_closing

    def closeEvent(self, event):
        """
        🔒 SHUTDOWN SEGURO COM PROTEÇÃO CONTRA RACE CONDITIONS
        Encerramento ordenado: timers → thread → banco → aceitar evento
        """
        with self._shutdown_lock:
            if self._is_closing:
                # Já estamos encerrando, evitar duplicação
                event.accept()
                return
            
            self._is_closing = True
        
        try:
            print("\\n[SHUTDOWN] Iniciando encerramento seguro do sistema...")
            
            # ETAPA 1: Parar todos os timers (essencial fazer isso ANTES de parar threads)
            print("[SHUTDOWN] Parando timers...")
            try:
                self.export_timer.stop()
                self.export_schedule_timer.stop()
                # Parar timers do relatório de fila
                if hasattr(self, 'queue_reports') and self.queue_reports:
                    self.queue_reports.stop_timers()
            except Exception as e:
                print(f"[AVISO] Erro ao parar timers: {e}")
            
            # ETAPA 2: Parar a thread de vídeo se estiver rodando
            if self.video_thread and self.video_thread.running:
                print("[SHUTDOWN] Encerrando thread de vídeo...")
                try:
                    self.video_thread.stop()  # Sinaliza para parar
                    
                    # Aguardar com timeout (máximo 5 segundos)
                    if not self.video_thread.wait(5000):
                        print("[AVISO] Thread não respondeu no timeout - forçando terminate")
                        self.video_thread.terminate()
                        self.video_thread.wait(2000)  # Aguardar mais 2s
                    else:
                        print("[SHUTDOWN] Thread de vídeo encerrada com sucesso")
                except Exception as e:
                    print(f"[ERRO] Falha ao parar thread: {e}")
            
            # ETAPA 3: Cleanup da thread
            if self.video_thread:
                try:
                    self.video_thread.cleanup()
                    print("[SHUTDOWN] Cleanup da thread concluído")
                except Exception as e:
                    print(f"[AVISO] Erro no cleanup: {e}")
            
            # ETAPA 4: Fechar banco de dados
            if self.database:
                try:
                    # Tentar salvar contadores uma última vez
                    if self.video_thread and hasattr(self.video_thread, 'counter'):
                        self.video_thread.counter.save_to_database()
                        print("[SHUTDOWN] Contadores salvos no banco")
                except Exception as e:
                    print(f"[AVISO] Erro ao salvar contadores: {e}")
                
                try:
                    self.database.close()
                    print("[SHUTDOWN] Banco de dados fechado")
                except Exception as e:
                    print(f"[AVISO] Erro ao fechar banco: {e}")
            
            print("[SHUTDOWN] Encerramento completo - saindo\\n")
            event.accept()
            
        except Exception as e:
            print(f"[ERRO CRÍTICO] Falha no closeEvent: {e}")
            import traceback
            traceback.print_exc()
            event.accept()  # Aceitar mesmo com erro para evitar travamento

    def update_counters(self, contadores):
        total = contadores['total']['ida'] + contadores['total']['volta']
        self.total_label.setText(str(total))
        self.ida_total_label.setText(f"{contadores['total']['ida']}")
        self.volta_total_label.setText(f"{contadores['total']['volta']}")
        
        for cat, card in self.category_cards.items():
            if cat in contadores:
                tot = contadores[cat]['ida'] + contadores[cat]['volta']
                card.count_label.setText(str(tot))
                card.ida_label.setText(f"↑ {contadores[cat]['ida']}")
                card.volta_label.setText(f"↓ {contadores[cat]['volta']}")



    def update_status(self, status):
        if status == "Online":
            self.status_label.setText("● Online")
            self.status_label.setObjectName("statusOnline")
        else:
            self.status_label.setText(f"● {status}")
            self.status_label.setObjectName("statusOffline")
        
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _toggle_log(self):
        if self.log_text.isVisible():
            self.log_text.hide()
            self.btn_toggle_log.setText("▼ Mostrar")
        else:
            self.log_text.show()
            self.btn_toggle_log.setText("▲ Ocultar")

    def add_log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{ts}] {message}")

    # CORRIGIDO: Método load_saved_counters() removido (código morto)
    # Contadores são carregados automaticamente ao iniciar detecção, baseados no link RTSP

    def reset_counters(self):
        """MELHORADO: Reseta contadores OU banco de dados com opções para o usuário"""
        total = 0
        if self.video_thread and self.video_thread.running:
            total = self.video_thread.counter.get_total()

        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QRadioButton, QDialogButtonBox

        dialog = QDialog(self)
        dialog.setWindowTitle("Opções de Reset")
        dialog.setMinimumWidth(480)
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: {ThemeColors.BACKGROUND};
            }}
            QLabel {{
                color: {ThemeColors.TEXT_PRIMARY};
                background: transparent;
            }}
            QRadioButton {{
                color: {ThemeColors.TEXT_PRIMARY};
                background: transparent;
                font-size: 13px;
                font-weight: bold;
            }}
            QRadioButton::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 8px;
                border: 2px solid {ThemeColors.BORDER};
                background: {ThemeColors.SURFACE};
            }}
            QRadioButton::indicator:checked {{
                border: 2px solid {ThemeColors.PRIMARY};
                background: {ThemeColors.PRIMARY};
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        icon_lbl = QLabel("⚠")
        icon_lbl.setStyleSheet(f"font-size: 26px; color: {ThemeColors.WARNING}; padding-right: 4px;")
        header_row.addWidget(icon_lbl)
        header_row.addSpacing(6)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        lbl_title = QLabel("Opções de Reset")
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY};")
        lbl_sub = QLabel("Escolha o tipo de reset a ser aplicado")
        lbl_sub.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")
        titles.addWidget(lbl_title)
        titles.addWidget(lbl_sub)
        header_row.addLayout(titles)
        header_row.addStretch()
        layout.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {ThemeColors.BORDER};")
        layout.addWidget(sep)

        # Card opção 1 — segura
        card1 = QFrame()
        card1.setStyleSheet(f"""
            QFrame {{
                background-color: {ThemeColors.SURFACE};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 8px;
            }}
        """)
        c1 = QVBoxLayout(card1)
        c1.setContentsMargins(14, 12, 14, 12)
        c1.setSpacing(5)
        self.radio_reset_counter = QRadioButton(f"Resetar monitoramento atual  ({total} veículos)")
        self.radio_reset_counter.setChecked(True)
        c1.addWidget(self.radio_reset_counter)
        for line in [
            "• Zera contadores da sessão atual (em memória)",
            "• Limpa IDs de tracking ativos",
            "• Dashboard e Histórico NÃO são afetados",
            "• Dados salvos permanecem intactos",
        ]:
            l = QLabel(line)
            l.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY}; padding-left: 20px; font-weight: normal;")
            c1.addWidget(l)
        layout.addWidget(card1)

        # Card opção 2 — destrutiva
        card2 = QFrame()
        card2.setStyleSheet(f"""
            QFrame {{
                background-color: #150808;
                border: 1px solid {ThemeColors.DANGER};
                border-radius: 8px;
            }}
        """)
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(14, 12, 14, 12)
        c2.setSpacing(5)
        self.radio_reset_database = QRadioButton("Resetar TUDO (Banco de Dados + Monitoramento)")
        self.radio_reset_database.setStyleSheet(f"color: {ThemeColors.DANGER}; font-weight: bold;")
        self.radio_reset_database.setProperty("danger", True)
        c2.addWidget(self.radio_reset_database)

        # Garante exclusão mútua (radio buttons em QFrames diferentes não se agrupam automaticamente)
        _btn_group = QButtonGroup(dialog)
        _btn_group.addButton(self.radio_reset_counter)
        _btn_group.addButton(self.radio_reset_database)

        for line in [
            "• APAGA Dashboard (gráficos e estatísticas)",
            "• APAGA Histórico (todas as detecções)",
            "• APAGA Monitoramento (contagem atual)",
            "• AÇÃO IRREVERSÍVEL — Volta ao zero total!",
        ]:
            l = QLabel(line)
            l.setStyleSheet("font-size: 12px; color: #f87171; padding-left: 20px; font-weight: normal;")
            c2.addWidget(l)
        layout.addWidget(card2)

        # Botões
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Confirmar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.button(QDialogButtonBox.Ok).setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.DANGER};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 22px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: #c0392b; }}
        """)
        buttons.button(QDialogButtonBox.Cancel).setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.SURFACE_LIGHT};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 6px;
                padding: 8px 22px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {ThemeColors.BORDER}; }}
        """)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setLayout(layout)

        if dialog.exec_() == QDialog.Accepted:
            if self.radio_reset_counter.isChecked():
                self._reset_counter_only(total)
            elif self.radio_reset_database.isChecked():
                self._reset_database_only()
        else:
            self.add_log("Reset cancelado pelo usuário")

    def _reset_counter_only(self, total):
        """Reseta apenas os contadores em memória (não afeta banco de dados)"""
        if self.video_thread and self.video_thread.running:
            # Confirmação adicional
            reply = QMessageBox.question(
                self,
                "Confirmar Reset de Monitoramento",
                f"Resetar apenas o monitoramento atual?\n\n"
                f"O QUE VAI SER ZERADO:\n"
                f"• Contadores da tela principal: {total} veículos\n"
                f"• IDs de tracking ativos\n\n"
                f"O QUE NÃO VAI SER AFETADO:\n"
                f"✓ Dashboard (gráficos e estatísticas)\n"
                f"✓ Histórico (todas as detecções salvas)\n"
                f"✓ Banco de dados (permanece intacto)\n\n"
                f"Continuar?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.video_thread.counter.reset()
                self.video_thread.track_last_center.clear()
                self.video_thread.track_last_center_xy.clear()
                self.video_thread.track_counted.clear()
                self.video_thread.track_last_zone.clear()
                self.video_thread.track_last_event_time.clear()
                self.video_thread.track_last_seen.clear()
                self.add_log("Monitoramento resetado (Dashboard/Histórico preservados)")
                QMessageBox.information(
                    self,
                    "Reset Concluído",
                    f"Monitoramento resetado com sucesso!\n\n"
                    f"Zerado:\n"
                    f"• {total} veículos da contagem atual\n\n"
                    f"Preservado:\n"
                    f"• Dashboard continua com gráficos\n"
                    f"• Histórico continua com detecções\n"
                    f"• Banco de dados intacto"
                )
            else:
                self.add_log("Reset de contagem cancelado")
        else:
            QMessageBox.information(
                self,
                "Sistema Inativo",
                "O sistema precisa estar em execução para resetar contadores.\n\n"
                "Clique em 'Iniciar Sistema' primeiro."
            )

    def _reset_database_only(self):
        """Reseta TODO o banco de dados (apaga todos registros históricos)"""
        # Confirmação com senha de segurança
        from PyQt5.QtWidgets import QInputDialog

        # Primeira confirmação
        reply = QMessageBox.warning(
            self,
            "ATENÇÃO: Reset do Banco de Dados",
            "Você está prestes a APAGAR PERMANENTEMENTE:\n\n"
            "• TODOS os registros históricos\n"
            "• TODOS os contadores salvos\n"
            "• TODOS os dados de todas as câmeras\n\n"
            "Esta ação é IRREVERSÍVEL e NÃO pode ser desfeita!\n\n"
            "Deseja realmente continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.No:
            self.add_log("Reset do banco de dados cancelado")
            return

        # Segunda confirmação com digitação
        confirmation, ok = QInputDialog.getText(
            self,
            "Confirmação Final",
            "Para confirmar, digite exatamente:\nAPAGAR TUDO"
        )

        if not ok or confirmation != "APAGAR TUDO":
            self.add_log("Reset do banco de dados cancelado (confirmação incorreta)")
            QMessageBox.information(
                self,
                "Cancelado",
                "Reset do banco de dados cancelado.\n\nTexto de confirmação incorreto."
            )
            return

        # Executar reset do banco
        try:
            self.add_log("Iniciando limpeza COMPLETA (memória + banco)...")

            # Se houver thread rodando, usar reset_all() que limpa TUDO
            if self.video_thread and self.video_thread.running:
                # CORRIGIDO: Usar reset_all() ao invés de reset()
                self.video_thread.counter.reset_all()  # Limpa memória E banco
                self.video_thread.track_last_center.clear()
                self.video_thread.track_last_center_xy.clear()
                self.video_thread.track_counted.clear()
                self.video_thread.track_last_zone.clear()
                self.video_thread.track_last_event_time.clear()
                self.video_thread.track_last_seen.clear()
            else:
                # Se não estiver rodando, limpar banco diretamente
                self.database.clear_all()

            self.add_log("Banco de dados resetado completamente!")

            QMessageBox.information(
                self,
                "Reset Concluído",
                "Banco de dados resetado com sucesso!\n\n"
                "• Todos os registros históricos foram apagados\n"
                "• Todos os contadores foram zerados\n"
                "• Sistema pronto para começar do zero"
            )

        except Exception as e:
            self.add_log(f"Erro ao resetar banco de dados: {e}")
            QMessageBox.critical(
                self,
                "Erro",
                f"Falha ao resetar banco de dados:\n\n{str(e)}"
            )

    def export_report(self):
        try:
            import pandas as pd
            # Se o sistema está rodando, usar contador da thread; senão, carregar do banco
            if self.video_thread is not None and self.video_thread.running:
                counter = self.video_thread.counter
            else:
                # Criar um counter temporário e carregar dados do banco (com link RTSP atual)
                counter = VehicleCounter(database=self.database, rtsp_url=self.current_rtsp_url)

            dados = []

            for cat in ['Carros','Motos','Caminhões','Ônibus']:
                dados.append({
                    'Categoria': cat,
                    'Ida': counter.contadores[cat]['ida'],
                    'Volta': counter.contadores[cat]['volta'],
                    'Total': counter.contadores[cat]['ida'] + counter.contadores[cat]['volta']
                })

            dados.append({
                'Categoria': 'TOTAL',
                'Ida': counter.contadores['total']['ida'],
                'Volta': counter.contadores['total']['volta'],
                'Total': counter.get_total()
            })

            # Diálogo para escolher onde salvar
            default_filename = f"relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Salvar Relatório",
                default_filename,
                "Excel Files (*.xlsx);;All Files (*)"
            )

            if not filename:  # Usuário cancelou
                return

            # Adicionar extensão .xlsx se não tiver
            if not filename.endswith('.xlsx'):
                filename += '.xlsx'

            df = pd.DataFrame(dados)

            # Exportar com auto-ajuste de largura das colunas
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Relatório')

                # Ajustar largura das colunas automaticamente
                worksheet = writer.sheets['Relatório']
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter

                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass

                    # Adicionar margem de 2 caracteres
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width

            self.add_log(f"Relatório exportado: {filename}")
            QMessageBox.information(self, "Sucesso", f"Relatório exportado com sucesso!\n\n{filename}")
        except Exception as e:
            self.add_log(f"Erro ao exportar: {e}")
            QMessageBox.critical(self, "Erro", f"Falha ao exportar relatório:\n{e}")

    def open_roi_config_dialog(self):
        if self.video_thread is None:
            QMessageBox.information(self, "Info", "É necessário iniciar o sistema primeiro para configurar a linha.\n\nInicie o monitoramento e tente novamente.")
            return

        if self.video_thread.last_frame is None:
             QMessageBox.warning(self, "Aguardando Frame", "Aguardando captura do primeiro frame de vídeo...\n\nTente novamente em alguns segundos.")
             return

        dlg = ROIConfigDialog(self.video_thread, self.config, self)
        if dlg.exec_() == QDialog.Accepted:
            self.config.set('counting_mode', 'line')  # Sempre usar linha
            self.config.set('line_config', dlg.line_config)
            self.add_log("Configuração de Linha salva com sucesso")

    def open_help_dialog(self):
        """Abre diálogo de ajuda com explicações das funções"""
        dlg = HelpDialog(self)
        dlg.exec_()

    def select_export_folder(self):
        """Abre diálogo para selecionar pasta padrão de exportação"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta para Exportação",
            self.export_folder_input.text() or os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly
        )

        if folder:
            self.export_folder_input.setText(folder)
            self.config.set('export_folder', folder)
            self.add_log(f"Pasta de exportação definida: {folder}")

    def update_auto_export(self, index):
        """Atualiza intervalo de exportação automática"""
        # Parar timers atuais
        self.export_timer.stop()
        self.export_schedule_timer.stop()

        # Ocultar seletor de horário por padrão
        self.export_time_label.setVisible(False)
        self.export_time_edit.setVisible(False)

        # Configurar novo intervalo baseado na seleção
        intervals = {
            0: 0,           # Desativado
            1: 5 * 60000,   # 5 minutos
            2: 10 * 60000,  # 10 minutos
            3: 30 * 60000,  # 30 minutos
            4: 60 * 60000   # 60 minutos
        }

        # Opção 5: Horário Específico
        if index == 5:
            self.export_time_label.setVisible(True)
            self.export_time_edit.setVisible(True)
            self.export_schedule_timer.start()
            scheduled_time = self.export_time_edit.time().toString("HH:mm")
            self.add_log(f"Exportação automática agendada para: {scheduled_time}")
            return

        interval = intervals.get(index, 0)

        if interval > 0:
            self.export_timer.start(interval)
            minutes = interval // 60000
            self.add_log(f"Exportação automática ativada: {minutes} minutos")
        else:
            self.add_log("Exportação automática desativada")

    def check_scheduled_export(self):
        """
        Verifica se chegou o horário configurado para exportação diária.
        Executa apenas uma vez por dia no horário especificado.
        """
        now = datetime.now()
        current_time = now.time()
        current_date = now.date()

        # Obter horário configurado
        scheduled_time = self.export_time_edit.time().toPyTime()

        # DEBUG: Sempre mostra verificação (comentar depois se quiser)
        print(f"[DEBUG] Verificando exportação agendada - Atual: {current_time.strftime('%H:%M:%S')}, "
              f"Agendado: {scheduled_time.strftime('%H:%M')}, "
              f"Última exportação: {self.last_scheduled_export_date}")

        # Calcular horários em minutos desde meia-noite
        current_minutes = current_time.hour * 60 + current_time.minute
        scheduled_minutes = scheduled_time.hour * 60 + scheduled_time.minute

        # CORRIGIDO: Verifica se já passou do horário agendado E ainda não exportou hoje
        # Permite uma janela de 2 minutos para garantir que não perca o horário
        time_to_export = (current_minutes >= scheduled_minutes and
                         current_minutes <= scheduled_minutes + 2)

        if time_to_export and self.last_scheduled_export_date != current_date:
            print(f"[INFO] Horário de exportação atingido: {scheduled_time.strftime('%H:%M')}")
            self.auto_export_report()
            self.last_scheduled_export_date = current_date  # Marca como exportado hoje
            print(f"[INFO] Próxima exportação: amanhã às {scheduled_time.strftime('%H:%M')}")

    def auto_export_report(self):
        """Exporta relatório automaticamente para a pasta padrão (executa em thread separada)"""
        # Verificar se já há uma exportação em andamento
        if self._export_in_progress:
            self.add_log("⏳ Exportação anterior ainda em andamento, aguardando...")
            return

        # Verificar se há pasta configurada
        export_folder = self.export_folder_input.text()
        if not export_folder or not os.path.isdir(export_folder):
            self.add_log("⚠️ Pasta de exportação não configurada. Configure em 'Configurações de Exportação'")
            self.export_timer.stop()
            self.auto_export_combo.setCurrentIndex(0)
            QMessageBox.warning(
                self,
                "Pasta Não Configurada",
                "A pasta de exportação não está configurada.\n\n"
                "Configure uma pasta válida em 'Configurações de Exportação' antes de ativar a exportação automática."
            )
            return

        # Marcar exportação como em andamento
        self._export_in_progress = True

        # Executar exportação em thread separada para não bloquear a GUI
        export_thread = threading.Thread(
            target=self._do_export_report,
            args=(export_folder,),
            daemon=True
        )
        export_thread.start()

    def _do_export_report(self, export_folder):
        """
        Realiza a exportação Excel em background (roda em thread separada).
        Agora com proteção robusta contra crashes por permissões/antivírus.
        """
        import time

        try:
            # Se o sistema está rodando, usar contador da thread; senão, carregar do banco
            if self.video_thread is not None and self.video_thread.running:
                counter = self.video_thread.counter
            else:
                # Criar um counter temporário e carregar dados do banco
                counter = VehicleCounter(database=self.database, rtsp_url=self.current_rtsp_url)

            dados = []

            for cat in ['Carros','Motos','Caminhões','Ônibus']:
                dados.append({
                    'Categoria': cat,
                    'Ida': counter.contadores[cat]['ida'],
                    'Volta': counter.contadores[cat]['volta'],
                    'Total': counter.contadores[cat]['ida'] + counter.contadores[cat]['volta']
                })

            dados.append({
                'Categoria': 'TOTAL',
                'Ida': counter.contadores['total']['ida'],
                'Volta': counter.contadores['total']['volta'],
                'Total': counter.get_total()
            })

            # Gerar nome do arquivo com timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(export_folder, f"relatorio_{timestamp}.xlsx")

            # Tentar exportar com retry (proteção contra antivírus/permissões)
            max_retries = 3
            retry_delay = 0.5

            for attempt in range(max_retries):
                try:
                    # Operação de I/O que pode demorar
                    df = pd.DataFrame(dados)

                    # PROTEÇÃO: Tentar exportar com auto-width, se falhar usar exportação simples
                    try:
                        # Exportar com openpyxl para poder ajustar larguras
                        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Relatório')

                            # Ajustar largura das colunas automaticamente
                            worksheet = writer.sheets['Relatório']
                            for column in worksheet.columns:
                                max_length = 0
                                column_letter = column[0].column_letter

                                for cell in column:
                                    try:
                                        if len(str(cell.value)) > max_length:
                                            max_length = len(str(cell.value))
                                    except:
                                        pass

                                # Adicionar margem de 2 caracteres
                                adjusted_width = min(max_length + 2, 50)
                                worksheet.column_dimensions[column_letter].width = adjusted_width

                    except Exception as width_error:
                        # Se auto-width falhar, exportar de forma simples (sem ajuste de largura)
                        print(f"[AVISO] Auto-width falhou, exportando sem formatação: {type(width_error).__name__}")

                        # Apagar arquivo parcial se existir
                        if os.path.exists(filename):
                            try:
                                os.remove(filename)
                            except:
                                pass

                        # Exportação simples sem formatação (mais robusta)
                        df.to_excel(filename, index=False, sheet_name='Relatório', engine='openpyxl')

                    # Sucesso!
                    self.export_completed.emit(f"Relatório exportado: {filename}")
                    return

                except PermissionError as perm_error:
                    if attempt < max_retries - 1:
                        print(f"[AVISO] Arquivo Excel bloqueado (tentativa {attempt+1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise Exception(
                            f"Arquivo bloqueado após {max_retries} tentativas.\n"
                            f"Feche o Excel se estiver com o arquivo aberto."
                        ) from perm_error

        except Exception as e:
            # Log detalhado para diagnóstico
            import traceback
            print(f"[ERRO] Falha na exportação Excel:")
            print(f"  Tipo: {type(e).__name__}")
            print(f"  Mensagem: {str(e)}")
            print(f"  Detalhes:\n{traceback.format_exc()}")

            # Emitir sinal de erro thread-safe (mensagem amigável)
            self.export_completed.emit(f"Erro na exportação: {type(e).__name__}")

        finally:
            # Liberar flag de exportação
            self._export_in_progress = False

    def apply_stylesheet(self):
        # Combinar estilos globais
        style = (
            Styles.MAIN_WINDOW +
            Styles.PANEL +
            Styles.BUTTON_PRIMARY +
            Styles.BUTTON_SECONDARY +
            Styles.INPUT +
            Styles.TABLE +
            Styles.SCROLLBAR +
            Styles.TAB_WIDGET +
            Styles.SLIDER +
            Styles.CHECKBOX +
            Styles.TEXT_EDIT
        )
        
        # Adicionar estilos específicos da MainWindow
        style += f"""
        #panelTitle {{ 
            color: {ThemeColors.TEXT_PRIMARY}; 
            font-size: 20px; 
            font-weight: bold; 
            padding: 10px; 
        }}
        #panelSubtitle {{ 
            color: {ThemeColors.TEXT_SECONDARY}; 
            font-size: 13px; 
            padding-bottom: 15px; 
        }}
        
        #startButton {{
            background-color: {ThemeColors.SUCCESS};
            font-size: 15px; 
            padding: 14px 20px;
        }}
        #startButton:hover {{ background-color: #059669; }}
        #startButton:pressed {{ background-color: #047857; }}
        
        #statusOnline {{ color: {ThemeColors.SUCCESS}; font-weight: bold; font-size: 14px; }}
        #statusOffline {{ color: {ThemeColors.DANGER}; font-weight: bold; font-size: 14px; }}
        
        #totalFrame {{
            background-color: {ThemeColors.BACKGROUND};
            border-radius: 8px;
            border: 1px solid {ThemeColors.SURFACE};
        }}

        #videoFrame {{
            background-color: {ThemeColors.BACKGROUND};
            border-radius: 8px;
            border: 1px solid {ThemeColors.SURFACE};
        }}

        #cardTitle {{
            color: {ThemeColors.TEXT_PRIMARY}; font-size: 11px; font-weight: 600;
            text-transform: uppercase; letter-spacing: 0.3px;
        }}
        #cardCount {{
            color: {ThemeColors.TEXT_PRIMARY}; font-size: 36px; font-weight: 900;
            padding: 4px 0 6px 0;
            line-height: 1.0;
            min-height: 45px;
        }}
        #cardDirection {{ color: {ThemeColors.TEXT_PRIMARY}; font-size: 14px; font-weight: 600; }}
        """

        # Estilos para QMessageBox (herdam do pai por serem filhos do MainWindow)
        style += f"""
        QMessageBox {{
            background-color: {ThemeColors.BACKGROUND};
            color: {ThemeColors.TEXT_PRIMARY};
        }}
        QMessageBox QLabel {{
            color: {ThemeColors.TEXT_PRIMARY};
            background: transparent;
            font-size: 13px;
        }}
        QMessageBox QPushButton {{
            background-color: {ThemeColors.PRIMARY};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 6px 18px;
            min-width: 70px;
            font-weight: bold;
        }}
        QMessageBox QPushButton:hover {{
            background-color: {ThemeColors.PRIMARY_HOVER};
        }}
        QMessageBox QPushButton:default {{
            background-color: {ThemeColors.PRIMARY};
        }}

        QMenu {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_PRIMARY};
            border: 1px solid {ThemeColors.BORDER};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 24px 6px 12px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {ThemeColors.PRIMARY};
            color: white;
        }}
        QMenu::item:disabled {{
            color: {ThemeColors.TEXT_ALT};
        }}
        QMenu::separator {{
            height: 1px;
            background: {ThemeColors.BORDER};
            margin: 4px 8px;
        }}

        QInputDialog {{
            background-color: {ThemeColors.BACKGROUND};
            color: {ThemeColors.TEXT_PRIMARY};
        }}
        QInputDialog QLabel {{
            color: {ThemeColors.TEXT_PRIMARY};
            background: transparent;
            font-size: 13px;
        }}
        QInputDialog QLineEdit {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_PRIMARY};
            border: 1px solid {ThemeColors.BORDER};
            border-radius: 5px;
            padding: 6px 10px;
            font-size: 13px;
        }}
        QInputDialog QLineEdit:focus {{
            border-color: {ThemeColors.PRIMARY};
        }}
        QInputDialog QPushButton {{
            background-color: {ThemeColors.PRIMARY};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 6px 18px;
            min-width: 70px;
            font-weight: bold;
        }}
        QInputDialog QPushButton:hover {{
            background-color: {ThemeColors.PRIMARY_HOVER};
        }}
        QInputDialog QPushButton[text="Cancel"],
        QInputDialog QPushButton[text="Cancelar"] {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_PRIMARY};
            border: 1px solid {ThemeColors.BORDER};
        }}
        QInputDialog QPushButton[text="Cancel"]:hover,
        QInputDialog QPushButton[text="Cancelar"]:hover {{
            background-color: {ThemeColors.BORDER};
        }}
        """

        self.setStyleSheet(style)

# ========================= Diálogo ROI =========================
class ROIConfigDialog(QDialog):
    """Editor interativo para linha/zonas"""
    def __init__(self, video_thread, config: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurar Linha de Contagem")
        # Dimensionar respeitando a tela disponível
        screen = QApplication.primaryScreen().availableGeometry()
        win_w = min(1100, screen.width()  - 60)
        win_h = min(720,  screen.height() - 80)
        self.resize(win_w, win_h)
        self.video_thread = video_thread
        self.config = config

        # Aplicar estilo dark mode
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {ThemeColors.TEXT_PRIMARY};
            }}
            {Styles.PANEL}
            {Styles.BUTTON_PRIMARY}
            {Styles.SLIDER}
            {Styles.INPUT}
        """)
        
        # Carregar frame inicial
        if self.video_thread.last_frame is not None:
            self.frame = cv2.cvtColor(self.video_thread.last_frame, cv2.COLOR_BGR2RGB)
        else:
            # Fallback (não deve acontecer devido à verificação anterior)
            self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
            
        self.h, self.w = self.frame.shape[:2]

        self.counting_mode = 'line'  # Sempre usar linha
        self.line_config = dict(config.get('line_config', {
            'x1_ratio': 0.1, 'x2_ratio': 0.9, 'y_ratio': 0.55, 'band_px': 2
        }))
        # Garantir que os novos campos existam no dict carregado
        if 'x_mid_ratio' not in self.line_config:
            x1r = self.line_config.get('x1_ratio', 0.1)
            x2r = self.line_config.get('x2_ratio', 0.9)
            self.line_config['x_mid_ratio'] = (x1r + x2r) / 2.0
        if 'invert_direction' not in self.line_config:
            self.line_config['invert_direction'] = False
        if 'direction_mode' not in self.line_config:
            self.line_config['direction_mode'] = 'both'
        self.active_handle = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Configure a Linha de Contagem")
        header.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY};")
        main_layout.addWidget(header)

        info = QLabel("Arraste a linha para ajustar a posição. Veículos serão contados ao cruzarem esta linha.")
        info.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; margin-bottom: 10px;")
        main_layout.addWidget(info)

        self.canvas = QLabel()
        self.canvas.setMinimumSize(600, 400)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setStyleSheet(f"background: {ThemeColors.BACKGROUND}; border: 2px solid {ThemeColors.SURFACE}; border-radius: 8px;")
        main_layout.addWidget(self.canvas, 1)

        # ---- Opções de Sentido ----
        dir_group = QGroupBox("Opções de Sentido")
        dir_layout = QVBoxLayout()
        dir_layout.setSpacing(8)

        self.chk_invert = QCheckBox("Inverter sentido (troca IDA ↔ VOLTA)")
        self.chk_invert.setChecked(bool(self.line_config.get('invert_direction', False)))
        self.chk_invert.stateChanged.connect(self._on_invert_changed)
        dir_layout.addWidget(self.chk_invert)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Contar sentidos:"))
        self.combo_direction = QComboBox()
        self.combo_direction.addItem("Ambos os sentidos", 'both')
        self.combo_direction.addItem("Somente IDA", 'ida_only')
        self.combo_direction.addItem("Somente VOLTA", 'volta_only')
        cur_mode = self.line_config.get('direction_mode', 'both')
        for _i in range(self.combo_direction.count()):
            if self.combo_direction.itemData(_i) == cur_mode:
                self.combo_direction.setCurrentIndex(_i)
                break
        self.combo_direction.currentIndexChanged.connect(self._on_direction_mode_changed)
        mode_row.addWidget(self.combo_direction)
        mode_row.addStretch()
        dir_layout.addLayout(mode_row)

        dir_group.setLayout(dir_layout)
        main_layout.addWidget(dir_group)

        # Botão Atualizar Frame
        self.btn_refresh = QPushButton("Atualizar Frame")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.update_frame_snapshot)
        self.btn_refresh.setStyleSheet(Styles.BUTTON_SECONDARY)
        main_layout.addWidget(self.btn_refresh)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self.canvas.installEventFilter(self)
        self.refresh_canvas()
        self.apply_dialog_style()

    def apply_dialog_style(self):
        # Reutilizar estilos globais
        style = (
            Styles.MAIN_WINDOW +
            Styles.INPUT +
            Styles.BUTTON_PRIMARY +
            Styles.BUTTON_SECONDARY +
            Styles.PANEL
        )
        self.setStyleSheet(style)

    def ratios_to_pixels_line(self):
        x1   = int(self.line_config['x1_ratio']  * self.w)
        x2   = int(self.line_config['x2_ratio']  * self.w)
        x_mid= int(self.line_config['x_mid_ratio'] * self.w)
        y    = int(self.line_config['y_ratio']   * self.h)
        return x1, x_mid, x2, y

    def clamp_ratios(self):
        for k in ('x1_ratio', 'x2_ratio', 'y_ratio', 'x_mid_ratio'):
            self.line_config[k] = max(0.0, min(1.0, float(self.line_config.get(k, 0.5))))

        if self.line_config['x1_ratio'] > self.line_config['x2_ratio']:
            self.line_config['x1_ratio'], self.line_config['x2_ratio'] = \
                self.line_config['x2_ratio'], self.line_config['x1_ratio']

        # Manter x_mid entre x1 e x2
        x1r = self.line_config['x1_ratio']
        x2r = self.line_config['x2_ratio']
        self.line_config['x_mid_ratio'] = max(x1r, min(x2r, self.line_config['x_mid_ratio']))

    def refresh_canvas(self):
        self.clamp_ratios()
        img = self.frame.copy()

        x1, x_mid, x2, y = self.ratios_to_pixels_line()
        band = int(self.line_config.get('band_px', 2))
        invert = bool(self.line_config.get('invert_direction', False))
        direction_mode = self.line_config.get('direction_mode', 'both')

        # Cores (RGB pois frame já foi convertido para RGB)
        ida_color   = (80, 220, 80)    # verde
        volta_color = (220, 80, 80)    # vermelho
        dim_color   = (110, 110, 110)  # cinza para lado desabilitado

        left_color  = volta_color if invert else ida_color
        right_color = ida_color   if invert else volta_color
        left_label  = "VOLTA"    if invert else "IDA"
        right_label = "IDA"      if invert else "VOLTA"

        if invert:
            show_left  = direction_mode != 'ida_only'
            show_right = direction_mode != 'volta_only'
        else:
            show_left  = direction_mode != 'volta_only'
            show_right = direction_mode != 'ida_only'

        # Área semi-transparente da banda
        overlay = img.copy()
        if show_left and x_mid > x1:
            cv2.rectangle(overlay, (x1, y - band), (x_mid, y + band), left_color, -1)
        if show_right and x2 > x_mid:
            cv2.rectangle(overlay, (x_mid, y - band), (x2, y + band), right_color, -1)
        img = cv2.addWeighted(overlay, 0.3, img, 0.7, 0)

        # Segmento esquerdo
        if show_left and x_mid > x1:
            cv2.line(img, (x1, y), (x_mid, y), left_color, 4)
            cv2.rectangle(img, (x1, y - band), (x_mid, y + band), left_color, 2)
        elif x_mid > x1:
            cv2.line(img, (x1, y), (x_mid, y), dim_color, 2)

        # Segmento direito
        if show_right and x2 > x_mid:
            cv2.line(img, (x_mid, y), (x2, y), right_color, 4)
            cv2.rectangle(img, (x_mid, y - band), (x2, y + band), right_color, 2)
        elif x2 > x_mid:
            cv2.line(img, (x_mid, y), (x2, y), dim_color, 2)

        # Labels de sentido acima de cada metade
        font = cv2.FONT_HERSHEY_SIMPLEX
        if show_left and x_mid > x1:
            lx = (x1 + x_mid) // 2
            cv2.putText(img, left_label, (lx - 28, y - 18), font, 0.75, left_color, 2)
        if show_right and x2 > x_mid:
            rx = (x_mid + x2) // 2
            cv2.putText(img, right_label, (rx - 34, y - 18), font, 0.75, right_color, 2)

        # Handle L (esquerda)
        cv2.circle(img, (x1, y), 12, (255, 80, 80), -1)
        cv2.circle(img, (x1, y), 14, (255, 255, 255), 2)
        cv2.putText(img, "L", (x1 - 8, y + 5), font, 0.5, (255, 255, 255), 2)

        # Handle R (direita)
        cv2.circle(img, (x2, y), 12, (255, 80, 80), -1)
        cv2.circle(img, (x2, y), 14, (255, 255, 255), 2)
        cv2.putText(img, "R", (x2 - 8, y + 5), font, 0.5, (255, 255, 255), 2)

        # Handle M (meio — divide IDA/VOLTA, arraste horizontal)
        cv2.circle(img, (x_mid, y), 12, (255, 180, 0), -1)   # laranja
        cv2.circle(img, (x_mid, y), 14, (255, 255, 255), 2)
        cv2.putText(img, "M", (x_mid - 8, y + 5), font, 0.5, (0, 0, 0), 2)


        # Ensure contiguous array and correct bytes per line
        if not img.flags['C_CONTIGUOUS']:
            img = np.ascontiguousarray(img)
            
        height, width, channel = img.shape
        bytes_per_line = 3 * width
        
        # Keep reference to data to prevent garbage collection
        self._qimage_data = img
        
        qimg = QImage(img.data, width, height, bytes_per_line, QImage.Format_RGB888)
        pix = QPixmap.fromImage(qimg).scaled(
            self.canvas.width() - 10,
            self.canvas.height() - 10,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.canvas.setPixmap(pix)

    def on_y_slider(self, val):
        self.line_config['y_ratio'] = val / 100.0
        self.y_label.setText(f"{val}%")
        self.refresh_canvas()

    def on_band_slider(self, val):
        self.line_config['band_px'] = int(val)
        self.band_label.setText(f"{val}px")
        self.refresh_canvas()

    def eventFilter(self, obj, event):
        if obj is self.canvas and self.canvas.pixmap() is not None:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._handle_mouse(event, press=True)
                return True
            elif event.type() == QEvent.MouseMove and (event.buttons() & Qt.LeftButton):
                self._handle_mouse(event, press=False)
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self.active_handle = None
                return True
        return super().eventFilter(obj, event)

    def _label_to_img_coords(self, pos):
        lbl_w, lbl_h = self.canvas.width(), self.canvas.height()
        pix = self.canvas.pixmap()
        px_w, px_h = pix.width(), pix.height()
        off_x = (lbl_w - px_w) // 2
        off_y = (lbl_h - px_h) // 2
        mx = pos.x() - off_x
        my = pos.y() - off_y
        
        if 0 <= mx < px_w and 0 <= my < px_h:
            ix = int(mx * self.w / px_w)
            iy = int(my * self.h / px_h)
            return ix, iy
        return None, None

    def _handle_mouse(self, event, press):
        ix, iy = self._label_to_img_coords(event.pos())
        if ix is None:
            return

        x1, x_mid, x2, y = self.ratios_to_pixels_line()

        def near(a, b, thr=15):
            return abs(a - b) <= thr

        if press:
            if near(ix, x1) and near(iy, y):
                self.active_handle = 'x1'
            elif near(ix, x2) and near(iy, y):
                self.active_handle = 'x2'
            elif near(ix, x_mid) and near(iy, y):
                self.active_handle = 'mid'
            elif (x1 <= ix <= x2) and near(iy, y, thr=18):
                # Clique no corpo da linha move a altura
                self.active_handle = 'y'
            else:
                self.active_handle = None

        if self.active_handle == 'x1':
            self.line_config['x1_ratio'] = ix / self.w
        elif self.active_handle == 'x2':
            self.line_config['x2_ratio'] = ix / self.w
        elif self.active_handle == 'mid':
            raw = ix / self.w
            x1r = self.line_config['x1_ratio']
            x2r = self.line_config['x2_ratio']
            self.line_config['x_mid_ratio'] = max(x1r, min(x2r, raw))
        elif self.active_handle == 'y':
            self.line_config['y_ratio'] = iy / self.h

        self.refresh_canvas()

    def _on_invert_changed(self, state):
        self.line_config['invert_direction'] = bool(state)
        self.refresh_canvas()

    def _on_direction_mode_changed(self, _idx):
        self.line_config['direction_mode'] = self.combo_direction.currentData()
        self.refresh_canvas()

    def update_frame_snapshot(self):
        """Atualiza o frame de fundo com a imagem mais recente da câmera"""
        try:
            if self.video_thread and self.video_thread.last_frame is not None:
                # Validate frame before processing
                frame = self.video_thread.last_frame
                if frame is None or frame.size == 0:
                    raise ValueError("Frame inválido ou vazio")

                self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.h, self.w = self.frame.shape[:2]
                self.refresh_canvas()
                
                # Feedback visual rápido
                self.canvas.setStyleSheet("border: 2px solid #10B981; border-radius: 8px;")
                QTimer.singleShot(500, lambda: self.canvas.setStyleSheet("background: #0a1628; border: 2px solid #1e3a5f; border-radius: 8px;"))
                
                # Log success (optional)
                # print("Frame updated successfully")
            else:
                QMessageBox.warning(self, "Aviso", "Não foi possível obter um novo frame.\nVerifique se o vídeo está rodando.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao atualizar frame: {str(e)}")
            # print(f"Error updating frame: {e}")


# ========================= Diálogo de Ajuda =========================
class HelpDialog(QDialog):
    """Diálogo com explicações sobre as funções do sistema"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajuda - Sistema Monitoramento")
        self.resize(700, 600)
        self.setup_ui()
        self.apply_style()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Título
        title = QLabel("Guia de Funções do Sistema")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #0d9488; padding-bottom: 10px;")
        layout.addWidget(title)

        # Área de scroll para o conteúdo
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_widget.setStyleSheet(f"background-color: {ThemeColors.BACKGROUND};")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)

        # Seções de ajuda
        help_sections = [
            {
                "title": "URL RTSP",
                "content": """A URL RTSP (Real-Time Streaming Protocol) é o endereço da sua câmera IP que transmite vídeo em tempo real.

<b>Formato da URL:</b>
<code>rtsp://usuario:senha@ip:porta/caminho</code>

<b>Exemplo prático:</b>
<code>rtsp://admin:1234@192.168.1.100:554/stream</code>

<b>Componentes:</b>
• <b>usuario</b>: Nome de usuário da câmera
• <b>senha</b>: Senha de acesso
• <b>ip</b>: Endereço IP da câmera na rede
• <b>porta</b>: Geralmente 554 (padrão RTSP)
• <b>caminho</b>: Varia por fabricante (/stream, /live, /cam, etc.)

<b>Dica:</b> Consulte o manual da sua câmera para obter a URL RTSP correta."""
            },
            {
                "title": "Modelos de Detecção",
                "content": """O sistema oferece 3 modelos YOLOv11 com diferentes níveis de precisão e velocidade:

<b>yolo11n (Nano) - Recomendado para CPUs</b>
• Mais rápido e leve
• Menor uso de memória
• Ótimo para computadores modestos
• Precisão: Boa

<b>yolo11s (Small) - Balanceado</b>
• Equilíbrio entre velocidade e precisão
• Uso moderado de recursos
• Recomendado para a maioria dos casos
• Precisão: Muito Boa

<b>yolo11m (Medium) - Máxima Precisão</b>
• Melhor precisão de detecção
• Requer mais processamento
• Ideal para GPUs ou CPUs potentes
• Precisão: Excelente

<b>Como escolher:</b>
Se o vídeo estiver lento, use um modelo mais leve (nano). Se tiver GPU ou CPU potente, use o medium para melhor precisão."""
            },
            {
                "title": "Confiança Mínima",
                "content": """A confiança mínima define o quão "certeiro" o sistema precisa estar para considerar uma detecção válida.

<b>Como funciona:</b>
O detector dá uma "nota" de 0% a 100% para cada objeto detectado. A confiança mínima filtra detecções com nota baixa.

<b>Valores recomendados:</b>
• <b>30-40%</b>: Detecta mais veículos, mas pode ter falsos positivos
• <b>50%</b>: Equilíbrio ideal (padrão recomendado)
• <b>60-70%</b>: Mais rigoroso, apenas detecções muito confiáveis

<b>Exemplos práticos:</b>
• Câmera com boa iluminação: 50-60%
• Câmera com pouca luz/chuva: 35-45%
• Câmera muito nítida: 60-70%

<b>Dica:</b> Comece com 50% e ajuste conforme necessário. Se o sistema não detectar alguns veículos, diminua o valor. Se detectar objetos que não são veículos, aumente o valor."""
            },
            {
                "title": "Corte ROI (Região de Interesse)",
                "content": """O Corte ROI permite focar a detecção em uma área específica do vídeo, ignorando regiões irrelevantes.

<b>O que é ROI?</b>
ROI (Region of Interest) é a área do vídeo que você deseja analisar. Você pode cortar as bordas para:
• Melhorar a performance (menos área para processar)
• Ignorar regiões irrelevantes (céu, prédios, pedestres)
• Focar apenas na pista/via

<b>Como configurar:</b>
1. Marque a opção "Habilitar Corte ROI"
2. Ajuste os sliders para cada borda:
   • <b>Topo</b>: Remove parte superior (ex: céu)
   • <b>Baixo</b>: Remove parte inferior
   • <b>Esquerda</b>: Remove lado esquerdo
   • <b>Direita</b>: Remove lado direito

<b>Exemplo prático:</b>
Se o céu ocupa 30% do topo do vídeo, ajuste "Topo" para 30%. O sistema ignorará essa área e focará na pista.

<b>Benefícios:</b>
• Reduz processamento em até 50%
• Melhora velocidade (FPS)
• Evita detecções falsas em áreas irrelevantes"""
            }
        ]

        for section in help_sections:
            # Container para cada seção
            section_frame = QFrame()
            section_frame.setObjectName("helpSection")
            section_layout = QVBoxLayout(section_frame)
            section_layout.setSpacing(8)
            section_layout.setContentsMargins(15, 15, 15, 15)

            # Título da seção
            section_title = QLabel(section["title"])
            section_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0d9488;")
            section_layout.addWidget(section_title)

            # Conteúdo da seção
            section_content = QLabel(section["content"])
            section_content.setWordWrap(True)
            section_content.setTextFormat(Qt.RichText)
            section_content.setStyleSheet(f"font-size: 13px; line-height: 1.5; color: {ThemeColors.TEXT_ALT};")
            section_layout.addWidget(section_content)

            content_layout.addWidget(section_frame)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)

        # Botão Fechar
        btn_close = QPushButton("Fechar")
        btn_close.setMinimumHeight(40)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def apply_style(self):
        style = (
            Styles.MAIN_WINDOW +
            Styles.SCROLLBAR +
            Styles.BUTTON_PRIMARY
        )
        style += f"""
            QDialog {{
                background-color: {ThemeColors.BACKGROUND};
            }}
            QScrollArea {{
                background-color: {ThemeColors.BACKGROUND};
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {ThemeColors.BACKGROUND};
            }}
            QFrame#helpSection {{
                background-color: {ThemeColors.SURFACE};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 8px;
            }}
            QFrame#helpSection QLabel {{
                background-color: transparent;
            }}
        """
        self.setStyleSheet(style)
