#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contador de veículos

CONVENÇÃO DE NOMENCLATURA:
- Variáveis públicas/métodos: Português (interface do usuário)
- Variáveis internas YOLO: Inglês (categoria_en: 'car', 'truck', etc.)
- Bancos de dados: Português (compatibilidade com versões antigas)

Exemplo: categoria_en='car' → categoria='Carros'
"""

from datetime import datetime
import time
import logging
from typing import Optional, Dict


class VehicleCounter:
    """
    Gerencia contagem de veículos por categoria e sentido

    Attributes:
        categoria_map: Mapeamento de classes YOLO (inglês) para nomes em português
        contadores: Estrutura de contadores por categoria e sentido
        historico: Lista de eventos de contagem
    """

    def __init__(self, database=None, rtsp_url: str = ''):
        self.database = database
        self.rtsp_url = rtsp_url  # Link RTSP associado a este contador
        self.categoria_map = {
            'car': 'Carros',
            'moto': 'Motos',  # Dataset customizado do usuário usa 'moto'
            'motorcycle': 'Motos',
            'motor': 'Motos',  # Dataset Roboflow usa 'motor'
            'truck': 'Caminhões',
            'bus': 'Ônibus'
        }

        # Se tem banco de dados E link RTSP, carregar contadores salvos deste link
        if self.database and self.rtsp_url:
            self.contadores = self.database.load_counters(rtsp_url=self.rtsp_url)
        else:
            self.reset()

        self.historico = []
        self._last_save_time = time.time()
        self._save_interval = 5.0  # Salvar a cada 5 segundos

    def reset(self) -> None:
        """
        Reseta APENAS os contadores em memória (não afeta banco de dados).
        Use reset_all() para limpar banco de dados também.
        """
        self.contadores = {
            'total': {'ida': 0, 'volta': 0},
            'Carros': {'ida': 0, 'volta': 0},
            'Motos': {'ida': 0, 'volta': 0},
            'Caminhões': {'ida': 0, 'volta': 0},
            'Ônibus': {'ida': 0, 'volta': 0}
        }
        self.historico = []
        # NÃO limpa banco de dados - apenas memória

    def reset_all(self) -> None:
        """
        Reseta TUDO: contadores em memória E banco de dados.
        Use com cuidado - apaga todos os dados históricos!
        """
        # Resetar memória
        self.reset()

        # Limpar banco de dados também
        if self.database:
            self.database.clear_all()

    def adicionar(self, categoria_en: str, sentido: str) -> None:
        """
        Adiciona uma contagem para uma categoria e sentido

        Args:
            categoria_en: Categoria em inglês (YOLO): 'car', 'truck', 'bus', 'motorcycle'
            sentido: Direção do movimento: 'ida' ou 'volta'

        Raises:
            ValueError: Se categoria_en ou sentido forem inválidos
        """
        # CORRIGIDO: Validar entrada para evitar dados corrompidos
        if not categoria_en:
            logging.error("adicionar() chamado com categoria vazia")
            return  # Silenciosamente ignora (não crashar o sistema)

        if sentido not in ['ida', 'volta']:
            logging.error(f"adicionar() chamado com sentido inválido: '{sentido}', ignorando")
            return  # Silenciosamente ignora

        # Mapear categoria com validação
        categoria = self.categoria_map.get(categoria_en)
        if categoria is None:
            logging.warning(f"Categoria desconhecida: '{categoria_en}', usando 'Carros' como fallback")
            categoria = 'Carros'

        # Verificar se categoria existe nos contadores (safety check)
        if categoria not in self.contadores:
            logging.error(f"Categoria '{categoria}' não existe na estrutura de contadores, ignorando")
            return

        # Incrementar contadores com tratamento de erro
        try:
            self.contadores['total'][sentido] += 1
            self.contadores[categoria][sentido] += 1
        except KeyError as e:
            logging.error(f"Erro ao incrementar contador: {e}, estrutura pode estar corrompida")
            return
        self.historico.append({
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'categoria_en': categoria_en,
            'categoria': categoria,
            'sentido': sentido
        })

        # Salvar no banco de dados periodicamente (a cada 5 segundos)
        if self.database:
            current_time = time.time()
            if current_time - self._last_save_time >= self._save_interval:
                self.save_to_database()
                self._last_save_time = current_time
            
            # OTIMIZAÇÃO: Adicionar ao histórico sem commit individual
            self.database.add_to_history(categoria_en, categoria, sentido, rtsp_url=self.rtsp_url)

    def save_to_database(self) -> None:
        """Força salvamento no banco de dados (OTIMIZAÇÃO: com flush)"""
        if self.database:
            try:
                self.database.save_counters(self.contadores, rtsp_url=self.rtsp_url)
                self.database.flush()  # Sincronizar com disco
            except Exception as e:
                import traceback
                logging.error(f"Erro ao salvar/flush no DB: {e}")
                logging.error(traceback.format_exc())

    def get_total(self) -> int:
        """
        Retorna total geral de veículos contados

        Returns:
            Soma de todos os veículos (ida + volta)
        """
        return self.contadores['total']['ida'] + self.contadores['total']['volta']
