#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aba de Análise de Fila — gráfico de tendência de espera e histograma de distribuição.
"""
import logging
import traceback
import numpy as np
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QFrame, QPushButton, QScrollArea, QComboBox,
    QDateTimeEdit, QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QDateTime

from .styles import Styles, ThemeColors
from ..core.queue_database import QueueDatabase

try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


CLASS_MAP  = {'car': 'Carro', 'motorcycle': 'Moto', 'moto': 'Moto', 'truck': 'Caminhão', 'bus': 'Ônibus'}
PT_TO_YOLO = {v: k for k, v in CLASS_MAP.items()}

# Faixas do histograma de distribuição
BUCKETS = [
    (0,   30,           '0–30s'),
    (31,  60,           '31–60s'),
    (61,  120,          '1–2min'),
    (121, 300,          '2–5min'),
    (301, float('inf'), '>5min'),
]
BUCKET_COLORS = ['#10B981', '#22c55e', '#f59e0b', '#ef4444', '#7f1d1d']


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class QueueAnalysisWorker(QThread):
    """Carrega e processa dados do banco de fila em segundo plano."""
    data_ready    = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, queue_db, start_date, end_date,
                 rtsp_url=None, vehicle_class=None, threshold_sec=60):
        super().__init__()
        self.queue_db      = queue_db
        self.start_date    = start_date
        self.end_date      = end_date
        self.rtsp_url      = rtsp_url
        self.vehicle_class = vehicle_class
        self.threshold_sec = threshold_sec

    def run(self):
        try:
            records = self.queue_db.get_history(
                rtsp_url=self.rtsp_url,
                start_date=self.start_date,
                end_date=self.end_date,
                vehicle_class=self.vehicle_class,
                limit=100_000,
            )

            total = len(records)
            waits = [r['wait_duration_sec'] for r in records]
            avg_wait = sum(waits) / total if total else 0.0
            max_wait = max(waits) if total else 0.0
            over_threshold = sum(1 for w in waits if w > self.threshold_sec)

            # ---- 1. Tendência horária ----------------------------------------
            # Agrupa tempo médio de espera por hora do dia (0-23)
            hourly: dict[int, list] = {}
            for r in records:
                try:
                    hour = int(r['entry_time'][11:13])
                    hourly.setdefault(hour, []).append(r['wait_duration_sec'])
                except (ValueError, IndexError):
                    pass

            means_raw = [
                (sum(hourly[h]) / len(hourly[h])) if h in hourly else None
                for h in range(24)
            ]

            # Média móvel centrada de janela 3 h (suaviza picos isolados)
            means_arr = np.array([v if v is not None else np.nan for v in means_raw])
            rolling   = np.full(24, np.nan)
            for i in range(24):
                window = means_arr[max(0, i - 1): i + 2]
                valid  = window[~np.isnan(window)]
                if len(valid):
                    rolling[i] = float(valid.mean())

            # ---- 2. Histograma -----------------------------------------------
            histogram = {label: 0 for _, _, label in BUCKETS}
            for w in waits:
                for lo, hi, label in BUCKETS:
                    if lo <= w <= hi:
                        histogram[label] += 1
                        break

            self.data_ready.emit({
                'total':          total,
                'avg_wait':       avg_wait,
                'max_wait':       max_wait,
                'over_threshold': over_threshold,
                'threshold':      self.threshold_sec,
                'hourly_raw':     means_raw,        # list[float|None], len=24
                'hourly_rolling': rolling.tolist(), # list[float], may contain nan
                'histogram':      histogram,
            })

        except Exception as e:
            logging.error(f"[QueueAnalysisWorker] {e}\n{traceback.format_exc()}")
            self.error_occurred.emit(str(e))


# ---------------------------------------------------------------------------
# Aba principal
# ---------------------------------------------------------------------------

class QueueAnalysisTab(QWidget):
    """
    Exibe dois gráficos sobre os dados de fila persistidos:
      1. Tendência de Espera por Hora do Dia (linha + área + média móvel)
      2. Histograma de Distribuição de Tempos de Espera (barras por faixa)
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window        = main_window
        self._queue_db          = QueueDatabase()
        self._worker            = None
        self._refresh_in_progress = False
        self.custom_start       = None
        self.custom_end         = None

        self._init_ui()

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
            }}
        """ + Styles.PANEL + Styles.INPUT + Styles.BUTTON_PRIMARY + Styles.SCROLLBAR)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(18)

        # ── Barra de ferramentas ──────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        header = QLabel("Análise de Fila")
        header.setStyleSheet(Styles.HEADER_TITLE)
        toolbar.addWidget(header)
        toolbar.addStretch()

        for label, attr, items, width in [
            ("Período:",  "period_combo",       ["Hoje", "Últimos 7 dias", "Últimos 30 dias", "Personalizado"], 170),
            ("Câmera:",   "camera_combo",        [],                                                             190),
            ("Veículo:",  "class_combo",         ["Todos", "Carro", "Moto", "Caminhão", "Ônibus"],              120),
            ("Atualizar:","auto_refresh_combo",  ["Desativado", "5 min", "10 min", "30 min"],                   120),
        ]:
            toolbar.addWidget(QLabel(label))
            combo = QComboBox()
            if items:
                combo.addItems(items)
            combo.setMinimumHeight(36)
            combo.setMinimumWidth(width)
            combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
            setattr(self, attr, combo)
            toolbar.addWidget(combo)

        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        self.auto_refresh_combo.currentIndexChanged.connect(self._update_auto_refresh)

        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setMinimumHeight(36)
        self.btn_refresh.setMinimumWidth(110)
        self.btn_refresh.setStyleSheet(Styles.BUTTON_PRIMARY)
        self.btn_refresh.clicked.connect(self.refresh_data)
        toolbar.addWidget(self.btn_refresh)

        main_layout.addLayout(toolbar)

        # Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(0, 0, 6, 0)

        # ── Cards de métricas ─────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.card_total    = self._make_card("Total de Eventos",    "0",    "#3B82F6")
        self.card_avg_wait = self._make_card("Tempo Médio",         "0.0s", "#8b5cf6")
        self.card_max_wait = self._make_card("Tempo Máximo",        "0.0s", "#ef4444")
        self.card_over_thr = self._make_card("Acima do Limiar",     "0",    "#f59e0b")
        for card in (self.card_total, self.card_avg_wait,
                     self.card_max_wait, self.card_over_thr):
            cards_row.addWidget(card)
        content_layout.addLayout(cards_row)

        if MATPLOTLIB_AVAILABLE:
            # Gráfico 1: Tendência (toda a largura)
            self.trend_chart = self._make_chart_group(
                "Tendência de Espera por Hora do Dia",
                height=310,
            )
            content_layout.addWidget(self.trend_chart)

            # Gráfico 2: Histograma
            self.hist_chart = self._make_chart_group(
                "Distribuição de Tempos de Espera",
                height=290,
            )
            content_layout.addWidget(self.hist_chart)
        else:
            lbl = QLabel(
                "Matplotlib não instalado. Instale com:\n"
                "pip install matplotlib"
            )
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 14px; padding: 40px;"
            )
            content_layout.addWidget(lbl)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    # ------------------------------------------------------------------
    # Helpers de UI
    # ------------------------------------------------------------------

    def _make_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.08);
            }}
            QLabel {{ background-color: transparent; border: none; }}
        """)
        card.setMinimumHeight(78)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(
            "color: rgba(255,255,255,0.85); font-size: 11px; font-weight: 600;"
        )
        lay.addWidget(lbl_t)
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet("color: white; font-size: 24px; font-weight: 700;")
        lbl_v.setObjectName("metric_value")
        lay.addWidget(lbl_v)
        return card

    def _set_card(self, card, value):
        card.findChild(QLabel, "metric_value").setText(str(value))

    def _make_chart_group(self, title, height=300):
        group = QGroupBox(title)
        group.setStyleSheet(f"""
            QGroupBox {{
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
                font-weight: bold;
                font-size: 13px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; }}
        """)
        lay = QVBoxLayout(group)
        fig    = Figure(figsize=(10, height / 100), dpi=100,
                        facecolor=ThemeColors.BACKGROUND)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setMinimumHeight(height)
        canvas.setStyleSheet(
            f"background-color: {ThemeColors.BACKGROUND}; border-radius: 6px;"
        )
        lay.addWidget(canvas)
        group.chart_figure = fig
        group.chart_canvas = canvas
        return group

    def _apply_chart_style(self, ax, fig):
        ax.set_facecolor(ThemeColors.BACKGROUND)
        fig.patch.set_facecolor(ThemeColors.BACKGROUND)
        ax.tick_params(colors=ThemeColors.TEXT_SECONDARY, which='both', labelsize=9)
        ax.xaxis.label.set_color(ThemeColors.TEXT_SECONDARY)
        ax.yaxis.label.set_color(ThemeColors.TEXT_SECONDARY)
        ax.grid(True, alpha=0.12, color=ThemeColors.BORDER,
                linestyle='-', linewidth=0.8)
        for spine in ax.spines.values():
            spine.set_edgecolor(ThemeColors.BORDER)
            spine.set_linewidth(0.8)

    # ------------------------------------------------------------------
    # Filtros / Período
    # ------------------------------------------------------------------

    def _get_dates(self):
        idx = self.period_combo.currentIndex()
        now = datetime.now()
        if idx == 0:
            return now.strftime('%Y-%m-%d') + ' 00:00:00', now.strftime('%Y-%m-%d %H:%M:%S')
        elif idx == 1:
            return ((now - timedelta(days=7)).strftime('%Y-%m-%d') + ' 00:00:00',
                    now.strftime('%Y-%m-%d %H:%M:%S'))
        elif idx == 2:
            return ((now - timedelta(days=30)).strftime('%Y-%m-%d') + ' 00:00:00',
                    now.strftime('%Y-%m-%d %H:%M:%S'))
        else:  # Personalizado
            return self.custom_start, self.custom_end

    def _refresh_cameras(self):
        current = self.camera_combo.currentData()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        self.camera_combo.addItem("Todas as Câmeras", None)
        for url in self._queue_db.get_unique_urls():
            display = url if len(url) <= 48 else url[:45] + "..."
            self.camera_combo.addItem(display, url)
        idx = self.camera_combo.findData(current)
        if idx >= 0:
            self.camera_combo.setCurrentIndex(idx)
        self.camera_combo.blockSignals(False)

    def _get_threshold(self):
        try:
            return int(
                self.main_window.config.get('queue_config', {})
                    .get('threshold_seconds', 60)
            )
        except Exception:
            return 60

    # ------------------------------------------------------------------
    # Atualização de dados
    # ------------------------------------------------------------------

    def refresh_data(self):
        if self._refresh_in_progress:
            return

        self._refresh_cameras()

        start, end = self._get_dates()
        if not start or not end:
            return

        camera    = self.camera_combo.currentData()
        cls_pt    = self.class_combo.currentText()
        cls_yolo  = PT_TO_YOLO.get(cls_pt)   # None = todos
        threshold = self._get_threshold()

        self._refresh_in_progress = True
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Carregando...")

        self._worker = QueueAnalysisWorker(
            self._queue_db, start, end,
            rtsp_url=camera, vehicle_class=cls_yolo,
            threshold_sec=threshold,
        )
        self._worker.data_ready.connect(self._on_data_ready)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    # ------------------------------------------------------------------
    # Callbacks do worker
    # ------------------------------------------------------------------

    def _on_data_ready(self, data):
        total         = data['total']
        avg_wait      = data['avg_wait']
        max_wait      = data['max_wait']
        over_threshold = data['over_threshold']
        threshold     = data['threshold']

        self._set_card(self.card_total,    str(total))
        self._set_card(self.card_avg_wait, f"{avg_wait:.1f}s")
        self._set_card(self.card_max_wait, f"{max_wait:.1f}s")
        self._set_card(self.card_over_thr, str(over_threshold))

        # Atualizar tooltip do card "Acima do Limiar"
        self.card_over_thr.setToolTip(
            f"Veículos com espera > {threshold}s (limiar configurado)"
        )

        if MATPLOTLIB_AVAILABLE:
            self._draw_trend(data)
            self._draw_histogram(data)

    def _on_worker_error(self, msg):
        logging.error(f"[QueueAnalysis] Worker error: {msg}")
        self.btn_refresh.setText("Erro!")
        QTimer.singleShot(2000, lambda: self.btn_refresh.setText("Atualizar"))

    def _on_worker_finished(self):
        self._refresh_in_progress = False
        self.btn_refresh.setEnabled(True)
        self.btn_refresh.setText("Atualizar")
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    # ------------------------------------------------------------------
    # Desenho dos gráficos
    # ------------------------------------------------------------------

    def _draw_trend(self, data):
        """Gráfico 1: linha de média por hora + média móvel (3h) + fill."""
        try:
            fig = self.trend_chart.chart_figure
            fig.clear()
            ax = fig.add_subplot(111)
            self._apply_chart_style(ax, fig)

            hours   = list(range(24))
            raw     = data['hourly_raw']      # list[float|None], len=24
            rolling = data['hourly_rolling']  # list[float|nan], len=24

            has_data = any(v is not None for v in raw)

            if has_data:
                # Pontos brutos (média real por hora)
                raw_x = [h for h, v in enumerate(raw) if v is not None]
                raw_y = [v for v in raw if v is not None]
                ax.scatter(raw_x, raw_y,
                           color='#60a5fa', alpha=0.55, s=32, zorder=3,
                           label='Média/hora')

                # Linha de média móvel (3h)
                roll_arr  = np.array(rolling, dtype=float)
                roll_mask = ~np.isnan(roll_arr)
                if roll_mask.any():
                    # Usar NaN onde não há dados para não ligar pontos distantes
                    roll_plot = np.where(roll_mask, roll_arr, np.nan)
                    ax.plot(hours, roll_plot,
                            color='#3B82F6', linewidth=2.5,
                            label='Média móvel (3h)', zorder=4)
                    # Fill abaixo da linha
                    ax.fill_between(hours, roll_plot, 0,
                                    where=roll_mask,
                                    alpha=0.15, color='#3B82F6', interpolate=True)


                ax.set_ylabel('Tempo de Espera (s)', fontsize=9,
                              color=ThemeColors.TEXT_SECONDARY)
                ax.set_xlabel('Hora do Dia', fontsize=9,
                              color=ThemeColors.TEXT_SECONDARY)
                ax.set_xticks(range(0, 24, 2))
                ax.set_xticklabels([f'{h:02d}h' for h in range(0, 24, 2)],
                                   fontsize=8)
                ax.set_xlim(-0.5, 23.5)
                ax.legend(fontsize=8, framealpha=0.15,
                          facecolor=ThemeColors.SURFACE,
                          labelcolor='white', loc='upper left')
            else:
                ax.text(0.5, 0.5, 'Sem dados para o período selecionado',
                        ha='center', va='center', fontsize=12,
                        transform=ax.transAxes,
                        color=ThemeColors.TEXT_SECONDARY)

            fig.subplots_adjust(bottom=0.14, left=0.09, right=0.97, top=0.91)
            self.trend_chart.chart_canvas.draw_idle()

        except Exception as e:
            logging.error(f"[QueueAnalysis] Trend chart error: {e}\n{traceback.format_exc()}")

    def _draw_histogram(self, data):
        """Gráfico 2: barras por faixa de tempo de espera com %, cor gradiente."""
        try:
            fig = self.hist_chart.chart_figure
            fig.clear()
            ax = fig.add_subplot(111)
            self._apply_chart_style(ax, fig)

            histogram = data['histogram']
            labels = [label for _, _, label in BUCKETS]
            counts = [histogram.get(label, 0) for label in labels]
            total  = sum(counts)

            if total > 0:
                x_pos = range(len(labels))
                bars  = ax.bar(x_pos, counts,
                               color=BUCKET_COLORS[:len(labels)],
                               edgecolor=(1, 1, 1, 0.08),
                               linewidth=0.8,
                               width=0.6)
                ax.set_xticks(list(x_pos))
                ax.set_xticklabels(labels, fontsize=9)

                # Anotar contagem e percentual em cada barra
                max_h = max(counts)
                for bar, count in zip(bars, counts):
                    if count > 0:
                        pct = count / total * 100
                        ax.text(
                            bar.get_x() + bar.get_width() / 2,
                            bar.get_height() + max_h * 0.015,
                            f'{count}\n({pct:.0f}%)',
                            ha='center', va='bottom',
                            fontsize=9, color='#e2e8f0',
                        )

                ax.set_ylabel('Nº de Veículos', fontsize=9,
                              color=ThemeColors.TEXT_SECONDARY)
                ax.set_xlabel('Faixa de Espera', fontsize=9,
                              color=ThemeColors.TEXT_SECONDARY)
                ax.set_ylim(0, max_h * 1.30)
            else:
                ax.text(0.5, 0.5, 'Sem dados para o período selecionado',
                        ha='center', va='center', fontsize=12,
                        transform=ax.transAxes,
                        color=ThemeColors.TEXT_SECONDARY)

            fig.subplots_adjust(bottom=0.14, left=0.09, right=0.97, top=0.95)
            self.hist_chart.chart_canvas.draw_idle()

        except Exception as e:
            logging.error(f"[QueueAnalysis] Histogram error: {e}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    # Período personalizado / Auto-refresh
    # ------------------------------------------------------------------

    def _on_period_changed(self, index):
        if index == 3:  # Personalizado
            dlg = QDialog(self)
            dlg.setWindowTitle("Selecionar Período")
            dlg.setMinimumWidth(370)
            dlg.setStyleSheet(f"""
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
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 18, 20, 16)
            lay.setSpacing(12)

            for row_label, attr in [("Data Inicial:", "start_edit"),
                                     ("Data Final:",   "end_edit")]:
                row = QHBoxLayout()
                lbl = QLabel(row_label)
                lbl.setFixedWidth(90)
                row.addWidget(lbl)
                edit = QDateTimeEdit()
                edit.setDateTime(QDateTime.currentDateTime().addDays(-7
                                 if "Inicial" in row_label else 0))
                edit.setDisplayFormat("dd/MM/yyyy")
                edit.setCalendarPopup(True)
                row.addWidget(edit)
                lay.addLayout(row)
                setattr(dlg, attr, edit)

            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.button(QDialogButtonBox.Ok).setText("Confirmar")
            btns.button(QDialogButtonBox.Cancel).setText("Cancelar")
            btns.button(QDialogButtonBox.Cancel).setStyleSheet(
                f"background-color: {ThemeColors.SURFACE_LIGHT}; color: {ThemeColors.TEXT_PRIMARY};"
                f"border: 1px solid {ThemeColors.BORDER}; border-radius: 5px; padding: 6px 16px;"
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            lay.addWidget(btns)

            if dlg.exec_() == QDialog.Accepted:
                self.custom_start = dlg.start_edit.date().toString("yyyy-MM-dd") + " 00:00:00"
                self.custom_end   = dlg.end_edit.date().toString("yyyy-MM-dd")   + " 23:59:59"
                self.refresh_data()
            else:
                self.period_combo.blockSignals(True)
                self.period_combo.setCurrentIndex(1)
                self.period_combo.blockSignals(False)
        else:
            self.refresh_data()

    def _update_auto_refresh(self, index):
        self.refresh_timer.stop()
        ms = {1: 5 * 60_000, 2: 10 * 60_000, 3: 30 * 60_000}.get(index)
        if ms:
            self.refresh_timer.start(ms)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_data()
