# -*- coding: utf-8 -*-
"""
Helper para gerar estilos com caminhos absolutos de ícones
"""
import sys
import os

def get_icon_path(icon_name):
    """
    Retorna o caminho absoluto para um ícone no formato URL.
    Funciona tanto em desenvolvimento quanto quando empacotado.
    """
    try:
        # PyInstaller usa _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Em desenvolvimento, usa o diretório do projeto
        base_path = os.path.abspath(".")

    # Caminho completo do ícone
    icon_path = os.path.join(base_path, 'icons', icon_name)
    # Converte backslashes para forward slashes (necessário para QSS no Windows)
    icon_path = icon_path.replace('\\', '/')
    return icon_path

def get_input_styles_with_icons(theme_colors):
    """
    Retorna os estilos INPUT com caminhos absolutos para ícones.
    """
    arrow_up = get_icon_path('arrow_up.ico')
    arrow_down = get_icon_path('arrow_down.ico')

    return f"""
        QLineEdit, QSpinBox, QTimeEdit {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            border: 1px solid {theme_colors.SURFACE_LIGHT};
            border-radius: 6px;
            padding: 10px 12px;
            font-size: 13px;
        }}
        QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus {{
            border: 2px solid {theme_colors.PRIMARY};
        }}
        QSpinBox::up-button, QTimeEdit::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 20px;
            border-top-right-radius: 6px;
            background-color: {theme_colors.SURFACE_LIGHT};
            margin: 0px;
        }}
        QSpinBox::down-button, QTimeEdit::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 20px;
            border-bottom-right-radius: 6px;
            background-color: {theme_colors.SURFACE_LIGHT};
            margin: 0px;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover, QTimeEdit::up-button:hover, QTimeEdit::down-button:hover {{
            background-color: {theme_colors.PRIMARY};
        }}
        QSpinBox::up-arrow, QTimeEdit::up-arrow {{
            image: url({arrow_up});
            width: 8px;
            height: 8px;
        }}
        QSpinBox::down-arrow, QTimeEdit::down-arrow {{
            image: url({arrow_down});
            width: 8px;
            height: 8px;
        }}

        QComboBox {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            border: 1px solid {theme_colors.SURFACE_LIGHT};
            border-radius: 6px;
            padding: 10px;
            font-size: 13px;
        }}
        QComboBox:focus {{
            border: 2px solid {theme_colors.PRIMARY};
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
            image: url({arrow_down});
            width: 12px;
            height: 12px;
            margin-right: 10px;
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            selection-background-color: {theme_colors.PRIMARY};
            selection-color: #FFFFFF;
            border: 2px solid {theme_colors.SURFACE_LIGHT};
            border-radius: 6px;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            padding: 8px 12px;
            border: none;
            min-height: 25px;
        }}
        QComboBox QAbstractItemView::item:hover {{
            background-color: {theme_colors.SURFACE_LIGHT};
            color: #FFFFFF;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {theme_colors.PRIMARY};
            color: #FFFFFF;
        }}

        QDateTimeEdit {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            border: 1px solid {theme_colors.SURFACE_LIGHT};
            border-radius: 6px;
            padding: 8px;
            font-size: 13px;
        }}
        QDateTimeEdit:focus {{
            border: 2px solid {theme_colors.PRIMARY};
        }}
        QDateTimeEdit::drop-down {{
            border: none;
            width: 25px;
        }}
        QDateTimeEdit::down-arrow {{
            image: url({arrow_down});
            width: 12px;
            height: 12px;
            margin-right: 5px;
            border: none;
        }}

        /* Override QTimeEdit specific arrows to be smaller (8px) vs QDateTimeEdit (12px) */
        QTimeEdit::up-arrow {{
            image: url({arrow_up});
            width: 8px;
            height: 8px;
            margin-left: 6px;
            margin-right: 6px;
        }}
        QTimeEdit::down-arrow {{
            image: url({arrow_down});
            width: 8px;
            height: 8px;
            margin-left: 6px;
            margin-right: 6px;
        }}

        /* Calendário popup - harmonizado com tema dark */
        QCalendarWidget {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
        }}
        QCalendarWidget QToolButton {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            border: none;
            border-radius: 4px;
            padding: 5px;
            font-weight: 600;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {theme_colors.PRIMARY};
            color: white;
        }}
        QCalendarWidget QMenu {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            border: 1px solid {theme_colors.SURFACE_LIGHT};
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
            background-color: {theme_colors.SURFACE};
        }}
        QCalendarWidget QAbstractItemView {{
            background-color: {theme_colors.SURFACE};
            color: {theme_colors.TEXT_ALT};
            selection-background-color: {theme_colors.PRIMARY};
            selection-color: white;
            border: none;
            outline: none;
        }}
        /* Cabeçalho dos dias da semana - CORRIGIDO */
        QCalendarWidget QWidget {{
            alternate-background-color: {theme_colors.SURFACE};
            background-color: {theme_colors.SURFACE};
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            color: {theme_colors.TEXT_ALT};
            background-color: {theme_colors.SURFACE};
            selection-background-color: {theme_colors.PRIMARY};
            selection-color: white;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {theme_colors.TEXT_TERTIARY};
        }}
    """

def get_checkbox_styles_with_icons(theme_colors):
    """
    Retorna os estilos CHECKBOX com caminhos absolutos para ícones.
    """
    check_white = get_icon_path('check_white.ico')

    return f"""
        QCheckBox {{
            color: {theme_colors.TEXT_ALT};
            font-size: 13px;
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 22px;
            height: 22px;
            border-radius: 5px;
            border: 2px solid {theme_colors.SURFACE_LIGHT};
            background: {theme_colors.SURFACE};
        }}
        QCheckBox::indicator:hover {{
            border-color: {theme_colors.PRIMARY};
            background: #1e4a7f;
        }}
        QCheckBox::indicator:pressed {{
            background: {theme_colors.PRIMARY_HOVER};
            border-color: {theme_colors.PRIMARY_HOVER};
        }}
        QCheckBox::indicator:checked {{
            background: {theme_colors.PRIMARY};
            border-color: {theme_colors.PRIMARY};
            border-width: 2px;
            image: url({check_white});
        }}
        QCheckBox::indicator:checked:hover {{
            background: rgba(59, 130, 246, 0.1);
            border-color: {theme_colors.PRIMARY_HOVER};
        }}
        QCheckBox::indicator:checked:pressed {{
            background: rgba(59, 130, 246, 0.2);
            border-color: {theme_colors.PRIMARY_PRESSED};
        }}
    """
