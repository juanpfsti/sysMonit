#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerenciador de banco de dados para persistência de contagens
"""

import sqlite3
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path


class CounterDatabase:
    """Gerencia persistência de contadores em banco SQLite"""

    # Mapeamento de IDs para normalização
    CATEGORIA_MAP_ID = {
        'Carros': 1,
        'Motos': 2,
        'Caminhões': 3,
        'Ônibus': 4,
        'Indefinido': 0
    }
    
    SENTIDO_MAP_ID = {
        'ida': 1,
        'volta': 2,
        'indefinido': 0
    }

    # Reverso para leitura
    ID_MAP_CATEGORIA = {v: k for k, v in CATEGORIA_MAP_ID.items()}
    ID_MAP_SENTIDO = {v: k for k, v in SENTIDO_MAP_ID.items()}

    def __init__(self, db_path='contador.db'):
        self.db_path = db_path
        self.conn = None
        self._lock = threading.Lock()  # Lock para thread-safety
        self._busy_timeout = 30.0  # Timeout ao tentar acessar banco ocupado
        self.init_database()

    def init_database(self):
        """Inicializa banco de dados e cria tabelas se necessário"""
        try:
            # CORRIGIDO: Usar WAL mode para melhor concorrência e evitar race conditions
            # check_same_thread=False permite uso em múltiplas threads
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0  # Timeout de 30s para evitar deadlocks
            )
            cursor = self.conn.cursor()

            # Habilitar WAL (Write-Ahead Logging) para melhor concorrência
            # Permite leituras enquanto há escritas em andamento
            cursor.execute("PRAGMA journal_mode=WAL")

            # Otimizações adicionais de performance e segurança
            cursor.execute("PRAGMA synchronous=NORMAL")  # Balance entre segurança e performance
            cursor.execute("PRAGMA cache_size=10000")    # Cache de 10MB para queries rápidas
            cursor.execute("PRAGMA temp_store=MEMORY")   # Tabelas temporárias em memória
            cursor.execute("PRAGMA busy_timeout=30000")  # Timeout de 30s para "database is busy"

            # Tabela para armazenar estado atual dos contadores (mantida para compatibilidade/dashboard)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contadores (
                    id INTEGER PRIMARY KEY,
                    rtsp_url TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    sentido TEXT NOT NULL,
                    valor INTEGER NOT NULL DEFAULT 0,
                    ultima_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # NOVA ESTRUTURA v2
            # 1. Tabela de Câmeras (Normalização de RTSP URL)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cameras (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rtsp_url TEXT UNIQUE NOT NULL,
                    descricao TEXT,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            ''')

            # 2. Tabela Histórico Otimizada (v2)
            # - Usa INTEGER para timestamp (Unix Epoch)
            # - Usa IDs para categoria e sentido
            # - Usa ID da câmera (Foreign Key)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS historico_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    camera_id INTEGER NOT NULL,
                    timestamp INTEGER NOT NULL,
                    categoria_id INTEGER NOT NULL,
                    sentido_id INTEGER NOT NULL,
                    FOREIGN KEY(camera_id) REFERENCES cameras(id)
                )
            ''')

            # Índices para a nova tabela
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hist_v2_time ON historico_v2(timestamp DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hist_v2_cam ON historico_v2(camera_id)')

            # 3. Tabela de histórico de fila (Queue Management)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS queue_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    track_id INTEGER,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT NOT NULL,
                    wait_duration_sec REAL NOT NULL,
                    vehicle_class TEXT DEFAULT '?',
                    rtsp_url TEXT DEFAULT '',
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_entry ON queue_history(entry_time DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_url ON queue_history(rtsp_url)')

            self.conn.commit()
            
            # Migração automática se tabela antiga existir e nova estiver vazia
            self._check_and_migrate()

            logging.info(f"Banco de dados inicializado: {self.db_path}")
        except Exception as e:
            logging.error(f"Erro ao inicializar banco: {e}")

    def _check_and_migrate(self):
        """Verifica se precisa migrar da tabela antiga (historico) para nova (historico_v2)"""
        try:
            cursor = self.conn.cursor()
            
            # Verificar se tabela antiga 'historico' existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
            if not cursor.fetchone():
                return  # Tabela antiga não existe, nada a migrar

            # Verificar se tabela nova está vazia
            cursor.execute("SELECT COUNT(*) FROM historico_v2")
            if cursor.fetchone()[0] > 0:
                return  # Tabela nova já tem dados, assumimos que migração já ocorreu

            logging.info("Iniciando migração de dados para formato otimizado v2...")
            
            # 1. Migrar Câmeras (URLs únicas)
            cursor.execute("SELECT DISTINCT rtsp_url FROM historico WHERE rtsp_url IS NOT NULL AND rtsp_url != ''")
            urls = cursor.fetchall()
            for url_row in urls:
                url = url_row[0]
                cursor.execute("INSERT OR IGNORE INTO cameras (rtsp_url) VALUES (?)", (url,))
            
            # 2. Migrar Dados
            # Ler dados antigos em lotes para não estourar memória
            batch_size = 10000
            offset = 0
            
            while True:
                cursor.execute(f"SELECT rtsp_url, timestamp, categoria, sentido FROM historico ORDER BY id LIMIT {batch_size} OFFSET {offset}")
                rows = cursor.fetchall()
                
                if not rows:
                    break
                
                migrations = []
                for row in rows:
                    rtsp_url, ts_str, cat_str, sent_str = row
                    
                    # Obter ID da câmera
                    cursor.execute("SELECT id FROM cameras WHERE rtsp_url = ?", (rtsp_url,))
                    cam_res = cursor.fetchone()
                    if not cam_res:
                        continue # URL vazia ou inválida
                    cam_id = cam_res[0]
                    
                    # Converter timestamp string para epoch integer
                    try:
                        # Tenta formatos comuns
                        if '.' in str(ts_str):
                             ts = datetime.strptime(str(ts_str), '%Y-%m-%d %H:%M:%S.%f').timestamp()
                        else:
                             ts = datetime.strptime(str(ts_str), '%Y-%m-%d %H:%M:%S').timestamp()
                        ts_int = int(ts)
                    except:
                        ts_int = int(time.time()) # Fallback se falhar
                    
                    # Mapear Categoria e Sentido
                    cat_id = self.CATEGORIA_MAP_ID.get(cat_str, 0)
                    sent_id = self.SENTIDO_MAP_ID.get(sent_str, 0)
                    
                    migrations.append((cam_id, ts_int, cat_id, sent_id))
                
                if migrations:
                    cursor.executemany(
                        "INSERT INTO historico_v2 (camera_id, timestamp, categoria_id, sentido_id) VALUES (?, ?, ?, ?)",
                        migrations
                    )
                    self.conn.commit()
                
                offset += batch_size
                logging.info(f"Migrados {offset} registros...")

            logging.info("Migração concluída com sucesso.")
            
            # Opcional: Renomear tabela antiga para backup ou dropar depois
            # cursor.execute("ALTER TABLE historico RENAME TO historico_backup")
            
            # VACUUM para liberar espaço
            logging.info("Otimizando arquivo do banco (VACUUM)...")
            cursor.execute("VACUUM")
            logging.info("Otimização concluída.")

        except Exception as e:
            logging.error(f"Erro na migração: {e}")
            import traceback
            logging.error(traceback.format_exc())

    def _get_camera_id(self, rtsp_url):
        """Helper para obter ou criar ID da câmera"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM cameras WHERE rtsp_url = ?", (rtsp_url,))
            res = cursor.fetchone()
            if res:
                return res[0]
            
            # Criar se não existe
            cursor.execute("INSERT INTO cameras (rtsp_url) VALUES (?)", (rtsp_url,))
            self.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logging.error(f"Erro ao obter camera_id: {e}")
            return None

    def save_counters(self, contadores, rtsp_url=''):
        """
        Salva estado atual dos contadores no banco
        Mantido compatível com estrutura antiga por enquanto
        """
        with self._lock:  # Thread-safe
            try:
                cursor = self.conn.cursor()

                # Limpar contadores antigos DESTE link RTSP específico
                cursor.execute("DELETE FROM contadores WHERE rtsp_url = ?", (rtsp_url,))

                # Salvar novos valores
                total_saved = 0
                for categoria, valores in contadores.items():
                    if categoria == 'total':
                        continue  # Total é calculado, não precisa salvar

                    for sentido, valor in valores.items():
                        cursor.execute('''
                            INSERT INTO contadores (id, rtsp_url, categoria, sentido, valor)
                            VALUES (NULL, ?, ?, ?, ?)
                        ''', (rtsp_url, categoria, sentido, valor))
                        total_saved += valor

                self.conn.commit()
                logging.debug(f"DB: Salvos {total_saved} veiculos para {rtsp_url[:30]}...")
            except Exception as e:
                logging.error(f"Erro ao salvar contadores: {e}")

    def load_counters(self, rtsp_url=''):
        """Carrega contadores do banco"""
        with self._lock:  # Thread-safe
            try:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT categoria, sentido, valor FROM contadores WHERE rtsp_url = ?",
                    (rtsp_url,)
                )
                rows = cursor.fetchall()

                # Inicializar estrutura padrão
                contadores = {
                    'total': {'ida': 0, 'volta': 0},
                    'Carros': {'ida': 0, 'volta': 0},
                    'Motos': {'ida': 0, 'volta': 0},
                    'Caminhões': {'ida': 0, 'volta': 0},
                    'Ônibus': {'ida': 0, 'volta': 0}
                }

                # Preencher com valores do banco
                for categoria, sentido, valor in rows:
                    if categoria in contadores:
                        contadores[categoria][sentido] = valor

                # Calcular total
                total_ida = sum(contadores[cat]['ida'] for cat in contadores if cat != 'total')
                total_volta = sum(contadores[cat]['volta'] for cat in contadores if cat != 'total')
                contadores['total']['ida'] = total_ida
                contadores['total']['volta'] = total_volta

                return contadores
            except Exception as e:
                logging.error(f"Erro ao carregar contadores: {e}")
                return {
                    'total': {'ida': 0, 'volta': 0},
                    'Carros': {'ida': 0, 'volta': 0},
                    'Motos': {'ida': 0, 'volta': 0},
                    'Caminhões': {'ida': 0, 'volta': 0},
                    'Ônibus': {'ida': 0, 'volta': 0}
                }

    def add_to_history(self, categoria_en, categoria, sentido, rtsp_url=''):
        """Adiciona evento ao histórico otimizado v2"""
        if not rtsp_url:
            return # Não salvar sem URL associada

        with self._lock:  # Thread-safe
            try:
                cam_id = self._get_camera_id(rtsp_url)
                if not cam_id:
                    return

                # Normalizar dados
                cat_id = self.CATEGORIA_MAP_ID.get(categoria, 0)
                sent_id = self.SENTIDO_MAP_ID.get(sentido, 0)
                ts_now = int(time.time())

                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO historico_v2 (camera_id, timestamp, categoria_id, sentido_id)
                    VALUES (?, ?, ?, ?)
                ''', (cam_id, ts_now, cat_id, sent_id))
                
                # logging.debug(f"Historico v2: {categoria} ({sentido}) at {ts_now}")
            except Exception as e:
                logging.error(f"Erro ao adicionar ao historico v2: {e}")

    def flush(self):
        """Força flush do WAL"""
        with self._lock:
            try:
                if self.conn:
                    self.conn.commit()
                    self.conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception as e:
                logging.warning(f"Aviso ao fazer checkpoint: {e}")

    def clear_all(self):
        """Limpa todos os dados"""
        with self._lock:  # Thread-safe
            try:
                cursor = self.conn.cursor()
                cursor.execute("DELETE FROM contadores")
                cursor.execute("DELETE FROM historico_v2")
                # cursor.execute("DELETE FROM cameras") # Opcional: manter câmeras
                self.conn.commit()
                logging.info("Banco de dados limpo")
            except Exception as e:
                logging.error(f"Erro ao limpar banco: {e}")

    def clean_corrupted_data(self):
        """Remove registros corrompidos (Stub para compatibilidade)"""
        return 0

    def get_history_events(self, rtsp_url='', start_date=None, end_date=None, limit=1000):
        """Busca eventos do histórico v2"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                query = """
                    SELECT h.id, c.rtsp_url, h.timestamp, h.categoria_id, h.sentido_id
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE 1=1
                """
                params = []

                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)

                if start_date:
                    ts_start = int(datetime.strptime(start_date, '%Y-%m-%d %H:%M:%S').timestamp())
                    query += " AND h.timestamp >= ?"
                    params.append(ts_start)

                if end_date:
                    ts_end = int(datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S').timestamp())
                    query += " AND h.timestamp <= ?"
                    params.append(ts_end)

                query += " ORDER BY h.timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                # Converter para formato esperado pela UI
                events = []
                for row in rows:
                    ts_local = datetime.fromtimestamp(row[2]).strftime('%Y-%m-%d %H:%M:%S')
                    cat_name = self.ID_MAP_CATEGORIA.get(row[3], 'Desconhecido')
                    sent_name = self.ID_MAP_SENTIDO.get(row[4], 'Desconhecido')
                    
                    events.append({
                        'id': row[0],
                        'rtsp_url': row[1],
                        'timestamp': ts_local,
                        'categoria_en': '', # Deprecated
                        'categoria': cat_name,
                        'sentido': sent_name
                    })

                return events
            except Exception as e:
                logging.error(f"Erro ao buscar histórico v2: {e}")
                import traceback
                logging.error(traceback.format_exc())
                return []

    def get_hourly_traffic(self, rtsp_url='', date=None):
        """Retorna contagem de veículos por hora"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                if date is None:
                    date = datetime.now().strftime('%Y-%m-%d')
                
                # Robust date parsing: extract date part if full datetime provided
                date_str = str(date).split(' ')[0]

                # Converter data start/end para epoch
                try:
                    dt_start = datetime.strptime(f"{date_str} 00:00:00", '%Y-%m-%d %H:%M:%S')
                except ValueError:
                     # Fallback to simple parsing if format is weird
                     dt_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

                ts_start = int(dt_start.timestamp())
                ts_end = ts_start + 86400

                query = """
                    SELECT
                        strftime('%H', datetime(h.timestamp, 'unixepoch', 'localtime')) as hora,
                        COUNT(*) as total
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE h.timestamp >= ? AND h.timestamp < ?
                """
                params = [ts_start, ts_end]

                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)

                query += " GROUP BY hora ORDER BY hora"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [{'hora': int(row[0]), 'total': row[1]} for row in rows]
            except Exception as e:
                logging.error(f"Erro ao buscar tráfego por hora v2: {e}")
                return []

    def get_vehicle_distribution(self, rtsp_url='', start_date=None, end_date=None):
        """Retorna distribuição de veículos por categoria"""
        with self._lock:
            try:
                cursor = self.conn.cursor()

                query = """
                    SELECT
                        h.categoria_id,
                        COUNT(*) as total
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE 1=1
                """
                params = []

                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)

                if start_date:
                    # Robust parsing for start_date
                    s_date_str = str(start_date).split(' ')[0]
                    try:
                        ts_start = int(datetime.strptime(f"{s_date_str} 00:00:00", '%Y-%m-%d %H:%M:%S').timestamp())
                        query += " AND h.timestamp >= ?"
                        params.append(ts_start)
                    except ValueError:
                        logging.warning(f"Data inválida ignorada (start): {start_date}")

                if end_date:
                    # Robust parsing for end_date (end of the day)
                    e_date_str = str(end_date).split(' ')[0]
                    try:
                        ts_end = int(datetime.strptime(f"{e_date_str} 23:59:59", '%Y-%m-%d %H:%M:%S').timestamp())
                        query += " AND h.timestamp <= ?"
                        params.append(ts_end)
                    except ValueError:
                        logging.warning(f"Data inválida ignorada (end): {end_date}")

                query += " GROUP BY h.categoria_id ORDER BY total DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [{'categoria': self.ID_MAP_CATEGORIA.get(row[0], 'Outros'), 'total': row[1]} for row in rows]
            except Exception as e:
                logging.error(f"Erro ao buscar distribuição v2: {e}")
                import traceback
                logging.error(traceback.format_exc())
                return []

    def get_weekly_comparison(self, rtsp_url='', weeks=4):
        """Retorna comparativo semanal"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                # Timestamp limite
                ts_limit = int(time.time()) - (weeks * 7 * 86400)

                query = """
                    SELECT
                        strftime('%Y-W%W', datetime(h.timestamp, 'unixepoch', 'localtime')) as semana,
                        h.categoria_id,
                        COUNT(*) as total
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE h.timestamp >= ?
                """
                params = [ts_limit]

                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)

                query += " GROUP BY semana, h.categoria_id ORDER BY semana DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [{'semana': row[0], 'categoria': self.ID_MAP_CATEGORIA.get(row[1], 'Outros'), 'total': row[2]} for row in rows]
            except Exception as e:
                logging.error(f"Erro ao buscar comparativo semanal v2: {e}")
                return []

    def get_daily_comparison(self, rtsp_url='', days=7):
        """Retorna comparativo diário"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                ts_limit = int(time.time()) - (days * 86400)

                query = """
                    SELECT
                        CAST(strftime('%w', datetime(h.timestamp, 'unixepoch', 'localtime')) AS INTEGER) as dia_ordem,
                        h.categoria_id,
                        COUNT(*) as total
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE h.timestamp >= ?
                """
                params = [ts_limit]

                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)

                query += " GROUP BY dia_ordem, h.categoria_id ORDER BY dia_ordem"

                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                dia_map = {0: 'Dom', 1: 'Seg', 2: 'Ter', 3: 'Qua', 4: 'Qui', 5: 'Sex', 6: 'Sab'}

                return [{'dia_semana': dia_map.get(row[0]), 'dia_ordem': row[0], 'categoria': self.ID_MAP_CATEGORIA.get(row[1], 'Outros'), 'total': row[2]} for row in rows]
            except Exception as e:
                logging.error(f"Erro ao buscar comparativo diario v2: {e}")
                return []

    def get_peak_hours(self, rtsp_url='', days=7):
        """Retorna horários de pico"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                ts_limit = int(time.time()) - (days * 86400)

                query = """
                    SELECT
                        strftime('%H', datetime(h.timestamp, 'unixepoch', 'localtime')) as hora,
                        CAST(COUNT(*) AS FLOAT) / ? as media
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE h.timestamp >= ?
                """
                params = [days, ts_limit]

                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)

                query += " GROUP BY hora ORDER BY media DESC"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [{'hora': int(row[0]), 'media': round(row[1], 1)} for row in rows]
            except Exception as e:
                logging.error(f"Erro ao buscar horários de pico v2: {e}")
                return []
    
    def get_unique_rtsp_urls(self):
        """Retorna lista de URLs RTSP"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT rtsp_url FROM cameras ORDER BY rtsp_url")
                return [row[0] for row in cursor.fetchall()]
            except Exception as e:
                logging.error(f"Erro ao buscar URLs v2: {e}")
                return []

    def get_hourly_summary(self, rtsp_url='', start_date=None, end_date=None, limit=500):
        """Resumo horário agregado"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                
                query = """
                     SELECT
                        strftime('%Y-%m-%d', datetime(h.timestamp, 'unixepoch', 'localtime')) as data,
                        strftime('%H', datetime(h.timestamp, 'unixepoch', 'localtime')) as hora,
                        COUNT(*) as total,
                        SUM(CASE WHEN h.categoria_id = 1 THEN 1 ELSE 0 END) as carros,
                        SUM(CASE WHEN h.categoria_id = 2 THEN 1 ELSE 0 END) as motos,
                        SUM(CASE WHEN h.categoria_id = 3 THEN 1 ELSE 0 END) as caminhoes,
                        SUM(CASE WHEN h.categoria_id = 4 THEN 1 ELSE 0 END) as onibus
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE 1=1
                """
                params = []
                
                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)
                
                # ... (lógica similar de data/hora)
                
                query += " GROUP BY data, hora ORDER BY data DESC, hora DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [{
                    'data': row[0],
                    'hora': int(row[1]),
                    'total': row[2],
                    'carros': row[3],
                    'motos': row[4],
                    'caminhoes': row[5],
                    'onibus': row[6]
                } for row in rows]

            except Exception as e:
                logging.error(f"Erro resumo horario v2: {e}")
                return []

    def get_24h_metrics(self, rtsp_url=''):
        """Métricas 24h"""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                ts_limit = int(time.time()) - 86400
                
                query = """
                    SELECT
                        COUNT(*) as total,
                        strftime('%Y-%m-%d %H', datetime(h.timestamp, 'unixepoch', 'localtime')) as hora_grupo
                    FROM historico_v2 h
                    JOIN cameras c ON h.camera_id = c.id
                    WHERE h.timestamp >= ?
                """
                params = [ts_limit]
                
                if rtsp_url:
                    query += " AND c.rtsp_url = ?"
                    params.append(rtsp_url)
                    
                query += " GROUP BY hora_grupo"
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                if not rows:
                     return {'total_24h': 0, 'media_hora': 0.0, 'pico_trafego': 0}

                total_24h = sum(row[0] for row in rows)
                pico_trafego = max(row[0] for row in rows)
                media_hora = total_24h / 24.0
                
                return {
                    'total_24h': total_24h,
                    'media_hora': round(media_hora, 1),
                    'pico_trafego': pico_trafego
                }

            except Exception as e:
                logging.error(f"Erro metricas 24h v2: {e}")
                return {'total_24h': 0, 'media_hora': 0.0, 'pico_trafego': 0}

    # ------------------------------------------------------------------
    # Queue History Methods
    # ------------------------------------------------------------------

    def save_queue_event(self, track_id, entry_time, exit_time, wait_duration_sec, vehicle_class='?', rtsp_url=''):
        """Persiste um evento de fila finalizado no banco de dados."""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute('''
                    INSERT INTO queue_history (track_id, entry_time, exit_time, wait_duration_sec, vehicle_class, rtsp_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (track_id, entry_time, exit_time, wait_duration_sec, vehicle_class, rtsp_url))
                self.conn.commit()
            except Exception as e:
                logging.error(f"Erro ao salvar evento de fila: {e}")

    def get_queue_history(self, rtsp_url=None, start_date=None, end_date=None,
                          start_hour=None, end_hour=None, vehicle_class=None, limit=1000):
        """Busca histórico de fila com filtros opcionais."""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                query = "SELECT id, track_id, entry_time, exit_time, wait_duration_sec, vehicle_class, rtsp_url FROM queue_history WHERE 1=1"
                params = []

                if rtsp_url:
                    query += " AND rtsp_url = ?"
                    params.append(rtsp_url)
                if start_date:
                    query += " AND entry_time >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND entry_time <= ?"
                    params.append(end_date)
                if start_hour is not None:
                    query += " AND CAST(strftime('%H', entry_time) AS INTEGER) >= ?"
                    params.append(int(start_hour))
                if end_hour is not None:
                    query += " AND CAST(strftime('%H', entry_time) AS INTEGER) <= ?"
                    params.append(int(end_hour))
                if vehicle_class and vehicle_class not in ('Todas', ''):
                    query += " AND vehicle_class = ?"
                    params.append(vehicle_class)

                query += " ORDER BY entry_time DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [
                    {
                        'id': r[0],
                        'track_id': r[1],
                        'entry_time': r[2],
                        'exit_time': r[3],
                        'wait_duration_sec': r[4],
                        'vehicle_class': r[5],
                        'rtsp_url': r[6],
                    }
                    for r in rows
                ]
            except Exception as e:
                logging.error(f"Erro ao buscar histórico de fila: {e}")
                return []

    def get_queue_metrics(self, rtsp_url=None, start_date=None, end_date=None,
                          start_hour=None, end_hour=None, vehicle_class=None):
        """Retorna métricas agregadas do histórico de fila."""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                query = """
                    SELECT
                        COUNT(*) as total,
                        AVG(wait_duration_sec) as avg_wait,
                        MAX(wait_duration_sec) as max_wait,
                        MIN(wait_duration_sec) as min_wait
                    FROM queue_history WHERE 1=1
                """
                params = []

                if rtsp_url:
                    query += " AND rtsp_url = ?"
                    params.append(rtsp_url)
                if start_date:
                    query += " AND entry_time >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND entry_time <= ?"
                    params.append(end_date)
                if start_hour is not None:
                    query += " AND CAST(strftime('%H', entry_time) AS INTEGER) >= ?"
                    params.append(int(start_hour))
                if end_hour is not None:
                    query += " AND CAST(strftime('%H', entry_time) AS INTEGER) <= ?"
                    params.append(int(end_hour))
                if vehicle_class and vehicle_class not in ('Todas', ''):
                    query += " AND vehicle_class = ?"
                    params.append(vehicle_class)

                cursor.execute(query, params)
                row = cursor.fetchone()
                if row and row[0]:
                    return {
                        'total': row[0],
                        'avg_wait': round(row[1], 1) if row[1] else 0.0,
                        'max_wait': round(row[2], 1) if row[2] else 0.0,
                        'min_wait': round(row[3], 1) if row[3] else 0.0,
                    }
                return {'total': 0, 'avg_wait': 0.0, 'max_wait': 0.0, 'min_wait': 0.0}
            except Exception as e:
                logging.error(f"Erro ao buscar métricas de fila: {e}")
                return {'total': 0, 'avg_wait': 0.0, 'max_wait': 0.0, 'min_wait': 0.0}

    def get_queue_unique_urls(self):
        """Retorna URLs únicas com registros na queue_history."""
        with self._lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT DISTINCT rtsp_url FROM queue_history WHERE rtsp_url != '' ORDER BY rtsp_url")
                return [row[0] for row in cursor.fetchall()]
            except Exception as e:
                logging.error(f"Erro ao buscar URLs de fila: {e}")
                return []

    def close(self):
        """Fecha conexão com banco"""
        with self._lock:  # Thread-safe
            if self.conn:
                self.conn.close()
                logging.info("Conexão com banco fechada")
