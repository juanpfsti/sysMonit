#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Componente de Menu de Navegação (Hub) e Header Padronizado
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QGridLayout, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QCursor, QColor

from ..styles import Styles, ThemeColors
import os

class HubHeader(QWidget):
    """
    Header padronizado para as sub-views com botão de voltar.
    """
    back_clicked = pyqtSignal()
    
    def __init__(self, title, subtitle="", parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 4, 15, 4)
        layout.setSpacing(15)
        
        # Botão Voltar
        self.btn_back = QPushButton("← Voltar")
        self.btn_back.setCursor(QCursor(Qt.PointingHandCursor))
        self.btn_back.setFixedSize(90, 36)
        self.btn_back.clicked.connect(self.back_clicked.emit)
        self.btn_back.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.SURFACE_LIGHT};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER};
                border-radius: 6px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.PRIMARY};
                color: white;
                border: 1px solid {ThemeColors.PRIMARY};
            }}
        """)
        layout.addWidget(self.btn_back)
        
        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFixedHeight(24)
        sep.setStyleSheet(f"background-color: {ThemeColors.BORDER}; width: 1px;")
        layout.addWidget(sep)
        
        # Títulos
        titles_layout = QVBoxLayout()
        titles_layout.setSpacing(2)
        titles_layout.setAlignment(Qt.AlignVCenter)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY};")
        titles_layout.addWidget(lbl_title)
        
        if subtitle:
            lbl_sub = QLabel(subtitle)
            lbl_sub.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")
            titles_layout.addWidget(lbl_sub)
            
        layout.addLayout(titles_layout)
        layout.addStretch()


class MenuCard(QFrame):
    """
    Card clicável para o menu de navegação.
    """
    clicked = pyqtSignal()
    
    def __init__(self, title, description, icon_name, color_accent, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.color_accent = color_accent
        
        # Estilo base
        self.base_style = f"""
            QFrame {{
                background-color: {ThemeColors.SURFACE};
                border: 1px solid {ThemeColors.SURFACE_LIGHT};
                border-radius: 12px;
            }}
            QFrame:hover {{
                background-color: {ThemeColors.SURFACE_LIGHT};
                border: 1px solid {color_accent};
            }}
        """
        self.setStyleSheet(self.base_style)
        
        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 25, 20, 25)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)
        
        # Icone
        icon_lbl = QLabel()
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'icons')
        icon_path = os.path.join(icons_dir, f'{icon_name}.ico')
        if not os.path.exists(icon_path):
            icon_path = os.path.join(icons_dir, f'{icon_name}.png')
        if os.path.exists(icon_path):
            icon_lbl.setPixmap(QIcon(icon_path).pixmap(48, 48))
        else:
            # Fallback text
            icon_lbl.setText(icon_name)
            
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(icon_lbl)
        
        # Titulo
        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {ThemeColors.TEXT_PRIMARY}; border: none; background: transparent;")
        layout.addWidget(lbl_title)
        
        # Descrição
        lbl_desc = QLabel(description)
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"font-size: 13px; color: {ThemeColors.TEXT_SECONDARY}; border: none; background: transparent;")
        layout.addWidget(lbl_desc)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            
class NavigationMenu(QWidget):
    """
    Pagina de Menu (Hub) contendo grade de cards.
    """
    def __init__(self, items, parent=None):
        """
        items: Lista de tuplas (titulo, descricao, icon_name, color_accent, callback)
        """
        super().__init__(parent)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Título da página (opcional, pode ser removido se o header da aba já for suficiente)
        # layout.addWidget(QLabel("Menu"))
        
        # Grid de cards centralizado
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(25)
        
        # Centralizar o grid verticalmente
        layout.addStretch()
        layout.addWidget(grid_container)
        layout.addStretch()
        
        # Adicionar cards
        col = 0
        row = 0
        max_cols = 3
        
        for title, desc, icon, color, callback in items:
            card = MenuCard(title, desc, icon, color)
            # Usar lambda com default argument para capturar o callback correto
            card.clicked.connect(lambda c=callback: c())
            
            grid.addWidget(card, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
