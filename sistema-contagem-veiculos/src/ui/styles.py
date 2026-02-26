# -*- coding: utf-8 -*-
"""
Sistema de estilos centralizado para a aplicação (Dark Theme Moderno)
"""
from .styles_helper import get_input_styles_with_icons, get_checkbox_styles_with_icons

class ThemeColors:
    # Paleta Azul Original (Simples)
    BACKGROUND = "#0a1628"      # Azul escuro profundo
    SURFACE = "#1e3a5f"         # Azul médio
    SURFACE_LIGHT = "#2d4a6f"   # Azul mais claro
    BORDER = "#2d4a6f"          # Azul claro
    PANEL_BG = "#0f1d2e"        # Azul escuro médio (painéis)

    # Textos
    TEXT_PRIMARY = "#FFFFFF"    # Branco
    TEXT_SECONDARY = "#94A3B8"  # Cinza azulado
    TEXT_TERTIARY = "#64748B"   # Cinza
    TEXT_ALT = "#E2E8F0"        # Branco suave

    # Cores de Ação/Destaque
    PRIMARY = "#3B82F6"         # Azul vibrante
    PRIMARY_HOVER = "#2563EB"   # Azul hover
    PRIMARY_PRESSED = "#1D4ED8" # Azul pressionado

    SECONDARY = "#8b5cf6"       # Violet 500
    SECONDARY_HOVER = "#7c3aed" # Violet 600
    
    ACCENT = "#06b6d4"          # Cyan 500

    SUCCESS = "#10B981"         # Verde
    WARNING = "#f59e0b"         # Laranja
    DANGER = "#EF4444"          # Vermelho

    # Gráficos
    CHART_BG = "#1A233A"
    CHART_GRID = "#334155"

