"""
Módulo core do sistema (configuração, contador, detector)
"""

from .config import Config
from .counter import VehicleCounter
from .detector import VideoThread

__all__ = ['Config', 'VehicleCounter', 'VideoThread']
