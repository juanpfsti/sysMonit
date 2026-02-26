#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aba de Dashboard Analítico - Gráficos e estatísticas
"""

import logging
import traceback
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QGridLayout, QFrame, QPushButton, QScrollArea, QSizePolicy, QComboBox, QToolTip
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QCursor
from .styles import Styles, ThemeColors

# Tentar importar matplotlib (opcional)
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print(" Matplotlib não instalado. Dashboard usará visualização simplificada.")
    print("   Instale com: pip install matplotlib")


class InteractiveCanvas(FigureCanvasQTAgg):
    """Canvas matplotlib com suporte a tooltips via eventos Qt"""

    def __init__(self, figure):
        super().__init__(figure)
        self.setMouseTracking(True)
        self.tooltip_callback = None

    def set_tooltip_callback(self, callback):
        """Define função callback para gerar tooltip baseado em coordenadas"""
        self.tooltip_callback = callback

    def mouseMoveEvent(self, event):
        """Captura movimento do mouse e mostra tooltip Qt nativo"""
        super().mouseMoveEvent(event)

        if self.tooltip_callback:
            # Converter coordenadas Qt para coordenadas matplotlib
            x, y = event.x(), self.height() - event.y()
            tooltip_text = self.tooltip_callback(event.x(), event.y())

            if tooltip_text:
                QToolTip.showText(QCursor.pos(), tooltip_text, self)
            else:
                QToolTip.hideText()


class DashboardWorker(QThread):
    """Worker thread para carregar dados do dashboard em segundo plano"""
    data_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, database, rtsp_url, start_date, end_date, period_index):
        super().__init__()
        self.database = database
        self.rtsp_url = rtsp_url
        self.start_date = start_date
        self.end_date = end_date
        self.period_index = period_index

    def run(self):
        try:
            # Coletar dados (operações pesadas de banco)
            
            # 1. Distribuição (Cards e Gráfico Pizza)
            distribution_period = self.database.get_vehicle_distribution(
                rtsp_url=self.rtsp_url,
                start_date=self.start_date,
                end_date=self.end_date
            ) or []
            
            # 2. Tráfego Horário
            hourly_data = []
            if self.period_index == 0:  # Filtro "Hoje"
                today_date = datetime.now().strftime('%Y-%m-%d')
                hourly_data = self.database.get_hourly_traffic(
                    rtsp_url=self.rtsp_url,
                    date=today_date
                ) or []
                
                if not hourly_data:
                    yesterday_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                    hourly_data = self.database.get_hourly_traffic(
                        rtsp_url=self.rtsp_url,
                        date=yesterday_date
                    ) or []
            else:
                # Para outros filtros, buscar do primeiro dia do período
                first_day = self.start_date.split(' ')[0] if ' ' in self.start_date else self.start_date
                hourly_data = self.database.get_hourly_traffic(
                    rtsp_url=self.rtsp_url,
                    date=first_day
                ) or []
                
                # Se o primeiro dia não tiver dados, tentar próximos dias
                if not hourly_data:
                    for days_offset in range(1, 30):  # Tentar até 30 dias
                        try_date = (datetime.strptime(first_day, '%Y-%m-%d') + timedelta(days=days_offset)).strftime('%Y-%m-%d')
                        hourly_data = self.database.get_hourly_traffic(
                            rtsp_url=self.rtsp_url,
                            date=try_date
                        ) or []
                        if hourly_data:
                            break

            # 3. Comparativo Semanal
            daily_data = self.database.get_daily_comparison(
                rtsp_url=self.rtsp_url,
                days=7
            ) or []

            # 4. Horário de Pico (NOVO)
            # Analisar últimos 7 ou 30 dias para pegar média consistente
            peak_data = self.database.get_peak_hours(
                rtsp_url=self.rtsp_url,
                days=30 if self.period_index == 2 else 7
            ) or []

            # Empacotar resultados
            results = {
                'distribution': distribution_period,
                'hourly': hourly_data,
                'daily': daily_data,
                'peak': peak_data
            }
            
            self.data_ready.emit(results)

        except Exception as e:
            error_msg = f"Erro no worker: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            self.error_occurred.emit(str(e))


class DashboardTab(QWidget):
    """Aba de dashboard com gráficos e análises estatísticas"""

    # Paleta de cores como constante de classe
    COLOR_PALETTE = {
        'Carros': ThemeColors.SUCCESS,
        'Motos': ThemeColors.SECONDARY,
        'Caminhões': ThemeColors.DANGER,
        'Ônibus': ThemeColors.WARNING
    }

    def __init__(self, database, config, parent=None):
        super().__init__(parent)
        self.database = database
        self.config = config
        self.current_rtsp_url = ''

        # Período personalizado
        self.custom_start_date = None
        self.custom_end_date = None

        # Usar paleta de cores da classe
        self.color_palette = self.COLOR_PALETTE

        #  PROTEÇÃO CONTRA RACE CONDITIONS
        self._refresh_in_progress = False
        self._worker = None  # Referência para o worker thread
        self._last_refresh_time = 0
        self._min_refresh_interval = 2.0  # Aumentado para 2s para evitar spam
        self._is_closing = False  # Flag para evitar operações durante shutdown

        self.init_ui()

        # Timer para atualização automática
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._on_auto_refresh)
        # Não inicia automaticamente - usuário escolhe no dropdown

    def init_ui(self):
        """Inicializa interface do dashboard"""
        # Aplicar estilo dark mode ao widget principal
        style = f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
            }}
        """ + (
            Styles.PANEL +
            Styles.INPUT +
            Styles.BUTTON_PRIMARY +
            Styles.SCROLLBAR
        )
        self.setStyleSheet(style)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(25)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel(" Dashboard Analítico")
        header.setStyleSheet(Styles.HEADER_TITLE)
        header_layout.addWidget(header)

        header_layout.addStretch()

        # Filtro de período global
        period_label = QLabel("Período:")
        period_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {ThemeColors.TEXT_SECONDARY}; margin-right: 8px;")
        header_layout.addWidget(period_label)

        self.period_filter = QComboBox()
        self.period_filter.addItems([
            "Hoje",
            "Últimos 7 dias",
            "Últimos 30 dias",
            "Período personalizado"
        ])
        self.period_filter.setMinimumHeight(40)
        self.period_filter.setMinimumWidth(200)
        self.period_filter.currentIndexChanged.connect(self.on_period_changed)
        self.period_filter.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        header_layout.addWidget(self.period_filter)

        header_layout.addSpacing(15)

        # Dropdown de atualização automática
        self.auto_refresh_combo = QComboBox()
        self.auto_refresh_combo.addItems([
            "Auto: Desativado",
            "Auto: 5 min",
            "Auto: 10 min",
            "Auto: 30 min",
            "Auto: 45 min"
        ])
        self.auto_refresh_combo.setMinimumHeight(40)
        self.auto_refresh_combo.currentIndexChanged.connect(self.update_auto_refresh)
        self.auto_refresh_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        header_layout.addWidget(self.auto_refresh_combo)

        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setMinimumHeight(40)
        self.btn_refresh.setMinimumWidth(130)
        self.btn_refresh.setStyleSheet(Styles.BUTTON_PRIMARY)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)  # Usar método com debounce
        header_layout.addWidget(self.btn_refresh)

        main_layout.addLayout(header_layout)

        # Scroll area para o conteúdo
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(25)

        if MATPLOTLIB_AVAILABLE:
            # Layout com gráficos usando matplotlib
            self.create_charts_layout(content_layout)
        else:
            # Layout simplificado sem matplotlib
            self.create_simple_layout(content_layout)

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def create_simple_layout(self, layout):
        """Cria layout simplificado sem matplotlib"""

        # Cards de resumo
        summary_group = QGroupBox("Resumo do Período Selecionado")
        summary_layout = QGridLayout()
        summary_layout.setSpacing(15)

        self.card_total = self.create_stat_card("Total de Veículos", "0", "#3B82F6")
        self.card_carros = self.create_stat_card("Carros", "0", self.color_palette['Carros'])
        self.card_motos = self.create_stat_card("Motos", "0", self.color_palette['Motos'])
        self.card_caminhoes = self.create_stat_card("Caminhões", "0", self.color_palette['Caminhões'])

        summary_layout.addWidget(self.card_total, 0, 0)
        summary_layout.addWidget(self.card_carros, 0, 1)
        summary_layout.addWidget(self.card_motos, 0, 2)
        summary_layout.addWidget(self.card_caminhoes, 0, 3)

        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        # Tráfego por hora (tabela simples)
        hourly_group = QGroupBox(" Tráfego Horário (Hoje)")
        hourly_layout = QVBoxLayout()
        self.hourly_text = QLabel("Carregando...")
        self.hourly_text.setWordWrap(True)
        self.hourly_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        hourly_layout.addWidget(self.hourly_text)
        hourly_group.setLayout(hourly_layout)
        layout.addWidget(hourly_group)

        # Distribuição por tipo
        dist_group = QGroupBox("Distribuição por Tipo de Veículo (Últimos 7 Dias)")
        dist_layout = QVBoxLayout()
        self.dist_text = QLabel("Carregando...")
        self.dist_text.setWordWrap(True)
        self.dist_text.setStyleSheet("font-family: monospace; font-size: 12px;")
        dist_layout.addWidget(self.dist_text)
        dist_group.setLayout(dist_layout)
        layout.addWidget(dist_group)

        layout.addStretch()

    def create_charts_layout(self, layout):
        """Cria layout com gráficos matplotlib"""

        # Cards de resumo (usando cores consistentes)
        summary_group = QGroupBox("Resumo do Período Selecionado")
        summary_layout = QGridLayout()
        summary_layout.setSpacing(15)

        self.card_total = self.create_stat_card("Total de Veículos", "0", "#3B82F6")
        self.card_carros = self.create_stat_card("Carros", "0", self.color_palette['Carros'])
        self.card_motos = self.create_stat_card("Motos", "0", self.color_palette['Motos'])
        self.card_caminhoes = self.create_stat_card("Caminhões", "0", self.color_palette['Caminhões'])

        summary_layout.addWidget(self.card_total, 0, 0)
        summary_layout.addWidget(self.card_carros, 0, 1)
        summary_layout.addWidget(self.card_motos, 0, 2)
        summary_layout.addWidget(self.card_caminhoes, 0, 3)

        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)

        # Grid de gráficos
        charts_layout = QGridLayout()
        charts_layout.setSpacing(20)

        # Gráfico 1: Distribuição por tipo (canto superior esquerdo)
        self.distribution_chart = self.create_chart("Distribuição por Tipo")
        charts_layout.addWidget(self.distribution_chart, 0, 0)

        # Gráfico 2: Comparativo semanal (canto superior direito)
        self.weekly_chart = self.create_chart("Comparativo Semanal")
        charts_layout.addWidget(self.weekly_chart, 0, 1)

        # Gráfico 3: Horário de Pico (linha inteira embaixo)
        self.peak_chart = self.create_chart("Horários de Pico (Média Histórica)")
        charts_layout.addWidget(self.peak_chart, 1, 0, 1, 2)  # Spanar 2 colunas

        layout.addLayout(charts_layout)

    def create_stat_card(self, title, value, color):
        """Cria um card de estatística"""
        card = QFrame()
        card.setStyleSheet(Styles.get_card_style(color))
        card.setMinimumHeight(110)
        card.setMaximumHeight(110)
        # Adicionar sombra usando efeito gráfico
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        from PyQt5.QtGui import QColor
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)
        card_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            color: rgba(255, 255, 255, 1.0);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            padding: 0;
            margin: 0;
            background-color: transparent;
            border: none;
        """)
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet("""
            color: white;
            font-size: 40px;
            font-weight: 800;
            letter-spacing: -1px;
            line-height: 1.0;
            padding: 4px 0 0 0;
            margin: 0;
            background-color: transparent;
            border: none;
        """)
        value_label.setObjectName("stat_value")
        value_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        card_layout.addWidget(value_label)

        card_layout.addStretch()

        return card

    def _adjust_color_brightness(self, hex_color, factor):
        """Ajusta o brilho de uma cor hexadecimal"""
        # Remove # se presente
        hex_color = hex_color.lstrip('#')
        # Converte para RGB
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        # Ajusta o brilho
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        # Garante que os valores estejam no intervalo válido
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        return f'#{r:02x}{g:02x}{b:02x}'

    def create_chart(self, title):
        """Cria um widget de gráfico matplotlib"""
        container = QGroupBox(title)
        layout = QVBoxLayout()

        # Criar figura matplotlib com fundo escuro
        fig = Figure(figsize=(6, 4), dpi=100, facecolor=ThemeColors.BACKGROUND)
        # Usar canvas interativo customizado
        canvas = InteractiveCanvas(fig)
        canvas.setMinimumHeight(300)
        canvas.setStyleSheet(f"background-color: {ThemeColors.BACKGROUND}; border-radius: 8px;")

        layout.addWidget(canvas)
        container.setLayout(layout)
        container.chart_canvas = canvas
        container.chart_figure = fig

        return container

    def _apply_chart_style(self, ax, fig):
        """Aplica estilo dark mode aos gráficos"""
        # Fundo do gráfico (tudo na mesma cor escura)
        ax.set_facecolor(ThemeColors.BACKGROUND)
        fig.patch.set_facecolor(ThemeColors.BACKGROUND)

        # Cor do texto
        ax.tick_params(colors=ThemeColors.TEXT_SECONDARY, which='both')
        ax.xaxis.label.set_color(ThemeColors.TEXT_SECONDARY)
        ax.yaxis.label.set_color(ThemeColors.TEXT_SECONDARY)
        ax.title.set_color(ThemeColors.TEXT_PRIMARY)

        # Grid suave
        ax.grid(True, alpha=0.15, color=ThemeColors.BORDER, linestyle='-', linewidth=0.8)

        # Borda do gráfico
        for spine in ax.spines.values():
            spine.set_edgecolor(ThemeColors.BORDER)
            spine.set_linewidth(1)

    def set_rtsp_url(self, rtsp_url):
        """Define o link RTSP atual e atualiza o dashboard"""
        self.current_rtsp_url = rtsp_url
        self.refresh_dashboard()

    def on_period_changed(self, index):
        """Chamado quando o filtro de período é alterado"""
        if index == 3:  # Período personalizado
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDateTimeEdit, QDialogButtonBox
            from PyQt5.QtCore import QDateTime

            # Criar diálogo para seleção de período
            dialog = QDialog(self)
            dialog.setWindowTitle("Selecionar Período Personalizado")
            dialog.setMinimumWidth(400)
            dialog.setStyleSheet(f"""
                QDialog {{ background-color: {ThemeColors.BACKGROUND}; }}
                QLabel {{ color: {ThemeColors.TEXT_PRIMARY}; font-size: 13px; }}
                QDateTimeEdit {{
                    background-color: {ThemeColors.SURFACE};
                    color: {ThemeColors.TEXT_PRIMARY};
                    border: 1px solid {ThemeColors.BORDER};
                    border-radius: 4px;
                    padding: 5px 8px;
                }}
                QPushButton {{
                    background-color: {ThemeColors.PRIMARY};
                    color: white; border: none;
                    border-radius: 5px; padding: 6px 16px; font-weight: bold;
                }}
                QPushButton:hover {{ background-color: {ThemeColors.PRIMARY_HOVER}; }}
            """)

            layout = QVBoxLayout(dialog)
            layout.setContentsMargins(20, 18, 20, 16)
            layout.setSpacing(12)

            # Data inicial
            start_layout = QHBoxLayout()
            lbl_start = QLabel("Data Inicial:")
            lbl_start.setFixedWidth(90)
            start_layout.addWidget(lbl_start)
            start_date_edit = QDateTimeEdit()
            start_date_edit.setDateTime(QDateTime.currentDateTime().addDays(-7))
            start_date_edit.setDisplayFormat("dd/MM/yyyy")
            start_date_edit.setCalendarPopup(True)
            start_layout.addWidget(start_date_edit)
            layout.addLayout(start_layout)

            # Data final
            end_layout = QHBoxLayout()
            lbl_end = QLabel("Data Final:")
            lbl_end.setFixedWidth(90)
            end_layout.addWidget(lbl_end)
            end_date_edit = QDateTimeEdit()
            end_date_edit.setDateTime(QDateTime.currentDateTime())
            end_date_edit.setDisplayFormat("dd/MM/yyyy")
            end_date_edit.setCalendarPopup(True)
            end_layout.addWidget(end_date_edit)
            layout.addLayout(end_layout)

            # Botões
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.button(QDialogButtonBox.Ok).setText("Confirmar")
            buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
            buttons.button(QDialogButtonBox.Cancel).setStyleSheet(
                f"background-color: {ThemeColors.SURFACE_LIGHT}; color: {ThemeColors.TEXT_PRIMARY};"
                f"border: 1px solid {ThemeColors.BORDER}; border-radius: 5px; padding: 6px 16px;"
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)

            if dialog.exec_() == QDialog.Accepted:
                # Usar dia inteiro (00:00:00 até 23:59:59)
                self.custom_start_date = start_date_edit.dateTime().toString("yyyy-MM-dd") + " 00:00:00"
                self.custom_end_date = end_date_edit.dateTime().toString("yyyy-MM-dd") + " 23:59:59"
                self.refresh_dashboard()
            else:
                # Se cancelou, voltar para "Últimos 7 dias"
                self.period_filter.blockSignals(True)
                self.period_filter.setCurrentIndex(1)
                self.period_filter.blockSignals(False)
        else:
            # Para outros períodos, atualizar dashboard imediatamente
            self.refresh_dashboard()

    def get_period_dates(self):
        """Retorna as datas de início e fim baseado no filtro selecionado"""
        period_index = self.period_filter.currentIndex()

        if period_index == 0:  # Hoje
            today = datetime.now().strftime('%Y-%m-%d')
            return today, datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif period_index == 1:  # Últimos 7 dias
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            return week_ago, datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif period_index == 2:  # Últimos 30 dias
            month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            return month_ago, datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif period_index == 3:  # Personalizado
            return self.custom_start_date, self.custom_end_date

    def update_auto_refresh(self, index):
        """Atualiza intervalo de atualização automática"""
        # Parar timer atual
        self.refresh_timer.stop()

        # Configurar novo intervalo baseado na seleção
        intervals = {
            0: 0,           # Desativado
            1: 5 * 60000,   # 5 minutos
            2: 10 * 60000,  # 10 minutos
            3: 30 * 60000,  # 30 minutos
            4: 45 * 60000   # 45 minutos
        }

        interval = intervals.get(index, 0)

        if interval > 0:
            self.refresh_timer.start(interval)
            print(f"[Dashboard] Atualização automática ativada: {interval // 60000} minutos")
        else:
            print("[Dashboard] Atualização automática desativada")

    def _on_auto_refresh(self):
        """Callback do timer de auto-refresh"""
        if self._refresh_in_progress:
            logging.debug("Auto-refresh ignorado (já em progresso)")
            return
        
        logging.debug("Iniciando Auto-Refresh do Dashboard...")
        self.refresh_dashboard()

    def _on_refresh_clicked(self):
        """Método com debounce para o botão de atualização"""
        import time
        
        # Verificar se já está atualizando
        if self._refresh_in_progress:
            logging.debug("Refresh já em progresso, ignorando clique")
            return
        
        # Verificar intervalo mínimo entre atualizações
        elapsed = time.time() - self._last_refresh_time
        if elapsed < self._min_refresh_interval:
            logging.debug(f"Atualização muito rápida ({elapsed:.2f}s), aguardando {self._min_refresh_interval}s")
            return
        
        self.refresh_dashboard()
        self._last_refresh_time = time.time()

    def closeEvent(self):
        """ Limpeza antes de fechar dashboard"""
        self._is_closing = True
        try:
            # Parar worker
            if self._worker and self._worker.isRunning():
                self._worker.quit()
                self._worker.wait(1000)

            # Parar timers
            if hasattr(self, 'period_filter'):
                self.period_filter.blockSignals(True)
            if hasattr(self, 'auto_refresh_combo'):
                self.auto_refresh_combo.blockSignals(True)
            if hasattr(self, 'btn_refresh'):
                self.btn_refresh.blockSignals(True)
        except:
            pass

    def refresh_dashboard(self):
        """Inicia atualização do dashboard em BACKGROUND"""
        # Verificar shutdown
        if self._is_closing:
            return
        try:
            if hasattr(self.parent(), 'is_shutting_down') and self.parent().is_shutting_down():
                return
        except:
            pass
        
        if self._refresh_in_progress:
            return

        self._refresh_in_progress = True
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Carregando...")

        # Obter datas antes de iniciar thread
        start_date, end_date = self.get_period_dates()
        period_idx = self.period_filter.currentIndex()

        # Iniciar Worker
        self._worker = DashboardWorker(self.database, self.current_rtsp_url, start_date, end_date, period_idx)
        self._worker.data_ready.connect(self._on_worker_finished)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _on_worker_finished(self, data):
        """Recebe dados processados do worker e atualiza UI"""
        if self._is_closing: return

        try:
            if MATPLOTLIB_AVAILABLE:
                self._update_ui_charts(data)
            else:
                self._update_ui_simple(data)
                
        except Exception as e:
            logging.error(f"Erro ao atualizar UI: {e}")
            self.card_total.findChild(QLabel, "stat_value").setText("Erro")

    def _on_worker_error(self, error_msg):
        logging.error(f"Erro no Worker Dashboard: {error_msg}")
        self.btn_refresh.setText("Erro!")
        QTimer.singleShot(2000, lambda: self.btn_refresh.setText("Atualizar"))

    def _cleanup_worker(self):
        """Limpeza após término do worker"""
        self._refresh_in_progress = False
        if not self._is_closing:
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("Atualizar")
        self._worker.deleteLater()
        self._worker = None

    def _update_ui_simple(self, data):
        """Atualiza UI simplificada (sem gráficos)"""
        dist_data = data.get('distribution', [])
        
        # Cards
        total_period = sum(item['total'] for item in dist_data)
        carros = sum(item['total'] for item in dist_data if item.get('categoria') == 'Carros')
        motos = sum(item['total'] for item in dist_data if item.get('categoria') == 'Motos')
        caminhoes = sum(item['total'] for item in dist_data if item.get('categoria') == 'Caminhões')

        self.card_total.findChild(QLabel, "stat_value").setText(str(total_period))
        self.card_carros.findChild(QLabel, "stat_value").setText(str(carros))
        self.card_motos.findChild(QLabel, "stat_value").setText(str(motos))
        self.card_caminhoes.findChild(QLabel, "stat_value").setText(str(caminhoes))

        # Texto Hora
        hourly_data = data.get('hourly', [])
        hourly_text = "Hora | Veículos\n" + "-" * 20 + "\n"
        for item in hourly_data:
            hourly_text += f"{item['hora']:02d}:00 | {item['total']:4d} {'█' * min(item['total'] // 10, 20)}\n"
        if not hourly_data:
            hourly_text = "Sem dados"
        self.hourly_text.setText(hourly_text)

        # Texto Distribuição
        dist_text = "Tipo      | Total | %\n" + "-" * 30 + "\n"
        for item in dist_data:
            pct = (item['total'] / total_period * 100) if total_period > 0 else 0
            dist_text += f"{item['categoria']:10} | {item['total']:5d} | {pct:5.1f}%\n"
        if not dist_data:
            dist_text = "Sem dados"
        self.dist_text.setText(dist_text)

    def _update_ui_charts(self, data):
        """Atualiza gráficos com dados do worker"""
        
        # --- Cards ---
        dist_data = data.get('distribution', [])
        total_period = sum(item['total'] for item in dist_data)
        carros = sum(item['total'] for item in dist_data if item.get('categoria') == 'Carros')
        motos = sum(item['total'] for item in dist_data if item.get('categoria') == 'Motos')
        caminhoes = sum(item['total'] for item in dist_data if item.get('categoria') == 'Caminhões')

        self.card_total.findChild(QLabel, "stat_value").setText(str(total_period))
        self.card_carros.findChild(QLabel, "stat_value").setText(str(carros))
        self.card_motos.findChild(QLabel, "stat_value").setText(str(motos))
        self.card_caminhoes.findChild(QLabel, "stat_value").setText(str(caminhoes))

        # --- Gráfico 1: Distribuição ---
        try:
            fig = self.distribution_chart.chart_figure
            fig.clear()
            ax = fig.add_subplot(111)
            self._apply_chart_style(ax, fig)

            if dist_data:
                categories = [item['categoria'] for item in dist_data]
                values = [item['total'] for item in dist_data]
                colors = [self.color_palette.get(cat, '#9ca3af') for cat in categories]
                
                bars = ax.bar(categories, values, color=colors, edgecolor='white', linewidth=1.5)
                ax.set_ylabel('Total', fontsize=10)
                
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax.text(bar.get_x() + bar.get_width()/2., height,
                               f'{int(height)}',
                               ha='center', va='bottom', fontsize=9, color='#e2e8f0')
            else:
                ax.text(0.5, 0.5, 'Sem dados', ha='center', va='center', fontsize=12, transform=ax.transAxes, color='#888')

            fig.subplots_adjust(bottom=0.15, left=0.12, right=0.95, top=0.95)
            self.distribution_chart.chart_canvas.draw_idle()
        except Exception as e:
            logging.error(f"Erro chart 2: {e}")

        # --- Gráfico 3: Comparativo Semanal ---
        daily_data = data.get('daily', [])
        try:
            fig = self.weekly_chart.chart_figure
            fig.clear()
            ax = fig.add_subplot(111)
            self._apply_chart_style(ax, fig)
            
            # (Simplificando lógica para não ficar muito longo - plotando total por dia)
            if daily_data:
                # Agrupar por dia
                days = sorted(list(set(d['dia_semana'] for d in daily_data)), key=lambda x: ['Dom','Seg','Ter','Qua','Qui','Sex','Sab'].index(x) if x in ['Dom','Seg','Ter','Qua','Qui','Sex','Sab'] else 99)
                day_values = {d: 0 for d in days}
                for d in daily_data:
                    day_values[d['dia_semana']] += d['total']
                
                vals = [day_values[d] for d in days]
                ax.bar(days, vals, color='#10B981', alpha=0.7)
            else:
                ax.text(0.5, 0.5, 'Sem dados', ha='center', va='center', fontsize=12, transform=ax.transAxes, color='#888')

            fig.subplots_adjust(bottom=0.15, left=0.12, right=0.95, top=0.95)
            self.weekly_chart.chart_canvas.draw_idle()
        except Exception as e:
            logging.error(f"Erro chart 3: {e}")

        # --- Gráfico 4: Horário de Pico (NOVO) ---
        peak_data = data.get('peak', [])
        try:
            if hasattr(self, 'peak_chart'):
                fig = self.peak_chart.chart_figure
                fig.clear()
                ax = fig.add_subplot(111)
                self._apply_chart_style(ax, fig)

                if peak_data:
                    # Ordenar por hora e preencher lacunas se necessário
                    peak_data.sort(key=lambda x: x['hora'])
                    
                    # Criar lista completa 0-23
                    hours_map = {x['hora']: x['media'] for x in peak_data}
                    hours = list(range(24))
                    medias = [hours_map.get(h, 0) for h in hours]
                    
                    # Gradient plot
                    ax.plot(hours, medias, color='#F59E0B', linewidth=2, marker='o', markersize=4)
                    ax.fill_between(hours, medias, color='#F59E0B', alpha=0.3)
                    ax.set_ylabel('Média Veículos', fontsize=9)
                    ax.set_xlabel('Hora do Dia', fontsize=9)
                    ax.set_xticks(range(0, 24, 2)) # Mostrar a cada 2 horas
                    
                    # Anotar o pico máximo
                    if medias:
                        max_val = max(medias)
                        if max_val > 0:
                            max_idx = medias.index(max_val)
                            ax.annotate(f'Pico: {max_val:.1f}', xy=(hours[max_idx], max_val), 
                                       xytext=(hours[max_idx], max_val + (max_val*0.1)),
                                       arrowprops=dict(facecolor='white', shrink=0.05),
                                       color='white', ha='center', fontsize=8)
                else:
                    ax.text(0.5, 0.5, 'Sem dados', ha='center', va='center', fontsize=12, transform=ax.transAxes, color='#888')

                # Aumentar margem superior para caber a anotação "Pico"
                fig.subplots_adjust(bottom=0.15, left=0.12, right=0.95, top=0.88)
                self.peak_chart.chart_canvas.draw_idle()
        except Exception as e:
            logging.error(f"Erro chart 4: {e}")
