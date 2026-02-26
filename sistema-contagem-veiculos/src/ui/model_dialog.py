#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diálogo de seleção de modelo YOLO personalizado.
Extraído de main_window.py para permitir import em queue_tab.py sem circular import.
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QRadioButton, QButtonGroup, QMessageBox, QFileDialog
)
from .styles import ThemeColors


class PersonalizedModelDialog(QDialog):
    """Diálogo para seleção de modelo personalizado"""

    def __init__(self, parent=None, current_model=None):
        super().__init__(parent)
        self.setWindowTitle("Selecionar Modelo Personalizado")
        self.setModal(True)
        self.setMinimumWidth(450)
        self.selected_model = None

        # Aplicar estilo dark mode ao diálogo
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {ThemeColors.BACKGROUND};
                color: {ThemeColors.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 13px;
            }}
            QRadioButton {{
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 13px;
                padding: 6px;
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 20px;
                height: 20px;
            }}
            QRadioButton::indicator:unchecked {{
                background-color: {ThemeColors.SURFACE};
                border: 2px solid {ThemeColors.SURFACE_LIGHT};
                border-radius: 10px;
            }}
            QRadioButton::indicator:unchecked:hover {{
                background-color: {ThemeColors.SURFACE_LIGHT};
                border: 2px solid {ThemeColors.PRIMARY};
            }}
            QRadioButton::indicator:checked {{
                background-color: {ThemeColors.PRIMARY};
                border: 2px solid {ThemeColors.PRIMARY};
                image: url(icons/check_white.ico);
                background-repeat: no-repeat;
                background-position: center;
            }}
            QLineEdit {{
                background-color: {ThemeColors.SURFACE};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 2px solid {ThemeColors.SURFACE_LIGHT};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 2px solid {ThemeColors.PRIMARY};
            }}
            QPushButton {{
                background-color: {ThemeColors.PRIMARY};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.PRIMARY_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ThemeColors.PRIMARY_PRESSED};
            }}
            QLineEdit {{
                     background-color: {ThemeColors.SURFACE};
        }}
        """)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Título
        title = QLabel("Escolha um modelo YOLO ou carregue um customizado:")
        title.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # Opções de modelo pré-treinado
        self.model_group = QButtonGroup()

        modelos_label = QLabel("Modelos Pré-treinados:")
        modelos_label.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-weight: bold; margin-top: 10px;")
        layout.addWidget(modelos_label)

        for idx, model_name in enumerate(['yolo11n.pt', 'yolo11s.pt']):
            radio = QRadioButton(f"{model_name} - {self._get_model_desc(model_name)}")
            self.model_group.addButton(radio, idx)
            layout.addWidget(radio)

        # Separador
        layout.addSpacing(10)

        # Opção para modelo customizado
        custom_radio = QRadioButton("Carregar modelo customizado (.pt)")
        custom_radio.toggled.connect(self._on_custom_toggled)
        self.model_group.addButton(custom_radio, 2)
        layout.addWidget(custom_radio)

        # Campo para arquivo customizado
        self.custom_file_layout = QHBoxLayout()

        arquivo_label = QLabel("Arquivo:")
        arquivo_label.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY};")
        self.custom_file_layout.addWidget(arquivo_label)

        self.custom_file_input = QLineEdit()
        self.custom_file_input.setPlaceholderText("Selecione um arquivo .pt")
        self.custom_file_input.setReadOnly(True)
        self.custom_file_layout.addWidget(self.custom_file_input)

        browse_btn = QPushButton("Procurar...")
        browse_btn.clicked.connect(self._browse_custom_model)
        browse_btn.setMaximumWidth(100)
        self.custom_file_layout.addWidget(browse_btn)

        self.custom_file_layout.setEnabled(False)

        layout.addLayout(self.custom_file_layout)

        # Set modelo atual como selecionado
        if current_model:
            if 'yolo11n' in current_model:
                self.model_group.button(0).setChecked(True)
            elif 'yolo11s' in current_model:
                self.model_group.button(1).setChecked(True)
            else:
                custom_radio.setChecked(True)
                self.custom_file_input.setText(current_model)
        else:
            self.model_group.button(0).setChecked(True)  # Default yolo11n

        # Botões
        layout.addSpacing(10)
        button_layout = QHBoxLayout()

        ok_btn = QPushButton("Confirmar")
        ok_btn.clicked.connect(self._accept_selection)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _get_model_desc(self, model_name):
        """Retorna descrição do modelo"""
        descs = {
            'yolo11n.pt': 'Nano (Mais Rápido, ~80 FPS CPU)',
            'yolo11s.pt': 'Small (Balanceado, ~45 FPS CPU)',
        }
        return descs.get(model_name, '')

    def _on_custom_toggled(self, checked):
        """Ativa/desativa os controles de arquivo customizado"""
        self.custom_file_layout.setEnabled(checked)

    def _browse_custom_model(self):
        """Abre diálogo para selecionar arquivo .pt"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione um modelo YOLO (.pt)",
            "",
            "YOLO Models (*.pt);;Todos (*.)"
        )
        if file_path:
            self.custom_file_input.setText(file_path)

    def _accept_selection(self):
        """Valida e aceita a seleção"""
        selected_id = self.model_group.checkedId()

        if selected_id == 0:
            self.selected_model = 'yolo11n.pt'
        elif selected_id == 1:
            self.selected_model = 'yolo11s.pt'
        elif selected_id == 2:
            # Modelo customizado
            custom_path = self.custom_file_input.text().strip()
            if not custom_path:
                QMessageBox.warning(self, "Erro", "Por favor, selecione um arquivo de modelo customizado.")
                return
            if not os.path.exists(custom_path):
                QMessageBox.warning(self, "Erro", f"Arquivo não encontrado: {custom_path}")
                return
            self.selected_model = custom_path

        self.accept()

    def get_selected_model(self):
        """Retorna o modelo selecionado"""
        return self.selected_model
