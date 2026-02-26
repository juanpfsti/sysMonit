from PyQt5.QtWidgets import QWidget, QVBoxLayout
from .components.navigation_hub import HubHeader

def wrap_with_header(widget, title, subtitle, back_callback):
    """
    Envolve um widget existente com um HubHeader.
    """
    container = QWidget()
    container.setMinimumWidth(0)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0,0,0,0)
    layout.setSpacing(0)
    
    header = HubHeader(title, subtitle)
    header.back_clicked.connect(back_callback)
    
    layout.addWidget(header)
    layout.addWidget(widget)
    
    return container