class Styles:
    """Definições de QSS (Qt Style Sheets)"""
    
    MAIN_WINDOW = f"""
        QMainWindow {{
            background-color: {ThemeColors.BACKGROUND};
        }}
        QWidget {{
            color: {ThemeColors.TEXT_PRIMARY};
            font-family: 'Segoe UI', 'Roboto', 'Arial', sans-serif;
        }}
    """
    
    PANEL = f"""
        #leftPanel {{
            background-color: {ThemeColors.PANEL_BG};
            border-right: 2px solid {ThemeColors.SURFACE};
        }}
        #rightPanel {{
            background-color: {ThemeColors.BACKGROUND};
            margin-left: 10px;
        }}
        QGroupBox {{
            color: {ThemeColors.TEXT_ALT};
            font-weight: bold;
            font-size: 13px;
            border: 2px solid {ThemeColors.SURFACE};
            border-radius: 8px;
            margin-top: 12px;
            padding: 18px 12px 12px 12px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: 8px;
            padding: 0 8px;
            background-color: {ThemeColors.PANEL_BG};
        }}
        QLabel {{
            color: {ThemeColors.TEXT_SECONDARY};
            font-size: 13px;
        }}
    """
    
    BUTTON_PRIMARY = f"""
        QPushButton {{
            background-color: {ThemeColors.PRIMARY};
            color: #FFFFFF;
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            font-size: 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {ThemeColors.PRIMARY_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {ThemeColors.PRIMARY_PRESSED};
        }}
        QPushButton:disabled {{
            background-color: {ThemeColors.SURFACE_LIGHT};
            color: {ThemeColors.TEXT_TERTIARY};
        }}
    """
    
    BUTTON_SECONDARY = f"""
        QPushButton {{
            background-color: {ThemeColors.SURFACE_LIGHT};
            color: {ThemeColors.TEXT_PRIMARY};
            border: 1px solid {ThemeColors.BORDER};
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {ThemeColors.BORDER};
            border-color: {ThemeColors.TEXT_TERTIARY};
        }}
        QPushButton:pressed {{
            background-color: {ThemeColors.SURFACE};
        }}
        QPushButton:disabled {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_TERTIARY};
        }}
    """
    
    INPUT = f"""
        QLineEdit, QSpinBox, QTimeEdit {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            border: 1px solid {ThemeColors.SURFACE_LIGHT};
            border-radius: 6px;
            padding: 10px 12px;
            font-size: 13px;
        }}
        QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus {{
            border: 2px solid {ThemeColors.PRIMARY};
        }}
        QSpinBox::up-button, QTimeEdit::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 20px;
            border-top-right-radius: 6px;
            background-color: {ThemeColors.SURFACE_LIGHT};
            margin: 0px;
        }}
        QSpinBox::down-button, QTimeEdit::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 20px;
            border-bottom-right-radius: 6px;
            background-color: {ThemeColors.SURFACE_LIGHT};
            margin: 0px;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover, QTimeEdit::up-button:hover, QTimeEdit::down-button:hover {{
            background-color: {ThemeColors.PRIMARY};
        }}
        QSpinBox::up-arrow, QTimeEdit::up-arrow {{
            image: url(icons/arrow_up.png);
            width: 8px;
            height: 8px;
        }}
        QSpinBox::down-arrow, QTimeEdit::down-arrow {{
            image: url(icons/arrow_down.png);
            width: 8px;
            height: 8px;
        }}

        QComboBox {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            border: 1px solid {ThemeColors.SURFACE_LIGHT};
            border-radius: 6px;
            padding: 10px;
            font-size: 13px;
        }}
        QComboBox:focus {{
            border: 2px solid {ThemeColors.PRIMARY};
        }}
        QComboBox:hover {{
            background-color: #244463;
        }}
        QComboBox::drop-down {{
            border: none;
            width: 30px;
            background-color: transparent;
        }}
        QComboBox::down-arrow {{
            image: url(icons/arrow_down.png);
            width: 12px;
            height: 12px;
            margin-right: 10px;
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            selection-background-color: {ThemeColors.PRIMARY};
            selection-color: #FFFFFF;
            border: 2px solid {ThemeColors.SURFACE_LIGHT};
            border-radius: 6px;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            padding: 8px 12px;
            border: none;
            min-height: 25px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {ThemeColors.SURFACE_LIGHT};
            color: #FFFFFF;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {ThemeColors.PRIMARY};
            color: #FFFFFF;
        }}

        QDateTimeEdit {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            border: 1px solid {ThemeColors.SURFACE_LIGHT};
            border-radius: 6px;
            padding: 8px;
            font-size: 13px;
        }}
        QDateTimeEdit:focus {{
            border: 2px solid {ThemeColors.PRIMARY};
        }}
        QDateTimeEdit::drop-down {{
            border: none;
            width: 25px;
        }}
        QDateTimeEdit::down-arrow {{
            image: url(icons/arrow_down.png);
            width: 12px;
            height: 12px;
            margin-right: 5px;
            border: none;
        }}

        /* Override QTimeEdit specific arrows to be smaller (8px) vs QDateTimeEdit (12px) */
        QTimeEdit::up-arrow {{
            image: url(icons/arrow_up.png);
            width: 8px;
            height: 8px;
            margin-left: 6px;
            margin-right: 6px;
        }}
        QTimeEdit::down-arrow {{
            image: url(icons/arrow_down.png);
            width: 8px;
            height: 8px;
            margin-left: 6px;
            margin-right: 6px;
        }}

        /* Calendário popup - harmonizado com tema dark */
        QCalendarWidget {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
        }}
        QCalendarWidget QToolButton {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            border: none;
            border-radius: 4px;
            padding: 5px;
            font-weight: 600;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {ThemeColors.PRIMARY};
            color: white;
        }}
        QCalendarWidget QMenu {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            border: 1px solid {ThemeColors.SURFACE_LIGHT};
            border-radius: 4px;
            padding: 4px;
        }}
        /* Ocultar setas do dropdown de mês/ano */
        QCalendarWidget QSpinBox::up-button {{
            width: 0px;
            height: 0px;
        }}
        QCalendarWidget QSpinBox::down-button {{
            width: 0px;
            height: 0px;
        }}
        QCalendarWidget QSpinBox::up-arrow {{
            image: none;
            width: 0px;
            height: 0px;
        }}
        QCalendarWidget QSpinBox::down-arrow {{
            image: none;
            width: 0px;
            height: 0px;
        }}
        QCalendarWidget QToolButton::menu-indicator {{
            image: none;
            width: 0px;
            height: 0px;
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {ThemeColors.SURFACE};
        }}
        QCalendarWidget QAbstractItemView {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            selection-background-color: {ThemeColors.PRIMARY};
            selection-color: white;
            border: none;
            outline: none;
        }}
        /* Cabeçalho dos dias da semana - CORRIGIDO */
        QCalendarWidget QWidget {{
            alternate-background-color: {ThemeColors.SURFACE};
            background-color: {ThemeColors.SURFACE};
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            color: {ThemeColors.TEXT_ALT};
            background-color: {ThemeColors.SURFACE};
            selection-background-color: {ThemeColors.PRIMARY};
            selection-color: white;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {ThemeColors.TEXT_TERTIARY};
        }}
    """
    
    TABLE = f"""
        QTableWidget {{
            background-color: #1A233A;
            alternate-background-color: #0f1729;
            color: {ThemeColors.TEXT_ALT};
            gridline-color: #2d3748;
            border: 1px solid #2d3748;
            border-radius: 8px;
            font-size: 13px;
        }}
        QTableWidget::item {{
            padding: 12px 8px;
            border-bottom: 1px solid #2d3748;
        }}
        QTableWidget::item:hover {{
            background-color: #2d3748;
        }}
        QTableWidget::item:selected {{
            background-color: {ThemeColors.PRIMARY};
            color: white;
        }}
        QHeaderView::section {{
            background-color: #0f1729;
            color: {ThemeColors.TEXT_ALT};
            padding: 12px 10px;
            border: none;
            border-bottom: 2px solid {ThemeColors.PRIMARY};
            font-weight: 600;
            font-size: 13px;
            text-align: center;
        }}
    """
    
    SCROLLBAR = f"""
        QScrollArea {{
            border: none;
            background-color: {ThemeColors.PANEL_BG};
        }}
        QScrollBar:vertical {{
            background: {ThemeColors.PANEL_BG};
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background: {ThemeColors.SURFACE};
            border-radius: 6px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {ThemeColors.SURFACE_LIGHT};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """
    
    TAB_WIDGET = f"""
        QTabWidget::pane {{
            border: 2px solid {ThemeColors.SURFACE};
            background: {ThemeColors.BACKGROUND};
            border-radius: 0 0 12px 12px;
        }}
        QTabBar::tab {{
            background: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_SECONDARY};
            padding: 9px 28px 9px 28px;
            min-height: 25px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            margin-right: 4px;
            margin-left: 2px;
            font-weight: 600;
            font-size: 13px;
            min-width: 140px;
            max-width: 220px;
        }}
        QTabBar::tab:selected {{
            background: {ThemeColors.PRIMARY};
            color: white;
        }}
        QTabBar::tab:hover:!selected {{
            background: {ThemeColors.SURFACE_LIGHT};
        }}
    """

    HEADER_TITLE = f"""
        font-size: 24px;
        font-weight: 700;
        color: #60a5fa;
        padding: 12px;
        font-family: 'Segoe UI', 'Roboto', sans-serif;
    """

    COMBO_BOX_VIEW = f"""
        QListView {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            border: none;
            outline: none;
        }}
        QListView::item {{
            background-color: {ThemeColors.SURFACE};
            color: {ThemeColors.TEXT_ALT};
            padding: 8px 12px;
            border: none;
        }}
        QListView::item:hover {{
            background-color: {ThemeColors.SURFACE_LIGHT};
            color: #FFFFFF;
        }}
        QListView::item:selected {{
            background-color: {ThemeColors.PRIMARY};
            color: #FFFFFF;
        }}
    """

    ICON_BUTTON = f"""
        QPushButton {{
            background-color: transparent;
            border: none;
            border-radius: 4px;
            padding: 4px;
        }}
        QPushButton:hover {{
            background-color: {ThemeColors.SURFACE_LIGHT};
        }}
        QPushButton:pressed {{
            background-color: {ThemeColors.BORDER};
        }}
    """

    ACTION_BUTTON_EMERALD = f"""
        QPushButton {{
            background-color: {ThemeColors.SUCCESS};
            color: white;
            border-radius: 8px;
            padding: 10px 20px;
            font-weight: 600;
            font-size: 14px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: #059669;
        }}
        QPushButton:pressed {{
            background-color: #047857;
        }}
    """

    ACTION_BUTTON_VIOLET = f"""
        QPushButton {{
            background-color: {ThemeColors.SECONDARY};
            color: white;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 13px;
            border: none;
        }}
        QPushButton:hover {{
            background-color: {ThemeColors.SECONDARY_HOVER};
        }}
        QPushButton:pressed {{
            background-color: #6d28d9;
        }}
    """

    ROI_PREVIEW = f"""
        background: {ThemeColors.BACKGROUND};
        border: 1px solid {ThemeColors.SURFACE};
        border-radius: 4px;
    """

    SLIDER = f"""
        QSlider::groove:horizontal {{
            background: {ThemeColors.SURFACE};
            height: 8px;
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: {ThemeColors.PRIMARY};
            width: 20px;
            height: 20px;
            margin: -6px 0;
            border-radius: 10px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {ThemeColors.PRIMARY_HOVER};
        }}
    """

    CHECKBOX = f"""
        QCheckBox {{
            color: {ThemeColors.TEXT_ALT};
            font-size: 13px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 22px;
            height: 22px;
            border-radius: 5px;
            border: 2px solid {ThemeColors.SURFACE_LIGHT};
            background: {ThemeColors.SURFACE};
        }}
        QCheckBox::indicator:hover {{
            border-color: {ThemeColors.PRIMARY};
            background: #1e4a7f;
        }}
        QCheckBox::indicator:pressed {{
            background: {ThemeColors.PRIMARY_HOVER};
            border-color: {ThemeColors.PRIMARY_HOVER};
        }}
        QCheckBox::indicator:checked {{
            background: {ThemeColors.PRIMARY};
            border-color: {ThemeColors.PRIMARY};
            border-width: 2px;
            image: url(icons/check_white.png);
        }}
        QCheckBox::indicator:checked:hover {{
            background: rgba(59, 130, 246, 0.1);
            border-color: {ThemeColors.PRIMARY_HOVER};
        }}
        QCheckBox::indicator:checked:pressed {{
            background: rgba(59, 130, 246, 0.2);
            border-color: {ThemeColors.PRIMARY_PRESSED};
        }}
    """

    TEXT_EDIT = f"""
        QTextEdit {{
            background-color: {ThemeColors.BACKGROUND};
            color: {ThemeColors.TEXT_TERTIARY};
            border: 1px solid {ThemeColors.SURFACE};
            border-radius: 8px;
            padding: 10px;
            font-size: 11px;
            font-family: 'Consolas', 'Courier New', monospace;
        }}
    """

    FRAME = f"""
        QFrame {{
            background-color: transparent;
            border: none;
        }}
    """

    @staticmethod
    def get_card_style(color_hex):
        """Gera estilo de card simples (sem gradiente)"""
        return f"""
            QFrame {{
                background-color: {color_hex};
                border-radius: 12px;
                border: 2px solid transparent;
                padding: 12px;
            }}
            QLabel {{
                background-color: transparent;
                border: none;
            }}
        """

# Sobrescrever estilos com caminhos absolutos de ícones
Styles.INPUT = get_input_styles_with_icons(ThemeColors)
Styles.CHECKBOX = get_checkbox_styles_with_icons(ThemeColors)

