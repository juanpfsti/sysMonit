#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aba de Relatórios de Fila — histórico persistido com filtros, métricas e exportação.
"""
import os
import csv
import threading
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QFileDialog,
    QFrame, QGroupBox, QComboBox, QSpinBox, QDialog,
    QMessageBox, QDateTimeEdit, QLineEdit, QTimeEdit
)
from PyQt5.QtCore import Qt, QDateTime, QTimer, QTime, pyqtSignal
from PyQt5.QtGui import QColor

from .styles import Styles, ThemeColors
from ..core.queue_database import QueueDatabase


# ---------------------------------------------------------------------------
# Tradução de classes YOLO → português
# ---------------------------------------------------------------------------
CLASS_MAP = {
    'car':        'Carro',
    'motorcycle': 'Moto',
    'moto':       'Moto',
    'truck':      'Caminhão',
    'bus':        'Ônibus',
}

def _translate_class(cls):
    """Traduz classe YOLO (car, motorcycle, etc.) para português."""
    return CLASS_MAP.get(str(cls).lower(), cls)


# ---------------------------------------------------------------------------
# Diálogo de exportação personalizada
# ---------------------------------------------------------------------------

class QueueCustomExportDialog(QDialog):
    """Permite escolher intervalo de datas e filtros para exportar em Excel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportar Personalizado — Fila")
        self.setModal(True)
        self.setMinimumWidth(390)
        self.result_data = None

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 13px;
            }}
            QDateTimeEdit, QSpinBox, QComboBox {{
                background-color: {ThemeColors.SURFACE};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 5px;
            }}
            QPushButton {{ padding: 6px 14px; border-radius: 4px; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(22, 22, 22, 22)

        info = QLabel(
            "Selecione o período e os filtros para o relatório Excel.\n"
            "O relatório incluirá resumo e detalhamento por evento."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background-color: {ThemeColors.BORDER}; margin: 4px 0;")
        layout.addWidget(sep)

        form = QVBoxLayout()
        form.setSpacing(8)

        def field_row(label_text, widget):
            r = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(115)
            lbl.setStyleSheet("font-weight: bold;")
            r.addWidget(lbl)
            r.addWidget(widget)
            return r

        self.start_date = QDateTimeEdit()
        self.start_date.setDateTime(QDateTime.currentDateTime().addDays(-7))
        self.start_date.setDisplayFormat("dd/MM/yyyy")
        self.start_date.setCalendarPopup(True)
        form.addLayout(field_row("Data inicial:", self.start_date))

        self.end_date = QDateTimeEdit()
        self.end_date.setDateTime(QDateTime.currentDateTime())
        self.end_date.setDisplayFormat("dd/MM/yyyy")
        self.end_date.setCalendarPopup(True)
        form.addLayout(field_row("Data final:", self.end_date))

        self.start_hour = QSpinBox()
        self.start_hour.setRange(0, 23)
        self.start_hour.setValue(0)
        self.start_hour.setSuffix("h")
        form.addLayout(field_row("Hora início:", self.start_hour))

        self.end_hour = QSpinBox()
        self.end_hour.setRange(0, 23)
        self.end_hour.setValue(23)
        self.end_hour.setSuffix("h")
        form.addLayout(field_row("Hora fim:", self.end_hour))

        self.class_combo = QComboBox()
        self.class_combo.addItems(["Todos", "Carro", "Moto", "Caminhão", "Ônibus"])
        form.addLayout(field_row("Veículo:", self.class_combo))

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet(Styles.BUTTON_SECONDARY)

        btn_ok = QPushButton("Exportar")
        btn_ok.clicked.connect(self._accept)
        btn_ok.setStyleSheet(Styles.BUTTON_PRIMARY)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def _accept(self):
        self.result_data = {
            'start_date':   self.start_date.date().toString("yyyy-MM-dd") + " 00:00:00",
            'end_date':     self.end_date.date().toString("yyyy-MM-dd")   + " 23:59:59",
            'start_hour':   self.start_hour.value(),
            'end_hour':     self.end_hour.value(),
            'vehicle_class': self.class_combo.currentText(),
        }
        self.accept()

    def get_data(self):
        return self.result_data


# ---------------------------------------------------------------------------
# Aba principal
# ---------------------------------------------------------------------------

class QueueReportsTab(QWidget):
    """
    Exibe histórico de eventos de fila com filtros, métricas e exportação Excel.
    Fonte primária: banco de dados (persistente).
    Fallback: sessão em memória do queue_thread atual.
    """

    export_done = pyqtSignal(str)  # sinal thread-safe para mensagens de log

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._threshold_sec = 60
        self._export_in_progress = False
        self.last_scheduled_export_date = None
        # Banco dedicado ao sistema de fila (leitura; o VideoThread escreve no mesmo arquivo)
        self._queue_db = QueueDatabase()

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
            }}
        """ + Styles.PANEL + Styles.TABLE + Styles.SCROLLBAR + Styles.INPUT
            + Styles.BUTTON_PRIMARY + Styles.BUTTON_SECONDARY)

        self._init_ui()

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)

        self.export_timer = QTimer()
        self.export_timer.timeout.connect(self.auto_export_queue_report)

        self.export_schedule_timer = QTimer()
        self.export_schedule_timer.setInterval(60000)
        self.export_schedule_timer.timeout.connect(self.check_scheduled_export)

        self.export_done.connect(self._on_export_done)

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(18)

        header = QLabel("Relatórios de Fila")
        header.setStyleSheet(Styles.HEADER_TITLE)
        layout.addWidget(header)

        # ── Filtros ────────────────────────────────────────────────────
        filters_group = QGroupBox("Filtros de Pesquisa")
        filters_group.setStyleSheet(f"""
            QGroupBox {{
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
                font-weight: bold;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        """)
        filters_layout = QVBoxLayout(filters_group)
        filters_layout.setSpacing(10)

        # Linha 1: Câmera | De | Até | Filtrar
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        row1.addWidget(QLabel("Câmera:"))
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(200)
        self.camera_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        row1.addWidget(self.camera_combo)

        row1.addWidget(QLabel("De:"))
        self.start_date = QDateTimeEdit()
        self.start_date.setDateTime(QDateTime.currentDateTime().addDays(-7))
        self.start_date.setDisplayFormat("dd/MM/yyyy")
        self.start_date.setCalendarPopup(True)
        self.start_date.setMinimumWidth(110)
        row1.addWidget(self.start_date)

        row1.addWidget(QLabel("Até:"))
        self.end_date = QDateTimeEdit()
        self.end_date.setDateTime(QDateTime.currentDateTime())
        self.end_date.setDisplayFormat("dd/MM/yyyy")
        self.end_date.setCalendarPopup(True)
        self.end_date.setMinimumWidth(110)
        row1.addWidget(self.end_date)

        row1.addStretch()

        btn_filter = QPushButton("Filtrar")
        btn_filter.setMinimumHeight(34)
        btn_filter.setMinimumWidth(100)
        btn_filter.setCursor(Qt.PointingHandCursor)
        btn_filter.setStyleSheet(Styles.BUTTON_PRIMARY)
        btn_filter.clicked.connect(self.refresh_data)
        row1.addWidget(btn_filter)

        filters_layout.addLayout(row1)

        # Linha 2: Hora início | Hora fim | Veículo | Atualizar auto
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        row2.addWidget(QLabel("Hora início:"))
        self.start_hour = QSpinBox()
        self.start_hour.setRange(0, 23)
        self.start_hour.setValue(0)
        self.start_hour.setSuffix("h")
        self.start_hour.setMaximumWidth(72)
        row2.addWidget(self.start_hour)

        row2.addWidget(QLabel("Hora fim:"))
        self.end_hour = QSpinBox()
        self.end_hour.setRange(0, 23)
        self.end_hour.setValue(23)
        self.end_hour.setSuffix("h")
        self.end_hour.setMaximumWidth(72)
        row2.addWidget(self.end_hour)

        row2.addWidget(QLabel("Veículo:"))
        self.class_combo = QComboBox()
        self.class_combo.addItems(["Todos", "Carro", "Moto", "Caminhão", "Ônibus"])
        self.class_combo.setMaximumWidth(130)
        self.class_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        row2.addWidget(self.class_combo)

        row2.addStretch()

        row2.addWidget(QLabel("Atualizar:"))
        self.auto_refresh_combo = QComboBox()
        self.auto_refresh_combo.addItems(["Desativado", "1 min", "5 min", "10 min", "30 min"])
        self.auto_refresh_combo.setMaximumWidth(120)
        self.auto_refresh_combo.currentIndexChanged.connect(self._update_auto_refresh)
        self.auto_refresh_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        row2.addWidget(self.auto_refresh_combo)

        filters_layout.addLayout(row2)
        layout.addWidget(filters_group)

        # ── Cards de métricas ─────────────────────────────────────────
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(15)
        self.card_total    = self._make_card("Total de Eventos", "0",     "#3B82F6")
        self.card_avg_wait = self._make_card("Tempo Médio",      "0.0s",  "#8b5cf6")
        self.card_max_wait = self._make_card("Tempo Máximo",     "0.0s",  "#ef4444")
        metrics_row.addWidget(self.card_total)
        metrics_row.addWidget(self.card_avg_wait)
        metrics_row.addWidget(self.card_max_wait)
        layout.addLayout(metrics_row)

        # ── Tabela ────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Entrada", "Saída", "Veículo", "Espera (s)"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Interactive)
        hh.setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Styles.TABLE)
        layout.addWidget(self.table)

        # ── Footer ────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        footer.setSpacing(10)

        self.lbl_count = QLabel("0 registros")
        self.lbl_count.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 13px; font-weight: 600;")
        footer.addWidget(self.lbl_count)

        footer.addStretch()

        btn_refresh = QPushButton("↻ Atualizar")
        btn_refresh.setMinimumHeight(38)
        btn_refresh.setMinimumWidth(110)
        btn_refresh.setCursor(Qt.PointingHandCursor)
        btn_refresh.clicked.connect(self.refresh_data)
        footer.addWidget(btn_refresh)

        btn_export = QPushButton("Exportar Excel")
        btn_export.setMinimumHeight(38)
        btn_export.setMinimumWidth(140)
        btn_export.setCursor(Qt.PointingHandCursor)
        btn_export.setStyleSheet(Styles.ACTION_BUTTON_EMERALD)
        btn_export.clicked.connect(self.export_excel)
        footer.addWidget(btn_export)

        btn_custom = QPushButton("Exportar Personalizado")
        btn_custom.setMinimumHeight(38)
        btn_custom.setMinimumWidth(170)
        btn_custom.setCursor(Qt.PointingHandCursor)
        btn_custom.setStyleSheet(Styles.BUTTON_SECONDARY)
        btn_custom.clicked.connect(self._open_custom_export)
        footer.addWidget(btn_custom)

        layout.addLayout(footer)

        # ── Exportação Automática ──────────────────────────────────────
        auto_group = QGroupBox("Exportação Automática")
        auto_group.setStyleSheet(f"""
            QGroupBox {{
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 12px;
                font-weight: bold;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        """)
        auto_layout = QVBoxLayout(auto_group)
        auto_layout.setSpacing(8)

        # Pasta de destino
        auto_layout.addWidget(QLabel("Pasta para exportações automáticas:"))
        folder_row = QHBoxLayout()
        self.auto_export_folder = QLineEdit(
            self.main_window.config.get('queue_auto_export_folder', '') if self.main_window else ''
        )
        self.auto_export_folder.setPlaceholderText("Selecione uma pasta...")
        self.auto_export_folder.setReadOnly(True)
        self.auto_export_folder.setStyleSheet(Styles.INPUT)
        folder_row.addWidget(self.auto_export_folder)

        btn_folder = QPushButton("Selecionar")
        btn_folder.setMinimumHeight(36)
        btn_folder.setCursor(Qt.PointingHandCursor)
        btn_folder.clicked.connect(self._select_export_folder)
        folder_row.addWidget(btn_folder)
        auto_layout.addLayout(folder_row)

        # Intervalo + horário específico
        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Exportação automática:"))
        self.auto_export_combo = QComboBox()
        self.auto_export_combo.addItems(
            ["Desativado", "5 min", "10 min", "30 min", "60 min", "Horário Específico"]
        )
        self.auto_export_combo.setMaximumWidth(180)
        self.auto_export_combo.currentIndexChanged.connect(self._update_auto_export)
        self.auto_export_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        interval_row.addWidget(self.auto_export_combo)

        self._lbl_at = QLabel("às")
        self._lbl_at.setVisible(False)
        interval_row.addWidget(self._lbl_at)

        self.auto_export_time = QTimeEdit()
        self.auto_export_time.setTime(QTime(18, 0))
        self.auto_export_time.setDisplayFormat("HH:mm")
        self.auto_export_time.setMaximumWidth(80)
        self.auto_export_time.setVisible(False)
        interval_row.addWidget(self.auto_export_time)

        interval_row.addStretch()
        auto_layout.addLayout(interval_row)

        layout.addWidget(auto_group)

    def _make_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.1);
            }}
            QLabel {{ background-color: transparent; border: none; }}
        """)
        card.setMinimumHeight(80)
        cl = QVBoxLayout(card)
        cl.setSpacing(6)
        cl.setContentsMargins(14, 12, 14, 12)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 12px; font-weight: 600;")
        cl.addWidget(lbl_t)
        lbl_v = QLabel(value)
        lbl_v.setStyleSheet("color: white; font-size: 26px; font-weight: 700;")
        lbl_v.setObjectName("metric_value")
        cl.addWidget(lbl_v)
        cl.addStretch()
        return card

    def _set_card(self, card, value):
        card.findChild(QLabel, "metric_value").setText(str(value))

    # ------------------------------------------------------------------
    # Acesso a dados
    # ------------------------------------------------------------------

    def _threshold(self):
        if self.main_window and hasattr(self.main_window, 'config'):
            return self.main_window.config.get('queue_config', {}).get('threshold_seconds', 60)
        return 60

    def _session_records(self):
        """Retorna registros da sessão em memória (fallback quando DB está vazio)."""
        try:
            qt = getattr(self.main_window, 'queue_tab', None)
            if not qt:
                return []
            thread = getattr(qt, 'queue_thread', None)
            if not thread:
                return []
            qm = getattr(thread, 'queue_manager', None)
            if not qm:
                return []
            return [
                {
                    'entry_time':        r['entry_time'],
                    'exit_time':         r['exit_time'],
                    'vehicle_class':     r['vehicle_class'],
                    'wait_duration_sec': r['wait_duration_sec'],
                }
                for r in reversed(qm.session_history)
            ]
        except Exception:
            return []

    def _build_db_filters(self):
        """Monta dicionário de filtros para as queries do banco."""
        start = self.start_date.date().toString("yyyy-MM-dd") + " 00:00:00"
        end   = self.end_date.date().toString("yyyy-MM-dd")   + " 23:59:59"
        sh    = self.start_hour.value()
        eh    = self.end_hour.value()

        # Câmera selecionada (None = todas)
        camera = self.camera_combo.currentData()

        # Veículo selecionado: traduzir de volta para a classe YOLO
        PT_TO_YOLO = {'Carro': 'car', 'Moto': 'moto', 'Caminhão': 'truck', 'Ônibus': 'bus'}
        cls_pt = self.class_combo.currentText()
        cls_yolo = PT_TO_YOLO.get(cls_pt)  # None quando "Todos"

        return dict(
            rtsp_url=camera if camera else None,
            start_date=start,
            end_date=end,
            start_hour=sh if sh > 0 else None,
            end_hour=eh if eh < 23 else None,
            vehicle_class=cls_yolo,
        )

    def _filter_session_records(self, records):
        """Aplica filtros de data/hora/classe nos registros em memória."""
        start_str = self.start_date.date().toString("yyyy-MM-dd") + " 00:00:00"
        end_str   = self.end_date.date().toString("yyyy-MM-dd")   + " 23:59:59"
        sh = self.start_hour.value()
        eh = self.end_hour.value()

        PT_TO_YOLO = {'Carro': 'car', 'Moto': 'moto', 'Caminhão': 'truck', 'Ônibus': 'bus'}
        cls_pt = self.class_combo.currentText()
        cls_yolo = PT_TO_YOLO.get(cls_pt)  # None = todos

        filtered = []
        for r in records:
            et = r['entry_time']
            if et < start_str or et > end_str:
                continue
            # Filtro de hora
            try:
                hour = int(et[11:13])
                if hour < sh or hour > eh:
                    continue
            except (ValueError, IndexError):
                pass
            # Filtro de classe
            if cls_yolo and r['vehicle_class'].lower() != cls_yolo:
                continue
            filtered.append(r)
        return filtered

    def _refresh_camera_combo(self):
        current = self.camera_combo.currentData()
        self.camera_combo.blockSignals(True)
        self.camera_combo.clear()
        self.camera_combo.addItem("Todas as Câmeras", None)
        for url in self._queue_db.get_unique_urls():
            display = url if len(url) <= 55 else url[:52] + "..."
            self.camera_combo.addItem(display, url)
        idx = self.camera_combo.findData(current)
        if idx >= 0:
            self.camera_combo.setCurrentIndex(idx)
        self.camera_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Atualização principal
    # ------------------------------------------------------------------

    def refresh_data(self):
        """Atualiza câmeras, métricas e tabela conforme filtros aplicados."""
        self._refresh_camera_combo()

        threshold = self._threshold()
        records = []
        source = "db"

        try:
            filters = self._build_db_filters()
            records = self._queue_db.get_history(limit=5000, **filters)
        except Exception as e:
            print(f"[ERRO] Falha ao buscar histórico de fila: {e}")
            import traceback; traceback.print_exc()

        # Fallback: sessão em memória quando o banco ainda não tem dados
        if not records:
            session = self._session_records()
            if session:
                records = self._filter_session_records(session)
                source = "session"

        # Métricas
        total = len(records)
        if total:
            waits = [r['wait_duration_sec'] for r in records]
            avg_w = sum(waits) / total
            max_w = max(waits)
        else:
            avg_w = max_w = 0.0

        self._set_card(self.card_total,    str(total))
        self._set_card(self.card_avg_wait, f"{avg_w:.1f}s")
        self._set_card(self.card_max_wait, f"{max_w:.1f}s")

        # Preencher tabela
        self._populate_table(records, threshold)

        suffix = " (sessão atual)" if source == "session" else ""
        self.lbl_count.setText(f"{total} registros{suffix}")

    def _populate_table(self, records, threshold):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(records))

        for i, r in enumerate(records):
            wait = r['wait_duration_sec']
            cls_translated = _translate_class(r['vehicle_class'])

            items = [
                QTableWidgetItem(r['entry_time']),
                QTableWidgetItem(r['exit_time']),
                QTableWidgetItem(cls_translated),
                QTableWidgetItem(f"{wait:.2f}"),
            ]

            if wait > threshold:
                for item in items:
                    item.setForeground(QColor(ThemeColors.DANGER))

            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, col, item)

        self.table.setSortingEnabled(True)

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _update_auto_refresh(self, index):
        self.refresh_timer.stop()
        intervals = {1: 60_000, 2: 5*60_000, 3: 10*60_000, 4: 30*60_000}
        ms = intervals.get(index, 0)
        if ms:
            self.refresh_timer.start(ms)

    # ------------------------------------------------------------------
    # Exportação Excel simples (tabela atual)
    # ------------------------------------------------------------------

    def export_excel(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Não há dados para exportar.")
            return

        default_name = f"fila_relatorio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Relatório de Fila", default_name, "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.endswith('.xlsx'):
            path += '.xlsx'

        try:
            import pandas as pd

            # Calcular resumo a partir dos dados da tabela
            waits = []
            for row in range(self.table.rowCount()):
                try:
                    waits.append(float(self.table.item(row, 3).text()))
                except (ValueError, AttributeError):
                    pass
            total = len(waits)
            avg_w = sum(waits) / total if total else 0.0
            max_w = max(waits) if total else 0.0

            start_str = self.start_date.date().toString("dd/MM/yyyy")
            end_str   = self.end_date.date().toString("dd/MM/yyyy")

            summary = [
                ["RELATÓRIO DE FILA DE ESPERA", "", "", ""],
                ["Período",    f"{start_str} a {end_str}", "", ""],
                ["Câmera",     self.camera_combo.currentText(), "", ""],
                ["Gerado em",  datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "", ""],
                ["", "", "", ""],
                ["RESUMO", "", "", ""],
                ["Total de Eventos",  total,          "", ""],
                ["Tempo Médio (s)",   f"{avg_w:.2f}", "", ""],
                ["Tempo Máximo (s)",  f"{max_w:.2f}", "", ""],
                ["", "", "", ""],
            ]

            headers = [self.table.horizontalHeaderItem(c).text()
                       for c in range(self.table.columnCount())]
            data_rows = [
                [(self.table.item(row, col).text() if self.table.item(row, col) else '')
                 for col in range(self.table.columnCount())]
                for row in range(self.table.rowCount())
            ]

            final = summary + [headers] + data_rows
            df = pd.DataFrame(final)
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Relatório Fila', index=False, header=False)
                ws = writer.sheets['Relatório Fila']
                ws.column_dimensions['A'].width = 24
                ws.column_dimensions['B'].width = 24
                ws.column_dimensions['C'].width = 14
                ws.column_dimensions['D'].width = 14

            QMessageBox.information(self, "Sucesso", f"Exportado com sucesso!\n{path}")

        except ImportError:
            QMessageBox.critical(self, "Erro",
                "Instale 'openpyxl' para exportar Excel:\npip install openpyxl")
        except PermissionError:
            QMessageBox.critical(self, "Erro",
                "Arquivo em uso ou sem permissão de escrita.\nFeche o arquivo e tente novamente.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao exportar:\n{e}")

    # ------------------------------------------------------------------
    # Exportação personalizada (Excel com relatório completo)
    # ------------------------------------------------------------------

    def _open_custom_export(self):
        dialog = QueueCustomExportDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if data:
                self._export_custom_excel(data)

    def _export_custom_excel(self, params):
        """Gera Excel com cabeçalho, resumo e detalhamento para o período escolhido."""
        import pandas as pd
        PT_TO_YOLO = {'Carro': 'car', 'Moto': 'moto', 'Caminhão': 'truck', 'Ônibus': 'bus'}
        cls_pt   = params['vehicle_class']
        cls_yolo = PT_TO_YOLO.get(cls_pt)

        camera = self.camera_combo.currentData()

        filters = dict(
            rtsp_url=camera if camera else None,
            start_date=params['start_date'],
            end_date=params['end_date'],
            start_hour=params['start_hour'] if params['start_hour'] > 0  else None,
            end_hour=params['end_hour']   if params['end_hour']   < 23 else None,
            vehicle_class=cls_yolo,
        )

        try:
            records = self._queue_db.get_history(limit=100_000, **filters)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao buscar dados:\n{e}")
            return

        # Fallback para sessão em memória
        if not records:
            session = self._session_records()
            # Aplicar filtros manuais
            start_str = params['start_date']
            end_str   = params['end_date']
            sh = params['start_hour']
            eh = params['end_hour']
            for r in session:
                et = r['entry_time']
                if et < start_str or et > end_str:
                    continue
                try:
                    if int(et[11:13]) < sh or int(et[11:13]) > eh:
                        continue
                except (ValueError, IndexError):
                    pass
                if cls_yolo and r['vehicle_class'].lower() != cls_yolo:
                    continue
                records.append(r)

        if not records:
            QMessageBox.warning(self, "Aviso", "Nenhum dado encontrado para o período selecionado.")
            return

        start_label = params['start_date'][:10].replace('-', '')
        end_label   = params['end_date'][:10].replace('-', '')
        default_name = f"fila_relatorio_{start_label}_a_{end_label}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Relatório de Fila", default_name, "Excel (*.xlsx)"
        )
        if not path:
            return
        if not path.endswith('.xlsx'):
            path += '.xlsx'

        try:
            waits = [r['wait_duration_sec'] for r in records]
            total  = len(waits)
            avg_w  = sum(waits) / total if total else 0
            max_w  = max(waits) if total else 0
            min_w  = min(waits) if total else 0

            camera_label = self.camera_combo.currentText()

            header_rows = [
                ["RELATÓRIO DE FILA DE ESPERA", ""],
                ["Período",    f"{params['start_date'][:10]} a {params['end_date'][:10]}"],
                ["Horário",    f"{params['start_hour']}h – {params['end_hour']}h"],
                ["Câmera",     camera_label],
                ["Veículo",    cls_pt],
                ["Gerado em",  datetime.now().strftime("%d/%m/%Y %H:%M:%S")],
                ["", ""],
            ]

            summary_rows = [
                ["RESUMO", ""],
                ["Total de Eventos",  total],
                ["Tempo Médio (s)",   f"{avg_w:.2f}"],
                ["Tempo Máximo (s)",  f"{max_w:.2f}"],
                ["Tempo Mínimo (s)",  f"{min_w:.2f}"],
                ["", ""],
            ]

            detail_header = [["DETALHAMENTO", "", "", ""]]
            detail_cols   = [["Entrada", "Saída", "Veículo", "Espera (s)"]]
            detail_rows   = [
                [
                    r['entry_time'],
                    r['exit_time'],
                    _translate_class(r['vehicle_class']),
                    f"{r['wait_duration_sec']:.2f}",
                ]
                for r in records
            ]

            final_data = header_rows + summary_rows + detail_header + detail_cols + detail_rows
            df = pd.DataFrame(final_data)

            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Relatório Fila', index=False, header=False)
                ws = writer.sheets['Relatório Fila']
                ws.column_dimensions['A'].width = 24
                ws.column_dimensions['B'].width = 24
                ws.column_dimensions['C'].width = 14
                ws.column_dimensions['D'].width = 14

            QMessageBox.information(self, "Sucesso", f"Relatório Excel exportado!\n{path}")

        except ImportError:
            QMessageBox.critical(self, "Erro",
                "Instale 'openpyxl' para exportar Excel:\npip install openpyxl")
        except Exception as e:
            import traceback; traceback.print_exc()
            QMessageBox.critical(self, "Erro", f"Erro ao gerar Excel:\n{e}")

    # ------------------------------------------------------------------
    # Exportação automática
    # ------------------------------------------------------------------

    def _select_export_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar Pasta para Exportação Automática",
            self.auto_export_folder.text() or os.path.expanduser("~"),
            QFileDialog.ShowDirsOnly
        )
        if folder:
            self.auto_export_folder.setText(folder)
            if self.main_window:
                self.main_window.config.set('queue_auto_export_folder', folder)

    def _update_auto_export(self, index):
        self.export_timer.stop()
        self.export_schedule_timer.stop()
        self._lbl_at.setVisible(False)
        self.auto_export_time.setVisible(False)

        if index == 5:  # Horário específico
            self._lbl_at.setVisible(True)
            self.auto_export_time.setVisible(True)
            self.export_schedule_timer.start()
            return

        intervals = {1: 5*60_000, 2: 10*60_000, 3: 30*60_000, 4: 60*60_000}
        ms = intervals.get(index, 0)
        if ms:
            self.export_timer.start(ms)

    def check_scheduled_export(self):
        from datetime import date as _date, datetime as _dt
        current_time = _dt.now()
        current_date = _date.today()
        scheduled = self.auto_export_time.time()
        scheduled_minutes = scheduled.hour() * 60 + scheduled.minute()
        current_minutes = current_time.hour * 60 + current_time.minute
        in_window = scheduled_minutes <= current_minutes <= scheduled_minutes + 2
        if in_window and self.last_scheduled_export_date != current_date:
            self.auto_export_queue_report()
            self.last_scheduled_export_date = current_date

    def auto_export_queue_report(self):
        if self._export_in_progress:
            return
        folder = self.auto_export_folder.text()
        if not folder or not os.path.isdir(folder):
            self.export_timer.stop()
            self.auto_export_combo.setCurrentIndex(0)
            QMessageBox.warning(self, "Pasta Não Configurada",
                "Configure a pasta de exportação antes de ativar a exportação automática.")
            return
        self._export_in_progress = True
        threading.Thread(target=self._do_queue_export, args=(folder,), daemon=True).start()

    def _do_queue_export(self, folder):
        try:
            import pandas as pd
            filters = self._build_db_filters()
            records = self._queue_db.get_history(limit=100_000, **filters)
            if not records:
                records = self._filter_session_records(self._session_records())
            if not records:
                self.export_done.emit("⚠️ Auto-export fila: sem dados para exportar.")
                return

            waits = [r['wait_duration_sec'] for r in records]
            total = len(waits)
            avg_w = sum(waits) / total if total else 0.0
            max_w = max(waits) if total else 0.0

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(folder, f"fila_auto_{timestamp}.xlsx")

            summary = [
                ["RELATÓRIO DE FILA DE ESPERA (AUTO)", "", "", ""],
                ["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "", ""],
                ["", "", "", ""],
                ["RESUMO", "", "", ""],
                ["Total de Eventos",  total,          "", ""],
                ["Tempo Médio (s)",   f"{avg_w:.2f}", "", ""],
                ["Tempo Máximo (s)",  f"{max_w:.2f}", "", ""],
                ["", "", "", ""],
            ]

            headers  = [["Entrada", "Saída", "Veículo", "Espera (s)"]]
            data_rows = [
                [r['entry_time'], r['exit_time'],
                 _translate_class(r['vehicle_class']),
                 f"{r['wait_duration_sec']:.2f}"]
                for r in records
            ]

            df = pd.DataFrame(summary + headers + data_rows)
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Relatório Fila', index=False, header=False)
                ws = writer.sheets['Relatório Fila']
                for col, width in zip(['A', 'B', 'C', 'D'], [24, 24, 14, 14]):
                    ws.column_dimensions[col].width = width

            self.export_done.emit(f"✅ Auto-export fila: {os.path.basename(path)}")
        except Exception as e:
            self.export_done.emit(f"❌ Erro no auto-export fila: {e}")
        finally:
            self._export_in_progress = False

    def _on_export_done(self, msg):
        """Recebe resultado da thread de exportação (thread-safe via sinal)."""
        print(f"[QueueReports] {msg}")
        # Repassa ao log da janela principal, se disponível
        if self.main_window and hasattr(self.main_window, 'add_log'):
            self.main_window.add_log(msg)

    def stop_timers(self):
        """Para todos os timers — chamar no encerramento da aplicação."""
        self.export_timer.stop()
        self.export_schedule_timer.stop()
        self.refresh_timer.stop()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_data()
