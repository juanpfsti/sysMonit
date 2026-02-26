#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aba de Histórico - Tabela de eventos e exportação CSV
"""

import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QDateTimeEdit, QHeaderView, QFileDialog, QMessageBox,
    QGroupBox, QSpinBox, QComboBox, QCheckBox, QFrame, QTimeEdit, QDialog
)
from PyQt5.QtCore import Qt, QDateTime, QTimer, QTime
from .styles import Styles, ThemeColors



class CustomExportDialog(QDialog):
    """Diálogo para exportação personalizada por data e horário limite"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportar Personalizado")
        self.setModal(True)
        self.setMinimumWidth(350)
        self.selected_date = None
        self.selected_time = None
        
        # Estilo
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 13px;
            }}
            QDateEdit, QTimeEdit {{
                background-color: {ThemeColors.SURFACE};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 4px;
                padding: 5px;
            }}
            QPushButton {{
                padding: 6px 12px;
                border-radius: 4px;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Info
        info = QLabel("Selecione o dia e o horário limite para o relatório.\n"
                      "O relatório mostrará o total acumulado até o horário escolhido.")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Inputs
        form_layout = QVBoxLayout()
        form_layout.setSpacing(10)
        
        # Data
        lbl_date = QLabel("Data do Relatório:")
        lbl_date.setStyleSheet("font-weight: bold;")
        form_layout.addWidget(lbl_date)
        
        self.date_edit = QDateTimeEdit()
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        form_layout.addWidget(self.date_edit)
        
        # Hora Limite
        lbl_time = QLabel("Horário Limite (até):")
        lbl_time.setStyleSheet("font-weight: bold;")
        form_layout.addWidget(lbl_time)
        
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(18, 0)) # Default 18:00
        self.time_edit.setDisplayFormat("HH:mm")
        form_layout.addWidget(self.time_edit)
        
        layout.addLayout(form_layout)
        
        # Botões
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet(Styles.BUTTON_SECONDARY)
        
        btn_ok = QPushButton("Exportar")
        btn_ok.clicked.connect(self.accept_export)
        btn_ok.setStyleSheet(Styles.BUTTON_PRIMARY)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        
        layout.addLayout(btn_layout)
        
    def accept_export(self):
        self.selected_date = self.date_edit.date()
        self.selected_time = self.time_edit.time()
        self.accept()

    def get_data(self):
        return self.selected_date, self.selected_time


class HistoryTab(QWidget):
    """Aba de histórico com tabela de eventos e exportação"""

    def __init__(self, database, config, parent=None):
        super().__init__(parent)
        self.database = database
        self.config = config
        self.current_rtsp_url = ''
        self.init_ui()

        # Timer para atualização automática periódica (configurável pelo usuário)
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_current_view)
        # Não inicia automaticamente - usuário escolhe no dropdown

        # Timer para exportação automática periódica
        self.export_timer = QTimer()
        self.export_timer.timeout.connect(self.auto_export_xlsx)
        # Não inicia automaticamente - usuário habilita via checkbox

        # Timer para verificação de horário específico (verifica a cada minuto)
        self.export_schedule_timer = QTimer()
        self.export_schedule_timer.timeout.connect(self.check_scheduled_export)
        self.export_schedule_timer.setInterval(60000)  # 60 segundos

        # Controle de última exportação agendada
        self.last_scheduled_export_date = None

    def init_ui(self):
        """Inicializa interface da aba de histórico"""
        # Aplicar estilo dark mode ao widget principal
        style = f"""
            QWidget {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
                font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
            }}
        """ + (
            Styles.PANEL +
            Styles.TABLE +
            Styles.SCROLLBAR +
            Styles.INPUT +
            Styles.BUTTON_PRIMARY +
            Styles.BUTTON_SECONDARY
        )
        self.setStyleSheet(style)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)

        # Header simples (sem botão de alternância)
        header = QLabel("Resumo Horário")
        header.setStyleSheet(Styles.HEADER_TITLE)
        layout.addWidget(header)

        # Filtros - Reorganizados em grid compacto
        filters_group = QGroupBox("Filtros de Pesquisa")
        filters_main_layout = QVBoxLayout()
        filters_main_layout.setSpacing(10)

        # Linha 1: Fonte e Período
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Fonte
        row1.addWidget(QLabel("Fonte:"))
        self.rtsp_filter_combo = QComboBox()
        self.rtsp_filter_combo.setMinimumWidth(180)
        self.rtsp_filter_combo.setToolTip("Selecione a câmera")
        self.rtsp_filter_combo.addItem("Todas as Fontes", "")
        self.rtsp_filter_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        self.refresh_rtsp_sources()
        row1.addWidget(self.rtsp_filter_combo)

        # Data inicial
        row1.addWidget(QLabel("De:"))
        self.start_date = QDateTimeEdit()
        self.start_date.setDateTime(QDateTime.currentDateTime().addDays(-1))
        self.start_date.setDisplayFormat("dd/MM/yyyy")  # Removido HH:mm
        self.start_date.setCalendarPopup(True)
        self.start_date.setMinimumWidth(110)
        row1.addWidget(self.start_date)

        # Data final
        row1.addWidget(QLabel("Até:"))
        self.end_date = QDateTimeEdit()
        self.end_date.setDateTime(QDateTime.currentDateTime())
        self.end_date.setDisplayFormat("dd/MM/yyyy")  # Removido HH:mm
        self.end_date.setCalendarPopup(True)
        self.end_date.setMinimumWidth(110)
        row1.addWidget(self.end_date)

        row1.addStretch()

        # Botão filtrar
        self.btn_filter = QPushButton("Filtrar")
        self.btn_filter.setMinimumHeight(36)
        self.btn_filter.setMinimumWidth(110)
        self.btn_filter.setCursor(Qt.PointingHandCursor)
        self.btn_filter.clicked.connect(self.refresh_current_view)
        row1.addWidget(self.btn_filter)

        filters_main_layout.addLayout(row1)

        # Linha 2: Automações (colapsada por padrão)
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        row2.addWidget(QLabel("Atualizar:"))
        self.auto_refresh_combo = QComboBox()
        self.auto_refresh_combo.addItems(["Desativado", "5 min", "10 min", "30 min", "45 min"])
        self.auto_refresh_combo.setMaximumWidth(120)
        self.auto_refresh_combo.currentIndexChanged.connect(self.update_auto_refresh)
        self.auto_refresh_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        row2.addWidget(self.auto_refresh_combo)

        row2.addWidget(QLabel("Exportar:"))
        self.auto_export_combo = QComboBox()
        self.auto_export_combo.addItems(["Desativado", "5 min", "10 min", "30 min", "60 min", "Horário Específico"])
        self.auto_export_combo.setMaximumWidth(140)
        self.auto_export_combo.currentIndexChanged.connect(self.update_auto_export)
        self.auto_export_combo.view().setStyleSheet(Styles.COMBO_BOX_VIEW)
        row2.addWidget(self.auto_export_combo)

        # Seletor de horário (inicialmente oculto)
        self.export_time_label = QLabel("às")
        self.export_time_label.setVisible(False)  # Oculto por padrão
        row2.addWidget(self.export_time_label)

        self.export_time_edit = QTimeEdit()
        self.export_time_edit.setTime(QTime(18, 0))  # Padrão: 18:00
        self.export_time_edit.setDisplayFormat("HH:mm")
        self.export_time_edit.setMaximumWidth(80)
        self.export_time_edit.setToolTip("Horário diário para exportação automática")
        self.export_time_edit.setVisible(False)  # Oculto por padrão
        row2.addWidget(self.export_time_edit)

        row2.addStretch()

        filters_main_layout.addLayout(row2)

        filters_group.setLayout(filters_main_layout)
        layout.addWidget(filters_group)

        # Cards de Métricas 24h (inicialmente ocultos)
        self.metrics_container = QWidget()
        metrics_layout = QHBoxLayout(self.metrics_container)
        metrics_layout.setSpacing(15)
        metrics_layout.setContentsMargins(0, 10, 0, 10)

        self.card_total_24h = self.create_metric_card("Total (24h)", "0", "#3B82F6")
        self.card_media = self.create_metric_card("Média/Hora", "0.0", "#8b5cf6")
        self.card_pico = self.create_metric_card("Pico de Tráfego", "0", "#10b981")

        metrics_layout.addWidget(self.card_total_24h)
        metrics_layout.addWidget(self.card_media)
        metrics_layout.addWidget(self.card_pico)

        layout.addWidget(self.metrics_container)
        # Sempre visível (mostra métricas 24h)

        # Tabela de Resumo Horário (única tabela, sempre visível)
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(['Data', 'Hora', 'Total', 'Carros', 'Motos', 'Caminhões', 'Ônibus'])

        # Configurar tabela de resumo com larguras fixas
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        for i in range(2, 7):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Interactive)

        # Definir larguras para melhor alinhamento
        self.table.setColumnWidth(0, 120)  # Data
        self.table.setColumnWidth(1, 100)  # Hora
        self.table.setColumnWidth(2, 100)  # Total
        self.table.setColumnWidth(3, 100)  # Carros
        self.table.setColumnWidth(4, 100)  # Motos
        self.table.setColumnWidth(5, 120)  # Caminhões
        self.table.setColumnWidth(6, 100)  # Ônibus

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)  # Ocultar números das linhas

        layout.addWidget(self.table)

        # Botões de ação
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 15, 0, 10)  # Mais espaço superior e inferior
        buttons_layout.setSpacing(12)

        self.info_label = QLabel("0 eventos carregados")
        self.info_label.setStyleSheet(f"""
            color: {ThemeColors.TEXT_SECONDARY};
            font-size: 13px;
            font-weight: 600;
            padding: 8px 0;
        """)
        buttons_layout.addWidget(self.info_label)

        buttons_layout.addStretch()

        self.btn_export_csv = QPushButton("Exportar Excel")
        self.btn_export_csv.setMinimumHeight(40)
        self.btn_export_csv.setMinimumWidth(150)
        self.btn_export_csv.setStyleSheet(Styles.ACTION_BUTTON_EMERALD)
        self.btn_export_csv.clicked.connect(self.export_xlsx)
        buttons_layout.addWidget(self.btn_export_csv)

        self.btn_export_custom = QPushButton("Exportar Personalizado")
        self.btn_export_custom.setMinimumHeight(40)
        self.btn_export_custom.setMinimumWidth(150)
        self.btn_export_custom.setStyleSheet(Styles.BUTTON_SECONDARY)
        self.btn_export_custom.clicked.connect(self.open_custom_export_dialog)
        buttons_layout.addWidget(self.btn_export_custom)

        self.btn_refresh = QPushButton("↻ Atualizar")
        self.btn_refresh.setMinimumHeight(40)
        self.btn_refresh.setMinimumWidth(120)
        self.btn_refresh.clicked.connect(self.refresh_current_view)
        buttons_layout.addWidget(self.btn_refresh)

        layout.addLayout(buttons_layout)

    def set_rtsp_url(self, rtsp_url):
        """Define o link RTSP atual e atualiza a tabela"""
        self.current_rtsp_url = rtsp_url
        self.refresh_rtsp_sources()
        self.refresh_current_view()

    def refresh_rtsp_sources(self):
        """Atualiza lista de fontes RTSP no dropdown"""
        try:
            # Salvar seleção atual
            current_selection = self.rtsp_filter_combo.currentData() if hasattr(self, 'rtsp_filter_combo') else ""

            # Limpar e adicionar "Todas"
            self.rtsp_filter_combo.clear()
            self.rtsp_filter_combo.addItem("Todas as Fontes", "")

            # Buscar URLs únicas do banco
            rtsp_urls = self.database.get_unique_rtsp_urls()

            for url in rtsp_urls:
                # Truncar URL para exibição
                display_url = url if len(url) <= 50 else url[:47] + "..."
                self.rtsp_filter_combo.addItem(f"{display_url}", url)

            # Restaurar seleção se possível
            index = self.rtsp_filter_combo.findData(current_selection)
            if index >= 0:
                self.rtsp_filter_combo.setCurrentIndex(index)

            print(f"[DEBUG] Fontes RTSP carregadas: {len(rtsp_urls)} encontradas")
        except Exception as e:
            print(f"[ERRO] Falha ao carregar fontes RTSP: {e}")

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
            minutes = interval // 60000
            print(f"[INFO] Atualização automática ativada: {minutes} minutos")
        else:
            print(f"[INFO] Atualização automática desativada")

    def update_auto_export(self, index):
        """Atualiza intervalo de exportação automática ou horário específico"""
        # Parar timers atuais
        self.export_timer.stop()
        self.export_schedule_timer.stop()

        # Mostrar/ocultar seletor de horário baseado na opção
        is_scheduled = (index == 5)  # Índice 5 = "Horário Específico"
        self.export_time_label.setVisible(is_scheduled)
        self.export_time_edit.setVisible(is_scheduled)

        if is_scheduled:
            # Modo: Horário Específico
            self.export_schedule_timer.start()  # Verifica a cada 1 minuto
            self.last_scheduled_export_date = None  # Reset do controle

            export_time = self.export_time_edit.time().toString("HH:mm")
            print(f"[INFO] Exportação agendada para: {export_time} (diariamente)")
        else:
            # Modo: Intervalo periódico
            intervals = {
                0: 0,           # Desativado
                1: 5 * 60000,   # 5 minutos
                2: 10 * 60000,  # 10 minutos
                3: 30 * 60000,  # 30 minutos
                4: 60 * 60000   # 60 minutos
            }

            interval = intervals.get(index, 0)

            if interval > 0:
                self.export_timer.start(interval)
                minutes = interval // 60000
                print(f"[INFO] Exportação automática ativada: {minutes} minutos")
            else:
                print(f"[INFO] Exportação automática desativada")

    def _write_table_to_csv(self, table, filepath):
        """
        CORRIGIDO: Método privado para escrever tabela em CSV (evita duplicação de código)
        Agora com proteção contra crashes por permissões/antivírus

        Args:
            table: QTableWidget a ser exportada
            filepath: Caminho do arquivo CSV de destino

        Raises:
            Exception: Se falhar após todas as tentativas de retry
        """
        import time

        max_retries = 3
        retry_delay = 0.5  # segundos

        for attempt in range(max_retries):
            try:
                # Tentar escrever o arquivo
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as csvfile:
                    writer = csv.writer(csvfile, delimiter=';')

                    # Escrever cabeçalhos
                    headers = []
                    for col in range(table.columnCount()):
                        header_item = table.horizontalHeaderItem(col)
                        headers.append(header_item.text() if header_item else f"Coluna {col}")
                    writer.writerow(headers)

                    # Escrever dados
                    for row in range(table.rowCount()):
                        row_data = []
                        for col in range(table.columnCount()):
                            item = table.item(row, col)
                            row_data.append(item.text() if item else '')
                        writer.writerow(row_data)

                # Se chegou aqui, sucesso!
                return

            except PermissionError as e:
                if attempt < max_retries - 1:
                    print(f"[AVISO] Arquivo em uso ou sem permissão (tentativa {attempt+1}/{max_retries}): {filepath}")
                    print(f"  Aguardando {retry_delay}s antes de tentar novamente...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Backoff exponencial
                else:
                    # Última tentativa falhou
                    raise Exception(
                        f"Não foi possível salvar o arquivo após {max_retries} tentativas.\n\n"
                        f"Possíveis causas:\n"
                        f"- Arquivo está aberto em outro programa (Excel, etc.)\n"
                        f"- Sem permissão de escrita na pasta\n"
                        f"- Antivírus bloqueando a operação\n\n"
                        f"Feche o arquivo se estiver aberto e tente novamente."
                    ) from e

            except Exception as e:
                # Outro tipo de erro
                import traceback
                print(f"[ERRO] Falha ao exportar CSV:")
                print(f"  Arquivo: {filepath}")
                print(f"  Erro: {type(e).__name__}: {str(e)}")
                print(f"  Detalhes:\n{traceback.format_exc()}")
                raise

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
            self.auto_export_xlsx()
            self.last_scheduled_export_date = current_date  # Marca como exportado hoje
            print(f"[INFO] Próxima exportação: amanhã às {scheduled_time.strftime('%H:%M')}")

    def auto_export_xlsx(self):
        """Exporta Excel automaticamente para a pasta padrão (usada pelo timer)."""
        try:
            export_folder = self.config.get('export_folder', '')
            if not export_folder or not os.path.isdir(export_folder):
                export_folder = str(Path("exports"))
                Path(export_folder).mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(export_folder, f"relatorio_veiculos_{timestamp}.xlsx")

            import pandas as pd

            def _col_sum(col_idx):
                total = 0
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, col_idx)
                    try:
                        total += int(item.text()) if item else 0
                    except ValueError:
                        pass
                return total

            t_total     = _col_sum(2)
            t_carros    = _col_sum(3)
            t_motos     = _col_sum(4)
            t_caminhoes = _col_sum(5)
            t_onibus    = _col_sum(6)

            n_cols = 7
            empty  = [""] * n_cols

            summary = [
                ["RELATÓRIO DE CONTAGEM VEICULAR (AUTO)"] + [""] * (n_cols - 1),
                ["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")] + [""] * (n_cols - 2),
                empty,
                ["RESUMO"] + [""] * (n_cols - 1),
                ["Total Geral", t_total]     + [""] * (n_cols - 2),
                ["Carros",      t_carros]    + [""] * (n_cols - 2),
                ["Motos",       t_motos]     + [""] * (n_cols - 2),
                ["Caminhões",   t_caminhoes] + [""] * (n_cols - 2),
                ["Ônibus",      t_onibus]    + [""] * (n_cols - 2),
                empty,
            ]

            headers   = [["Data", "Hora", "Total", "Carros", "Motos", "Caminhões", "Ônibus"]]
            data_rows = [
                [(self.table.item(row, col).text() if self.table.item(row, col) else '')
                 for col in range(self.table.columnCount())]
                for row in range(self.table.rowCount())
            ]
            total_row = [["TOTAL", "", t_total, t_carros, t_motos, t_caminhoes, t_onibus]]

            df = pd.DataFrame(summary + headers + data_rows + total_row)
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Relatório', index=False, header=False)
                ws = writer.sheets['Relatório']
                for col, width in zip(['A','B','C','D','E','F','G'],
                                      [20, 14, 12, 12, 12, 14, 12]):
                    ws.column_dimensions[col].width = width

            print(f"[AUTO-EXPORT] Exportado: {filename}")

        except Exception as e:
            import traceback
            print(f"[ERRO] Falha na exportação automática: {e}")
            traceback.print_exc()

    def create_metric_card(self, title, value, color):
        """Cria um card de métrica"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 8px;
                padding: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            QLabel {{
                background-color: transparent;
                border: none;
            }}
        """)
        card.setMinimumHeight(80)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        card_layout.setContentsMargins(8, 8, 8, 8)

        title_label = QLabel(title)
        title_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.9);
            font-size: 12px;
            font-weight: 600;
            background-color: transparent;
            border: none;
        """)
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet("""
            color: white;
            font-size: 26px;
            font-weight: 700;
            background-color: transparent;
            border: none;
        """)
        value_label.setObjectName("metric_value")
        card_layout.addWidget(value_label)

        card_layout.addStretch()

        return card

    def refresh_current_view(self):
        """Atualiza o resumo horário"""
        self.refresh_summary()

    def refresh_summary(self):
        """Atualiza visualização de resumo horário"""
        try:
            # Obter filtros - dia inteiro (00:00:00 até 23:59:59)
            start = self.start_date.dateTime().toString("yyyy-MM-dd") + " 00:00:00"
            end = self.end_date.dateTime().toString("yyyy-MM-dd") + " 23:59:59"
            rtsp_filter = self.rtsp_filter_combo.currentData()

            print(f"[DEBUG] Buscando resumo horário:")
            print(f"  RTSP URL: {rtsp_filter if rtsp_filter else '(TODAS AS FONTES)'}")

            # Buscar dados agregados
            summary_data = self.database.get_hourly_summary(
                rtsp_url=rtsp_filter,
                start_date=start,
                end_date=end
            )

            # Buscar métricas 24h
            metrics = self.database.get_24h_metrics(rtsp_url=rtsp_filter)

            # Atualizar cards de métricas
            self.card_total_24h.findChild(QLabel, "metric_value").setText(str(metrics['total_24h']))
            self.card_media.findChild(QLabel, "metric_value").setText(str(metrics['media_hora']))
            self.card_pico.findChild(QLabel, "metric_value").setText(str(metrics['pico_trafego']))

            # Limpar tabela de resumo
            self.table.setRowCount(0)

            # Preencher tabela de resumo
            for item in summary_data:
                row = self.table.rowCount()
                self.table.insertRow(row)

                self.table.setItem(row, 0, QTableWidgetItem(item['data']))
                self.table.setItem(row, 1, QTableWidgetItem(f"{item['hora']:02d}:00"))
                self.table.setItem(row, 2, QTableWidgetItem(str(item['total'])))
                self.table.setItem(row, 3, QTableWidgetItem(str(item['carros'])))
                self.table.setItem(row, 4, QTableWidgetItem(str(item['motos'])))
                self.table.setItem(row, 5, QTableWidgetItem(str(item['caminhoes'])))
                self.table.setItem(row, 6, QTableWidgetItem(str(item['onibus'])))

            # Atualizar status
            fonte_nome = self.rtsp_filter_combo.currentText().replace("", "")
            self.info_label.setText(f" {len(summary_data)} intervalos horários • Fonte: {fonte_nome}")

            print(f"[DEBUG] Resumo carregado: {len(summary_data)} intervalos")

        except Exception as e:
            print(f"[ERRO] Falha ao atualizar resumo: {e}")
            import traceback
            traceback.print_exc()

    def export_xlsx(self):
        """Exporta resumo horário para Excel com totais calculados"""
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "Aviso", "Não há dados para exportar.")
            return

        export_folder = self.config.get('export_folder', '')
        file_prefix = "resumo_horario"
        default_filename = f"{file_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        if export_folder and os.path.isdir(export_folder):
            default_filename = os.path.join(export_folder, default_filename)
            reply = QMessageBox.question(
                self, "Exportar",
                f"Exportar para a pasta padrão?\n\n{export_folder}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.No:
                filename, _ = QFileDialog.getSaveFileName(
                    self, "Exportar Histórico", default_filename, "Excel (*.xlsx)")
                if not filename:
                    return
            else:
                filename = default_filename
        else:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Exportar Histórico", default_filename, "Excel (*.xlsx)")
            if not filename:
                return

        if not filename.endswith('.xlsx'):
            filename += '.xlsx'

        try:
            import pandas as pd

            # Calcular totais das colunas numéricas
            def _col_sum(col_idx):
                total = 0
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, col_idx)
                    try:
                        total += int(item.text()) if item else 0
                    except ValueError:
                        pass
                return total

            t_total     = _col_sum(2)
            t_carros    = _col_sum(3)
            t_motos     = _col_sum(4)
            t_caminhoes = _col_sum(5)
            t_onibus    = _col_sum(6)

            start_str = self.start_date.date().toString("dd/MM/yyyy")
            end_str   = self.end_date.date().toString("dd/MM/yyyy")
            fonte     = self.rtsp_filter_combo.currentText()

            n_cols = 7
            empty  = [""] * n_cols

            summary = [
                ["RELATÓRIO DE CONTAGEM VEICULAR"] + [""] * (n_cols - 1),
                ["Período", f"{start_str} a {end_str}"] + [""] * (n_cols - 2),
                ["Fonte",   fonte]                      + [""] * (n_cols - 2),
                ["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")] + [""] * (n_cols - 2),
                empty,
                ["RESUMO"] + [""] * (n_cols - 1),
                ["Total Geral",  t_total]     + [""] * (n_cols - 2),
                ["Carros",       t_carros]    + [""] * (n_cols - 2),
                ["Motos",        t_motos]     + [""] * (n_cols - 2),
                ["Caminhões",    t_caminhoes] + [""] * (n_cols - 2),
                ["Ônibus",       t_onibus]    + [""] * (n_cols - 2),
                empty,
                ["DETALHAMENTO HORÁRIO"] + [""] * (n_cols - 1),
            ]

            headers = ["Data", "Hora", "Total", "Carros", "Motos", "Caminhões", "Ônibus"]
            data_rows = []
            for row in range(self.table.rowCount()):
                data_rows.append([
                    (self.table.item(row, col).text() if self.table.item(row, col) else '')
                    for col in range(self.table.columnCount())
                ])

            # Linha de total ao final
            total_row = ["TOTAL", "", t_total, t_carros, t_motos, t_caminhoes, t_onibus]

            final = summary + [headers] + data_rows + [total_row]
            df = pd.DataFrame(final)

            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Relatório', index=False, header=False)
                ws = writer.sheets['Relatório']
                for col, width in zip(['A','B','C','D','E','F','G'],
                                      [20, 14, 12, 12, 12, 14, 12]):
                    ws.column_dimensions[col].width = width

            QMessageBox.information(self, "Sucesso",
                                    f"Histórico exportado com sucesso!\n\n{filename}")

        except ImportError:
            QMessageBox.critical(self, "Erro",
                "Instale 'openpyxl':\npip install openpyxl")
        except Exception as e:
            import traceback; traceback.print_exc()
            QMessageBox.critical(self, "Erro ao Exportar",
                                 f"Não foi possível exportar o arquivo:\n\n{str(e)}")

    def open_custom_export_dialog(self):
        """Abre diálogo para exportação personalizada"""
        dialog = CustomExportDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            date, time = dialog.get_data()
            if date and time:
                self.export_custom_report(date, time)

    def export_custom_report(self, date, time):
        """Gera e salva relatório personalizado"""
        try:
            import pandas as pd
            # Formatar datas para query
            date_str = date.toString("yyyy-MM-dd")
            time_str = time.toString("HH:mm:ss")
            
            start_dt = f"{date_str} 00:00:00"
            end_dt = f"{date_str} {time_str}"
            
            print(f"[INFO] Gerando relatório personalizado: {start_dt} até {end_dt}")
            
            # Buscar dados
            # Usamos get_hourly_summary para pegar os dados discriminados por hora
            data = self.database.get_hourly_summary(
                rtsp_url=self.current_rtsp_url, # Respeita filtro atual de câmera se houver
                start_date=start_dt,
                end_date=end_dt,
                limit=1000
            )
            
            if not data:
                QMessageBox.warning(self, "Aviso", "Nenhum dado encontrado para o período selecionado.")
                return

            # Calcular totais
            total_geral = sum(item['total'] for item in data)
            total_carros = sum(item['carros'] for item in data)
            total_motos = sum(item['motos'] for item in data)
            total_caminhoes = sum(item['caminhoes'] for item in data)
            total_onibus = sum(item['onibus'] for item in data)
            
            # Preparar Excel
            default_filename = f"relatorio_personalizado_{date.toString('dd-MM-yyyy')}_ate_{time.toString('HH-mm')}.xlsx"
            
            # Configurar pasta padrão se existir
            export_folder = self.config.get('export_folder', '')
            if export_folder and os.path.exists(export_folder):
                 default_filename = os.path.join(export_folder, default_filename)
            
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Salvar Relatório Personalizado",
                default_filename,
                "Excel Files (*.xlsx)"
            )
            
            if not filename:
                return
                
            if not filename.endswith('.xlsx'):
                filename += '.xlsx'

            # Criar DataFrame único para o relatório
            
            # 1. Metadados (Cabeçalho)
            header_data = [
                ['RELATÓRIO DE CONTAGEM VEICULAR', ''],
                ['Data Relatório', date.toString("dd/MM/yyyy")],
                ['Horário Limite', time.toString("HH:mm")],
                ['Fonte', self.current_rtsp_url if self.current_rtsp_url else "Todas as Fontes"],
                ['Gerado em', datetime.now().strftime("%d/%m/%Y %H:%M:%S")],
                ['', ''] # Linha em branco
            ]
            
            # 2. Resumo Total
            summary_data = [
                ['RESUMO TOTAL', ''],
                ['Métrica', 'Valor'],
                ['Total Veículos', total_geral],
                ['Carros', total_carros],
                ['Motos', total_motos],
                ['Caminhões', total_caminhoes],
                ['Ônibus', total_onibus],
                ['', ''] # Linha em branco
            ]
            
            # 3. Detalhe Horário
            detail_header = [['DETALHAMENTO HORÁRIO', '', '', '', '', '']]
            detail_cols = [['Hora', 'Total', 'Carros', 'Motos', 'Caminhões', 'Ônibus']]
            
            detail_rows = []
            for item in data:
                detail_rows.append([
                    f"{item['hora']:02d}:00",
                    item['total'],
                    item['carros'],
                    item['motos'],
                    item['caminhoes'],
                    item['onibus']
                ])
                
            # Combinar tudo em um único DataFrame (usando listas)
            # Estratégia: Criar um DataFrame genérico e preencher
            final_data = []
            final_data.extend(header_data)
            final_data.extend(summary_data)
            final_data.extend(detail_header)
            final_data.extend(detail_cols)
            final_data.extend(detail_rows)
            
            df_final = pd.DataFrame(final_data)

            # Escrever no Excel em uma única aba
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df_final.to_excel(writer, sheet_name='Relatório', index=False, header=False)
                
                # Ajustar largura das colunas (opcional, requer acesso à planilha)
                worksheet = writer.sheets['Relatório']
                worksheet.column_dimensions['A'].width = 20
                worksheet.column_dimensions['B'].width = 15
                worksheet.column_dimensions['C'].width = 15
                worksheet.column_dimensions['D'].width = 15
                worksheet.column_dimensions['E'].width = 15
                worksheet.column_dimensions['F'].width = 15
                    
            QMessageBox.information(self, "Sucesso", f"Relatório Excel exportado com sucesso!\n{filename}")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Erro", f"Erro ao exportar relatório:\n{e}")
