#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Banco de dados dedicado ao sistema de fila de veículos (queue.db).

Design intencional:
  - Arquivo separado do banco de contadores → sem contenção de lock.
  - isolation_level=None (autocommit) → cada execute() é sua própria
    transação; leituras sempre enxergam os últimos dados commitados.
  - threading.Lock → seguro para uso por múltiplas threads.
  - Escrita síncrona: o arquivo é separado, não há contention; commits
    são instantâneos (<1 ms) e não travam o loop de vídeo.
"""

import sqlite3
import threading
import logging


class QueueDatabase:
    """Banco SQLite dedicado ao histórico de fila."""

    DB_PATH = 'queue.db'

    def __init__(self, db_path=None):
        self.db_path = db_path or self.DB_PATH
        self._lock = threading.Lock()
        self._conn = None
        self._init()

    # ------------------------------------------------------------------
    # Inicialização
    # ------------------------------------------------------------------

    def _init(self):
        try:
            # isolation_level=None → autocommit; sem transações implícitas abertas.
            # Isso garante que leituras posteriores sempre enxergam dados recém-gravados.
            self._conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0,
                isolation_level=None,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=2000")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._create_tables()
            logging.info(f"QueueDatabase iniciado: {self.db_path}")
        except Exception as e:
            logging.error(f"QueueDatabase: erro ao inicializar: {e}")

    def _create_tables(self):
        self._conn.execute('''
            CREATE TABLE IF NOT EXISTS queue_history (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                track_id          INTEGER,
                entry_time        TEXT    NOT NULL,
                exit_time         TEXT    NOT NULL,
                wait_duration_sec REAL    NOT NULL,
                vehicle_class     TEXT    DEFAULT "?",
                rtsp_url          TEXT    DEFAULT "",
                created_at        TEXT    DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_qh_entry ON queue_history(entry_time DESC)'
        )
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_qh_url ON queue_history(rtsp_url)'
        )

    # ------------------------------------------------------------------
    # Escrita (chamada a partir do thread de vídeo)
    # ------------------------------------------------------------------

    def save_event(self, track_id, entry_time, exit_time,
                   wait_duration_sec, vehicle_class='?', rtsp_url=''):
        """
        Persiste um evento de fila finalizado.
        Com isolation_level=None o commit é imediato e não bloqueia.
        """
        with self._lock:
            try:
                self._conn.execute(
                    '''INSERT INTO queue_history
                       (track_id, entry_time, exit_time,
                        wait_duration_sec, vehicle_class, rtsp_url)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (track_id, entry_time, exit_time,
                     wait_duration_sec, vehicle_class, rtsp_url),
                )
                print(f"[QueueDB] Evento salvo: {entry_time} | {vehicle_class} | {wait_duration_sec:.1f}s")
            except Exception as e:
                logging.error(f"QueueDatabase.save_event: {e}")

    # ------------------------------------------------------------------
    # Leituras (chamadas a partir da UI)
    # ------------------------------------------------------------------

    def _build_where(self, rtsp_url, start_date, end_date,
                     start_hour, end_hour, vehicle_class):
        clauses, params = [], []
        if rtsp_url:
            clauses.append("rtsp_url = ?")
            params.append(rtsp_url)
        if start_date:
            clauses.append("entry_time >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("entry_time <= ?")
            params.append(end_date)
        if start_hour is not None:
            clauses.append("CAST(strftime('%H', entry_time) AS INTEGER) >= ?")
            params.append(int(start_hour))
        if end_hour is not None:
            clauses.append("CAST(strftime('%H', entry_time) AS INTEGER) <= ?")
            params.append(int(end_hour))
        if vehicle_class and vehicle_class not in ('Todos', 'Todas', ''):
            clauses.append("vehicle_class = ?")
            params.append(vehicle_class)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def get_history(self, rtsp_url=None, start_date=None, end_date=None,
                    start_hour=None, end_hour=None, vehicle_class=None, limit=2000):
        with self._lock:
            try:
                where, params = self._build_where(
                    rtsp_url, start_date, end_date, start_hour, end_hour, vehicle_class
                )
                sql = (
                    f"SELECT id, track_id, entry_time, exit_time, "
                    f"wait_duration_sec, vehicle_class, rtsp_url "
                    f"FROM queue_history {where} "
                    f"ORDER BY entry_time DESC LIMIT ?"
                )
                params.append(limit)
                rows = self._conn.execute(sql, params).fetchall()
                return [
                    {
                        'id':                r[0],
                        'track_id':          r[1],
                        'entry_time':        r[2],
                        'exit_time':         r[3],
                        'wait_duration_sec': r[4],
                        'vehicle_class':     r[5],
                        'rtsp_url':          r[6],
                    }
                    for r in rows
                ]
            except Exception as e:
                logging.error(f"QueueDatabase.get_history: {e}")
                return []

    def get_metrics(self, rtsp_url=None, start_date=None, end_date=None,
                    start_hour=None, end_hour=None, vehicle_class=None):
        with self._lock:
            try:
                where, params = self._build_where(
                    rtsp_url, start_date, end_date, start_hour, end_hour, vehicle_class
                )
                sql = (
                    f"SELECT COUNT(*), AVG(wait_duration_sec), "
                    f"MAX(wait_duration_sec), MIN(wait_duration_sec) "
                    f"FROM queue_history {where}"
                )
                row = self._conn.execute(sql, params).fetchone()
                if row and row[0]:
                    return {
                        'total':    row[0],
                        'avg_wait': round(row[1], 1) if row[1] else 0.0,
                        'max_wait': round(row[2], 1) if row[2] else 0.0,
                        'min_wait': round(row[3], 1) if row[3] else 0.0,
                    }
                return {'total': 0, 'avg_wait': 0.0, 'max_wait': 0.0, 'min_wait': 0.0}
            except Exception as e:
                logging.error(f"QueueDatabase.get_metrics: {e}")
                return {'total': 0, 'avg_wait': 0.0, 'max_wait': 0.0, 'min_wait': 0.0}

    def get_unique_urls(self):
        with self._lock:
            try:
                rows = self._conn.execute(
                    "SELECT DISTINCT rtsp_url FROM queue_history "
                    "WHERE rtsp_url != '' ORDER BY rtsp_url"
                ).fetchall()
                return [r[0] for r in rows]
            except Exception as e:
                logging.error(f"QueueDatabase.get_unique_urls: {e}")
                return []

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def close(self):
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
