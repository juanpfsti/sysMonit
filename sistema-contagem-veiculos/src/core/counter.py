#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contador de veículos

CONVENÇÃO DE NOMENCLATURA:
- Variáveis públicas/métodos: Português (interface do usuário)
- Variáveis internas YOLO: Inglês (categoria_en: 'car', 'truck', etc.)
- Bancos de dados: Português (compatibilidade com versões antigas)

Exemplo: categoria_en='car' → categoria='Carros'

RESET DIÁRIO AUTOMÁTICO:
    O contador zera automaticamente à meia-noite via _check_reset_diario().
    A verificação é feita a cada chamada de adicionar(), garantindo que o
    reset ocorra sem precisar de um processo externo ou agendador.
    O histórico no banco de dados é preservado — apenas os contadores
    em memória e a tabela 'contadores' são zerados.
"""

from datetime import datetime, date
import time
import logging
from typing import Optional


class VehicleCounter:
    """
    Gerencia contagem de veículos por categoria e sentido.
    Inclui reset automático diário à meia-noite.

    Attributes:
        categoria_map:  Mapeamento YOLO (inglês) → nome em português
        contadores:     Estrutura de contadores por categoria e sentido
        historico:      Lista de eventos de contagem (sessão atual)
        _reset_date:    Data do último reset — controla o reset diário
    """

    def __init__(self, database=None, rtsp_url: str = ''):
        self.database    = database
        self.rtsp_url    = rtsp_url
        self.categoria_map = {
            'car':        'Carros',
            'moto':       'Motos',   # Dataset customizado
            'motorcycle': 'Motos',
            'motor':      'Motos',   # Dataset Roboflow
            'truck':      'Caminhões',
            'bus':        'Ônibus',
        }

        # Controle de reset diário
        self._reset_date: Optional[date] = None

        # Se tem banco de dados + URL, carregar contadores salvos
        if self.database and self.rtsp_url:
            self.contadores = self.database.load_counters(rtsp_url=self.rtsp_url)
            # Marcar a data de carregamento como "data do reset vigente"
            # para não zerar imediatamente contadores do dia atual
            self._reset_date = date.today()
        else:
            self._reset_contadores_memoria()

        self.historico       = []
        self._last_save_time = time.time()
        self._save_interval  = 5.0   # Salvar no banco a cada 5 segundos

    # ──────────────────────────────────────────────────────────────────────────
    # RESET DIÁRIO AUTOMÁTICO
    # ──────────────────────────────────────────────────────────────────────────

    def _check_reset_diario(self) -> None:
        """
        Verifica se é um novo dia e, se for, executa o reset automático.

        Chamado internamente a cada adicionar() — zero overhead se já resetou hoje.
        Registra um evento no log e, opcionalmente, salva snapshot no banco antes
        de zerar, para não perder contagens do dia anterior caso o sistema caia
        próximo à meia-noite.
        """
        hoje = date.today()
        if self._reset_date == hoje:
            return  # Já está no dia correto, nada a fazer

        if self._reset_date is not None:
            # Há um dia anterior — salvar snapshot antes de zerar
            logging.info(
                f"[Reset Diário] Novo dia detectado: {hoje}. "
                f"Zerando contadores (dados preservados no histórico)."
            )
            if self.database:
                try:
                    # Forçar salvamento final do dia anterior
                    self.database.save_counters(self.contadores, rtsp_url=self.rtsp_url)
                    self.database.flush()
                    logging.info(f"[Reset Diário] Snapshot final do dia {self._reset_date} salvo.")
                except Exception as e:
                    logging.error(f"[Reset Diário] Erro ao salvar snapshot: {e}")

        # Zerar memória e banco
        self._reset_contadores_memoria()
        if self.database:
            try:
                self.database.save_counters(self.contadores, rtsp_url=self.rtsp_url)
                self.database.flush()
            except Exception as e:
                logging.error(f"[Reset Diário] Erro ao zerar banco: {e}")

        self._reset_date = hoje
        self._last_save_time = time.time()

    def _reset_contadores_memoria(self) -> None:
        """Zera apenas a estrutura em memória — não afeta banco."""
        self.contadores = {
            'total':      {'ida': 0, 'volta': 0},
            'Carros':     {'ida': 0, 'volta': 0},
            'Motos':      {'ida': 0, 'volta': 0},
            'Caminhões':  {'ida': 0, 'volta': 0},
            'Ônibus':     {'ida': 0, 'volta': 0},
        }
        self.historico = []

    # ──────────────────────────────────────────────────────────────────────────
    # INTERFACE PÚBLICA
    # ──────────────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """
        Reseta APENAS os contadores em memória (não afeta banco de dados).
        Use reset_all() para limpar banco de dados também.
        """
        self._reset_contadores_memoria()

    def reset_all(self) -> None:
        """
        Reseta TUDO: contadores em memória E banco de dados.
        Use com cuidado — apaga todos os dados históricos!
        """
        self._reset_contadores_memoria()
        if self.database:
            self.database.clear_all()

    def adicionar(self, categoria_en: str, sentido: str) -> None:
        """
        Adiciona uma contagem para uma categoria e sentido.
        Verifica automaticamente se é necessário executar o reset diário.

        Args:
            categoria_en: Categoria em inglês (YOLO): 'car', 'truck', 'bus', 'motorcycle'
            sentido:      Direção do movimento: 'ida' ou 'volta'
        """
        # ── Reset diário automático (custo ~zero se mesmo dia) ──
        self._check_reset_diario()

        # ── Validações ──
        if not categoria_en:
            logging.error("adicionar() chamado com categoria vazia")
            return

        if sentido not in ('ida', 'volta'):
            logging.error(f"adicionar() sentido inválido: '{sentido}', ignorando")
            return

        categoria = self.categoria_map.get(categoria_en)
        if categoria is None:
            logging.warning(f"Categoria desconhecida: '{categoria_en}', usando 'Carros' como fallback")
            categoria = 'Carros'

        if categoria not in self.contadores:
            logging.error(f"Categoria '{categoria}' não existe na estrutura de contadores")
            return

        # ── Incrementar ──
        try:
            self.contadores['total'][sentido]    += 1
            self.contadores[categoria][sentido]  += 1
        except KeyError as e:
            logging.error(f"Erro ao incrementar contador: {e}")
            return

        self.historico.append({
            'timestamp':   datetime.now().isoformat(timespec='seconds'),
            'categoria_en': categoria_en,
            'categoria':   categoria,
            'sentido':     sentido,
        })

        # ── Persistência ──
        if self.database:
            current_time = time.time()
            if current_time - self._last_save_time >= self._save_interval:
                self.save_to_database()
                self._last_save_time = current_time

            # Histórico detalhado (sem commit individual — batched pelo database)
            self.database.add_to_history(categoria_en, categoria, sentido, rtsp_url=self.rtsp_url)

    def save_to_database(self) -> None:
        """Força salvamento periódico dos contadores no banco de dados."""
        if self.database:
            try:
                self.database.save_counters(self.contadores, rtsp_url=self.rtsp_url)
                self.database.flush()
            except Exception as e:
                import traceback
                logging.error(f"Erro ao salvar/flush no DB: {e}")
                logging.error(traceback.format_exc())

    def get_total(self) -> int:
        """Retorna total geral de veículos contados (ida + volta)."""
        return self.contadores['total']['ida'] + self.contadores['total']['volta']

    def get_data_reset(self) -> Optional[date]:
        """Retorna a data do último reset diário (ou None se nunca resetou)."""
        return self._reset_date

    def get_status(self) -> dict:
        """
        Retorna um snapshot do estado atual do contador.
        Útil para diagnóstico e monitoramento.
        """
        return {
            'total':      self.get_total(),
            'contadores': self.contadores,
            'reset_date': str(self._reset_date),
            'rtsp_url':   self.rtsp_url,
        }