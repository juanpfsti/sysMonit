#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API de Monitoramento de Veículos
---------------------------------
Expõe os dados do sistema de contagem via HTTP e WebSocket.

Endpoints disponíveis:
    GET  /api/contadores                  → contadores atuais por câmera (só hoje)
    GET  /api/historico                   → últimos N eventos
    GET  /api/historico/filtrado          → histórico com filtros de datetime, câmera, categoria, sentido
    GET  /api/historico/agregado          → totais agregados por hora/dia (para gráficos)
    GET  /api/cameras                     → lista de câmeras cadastradas
    WS   /ws                              → websocket para atualizações em tempo real
"""

import sqlite3
import asyncio
import json
import time
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH        = "contador.db"
DASHBOARD_PATH = "dashboard.html"
HOST           = "0.0.0.0"
PORT           = 8000
PUSH_INTERVAL  = 2.0   # segundos entre pushes via WebSocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# APP FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="API Monitoramento de Veículos",
    description="Exposição dos dados de contagem em tempo real",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Nova conexão. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[WS] Conexão encerrada. Total: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        if not self.active_connections:
            return
        message = json.dumps(data, ensure_ascii=False)
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# ─────────────────────────────────────────────────────────────────────────────
# BANCO DE DADOS — helpers
# ─────────────────────────────────────────────────────────────────────────────

ID_MAP_CATEGORIA = {0: "Indefinido", 1: "Carros", 2: "Motos", 3: "Caminhões", 4: "Ônibus"}
ID_MAP_SENTIDO   = {0: "indefinido", 1: "ida",    2: "volta"}

# Mapa inverso para filtros
CAT_MAP_NOME = {v: k for k, v in ID_MAP_CATEGORIA.items()}
SENT_MAP_NOME = {v: k for k, v in ID_MAP_SENTIDO.items()}


def get_db():
    """Conexão somente-leitura ao banco de dados."""
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(f"Banco de dados não encontrado: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=ON")
    return conn


def get_db_write():
    """Conexão com escrita — usada apenas para reset diário."""
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(f"Banco de dados não encontrado: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ts_to_str(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def str_to_ts(dt_str: str) -> Optional[float]:
    """Converte string 'YYYY-MM-DDTHH:MM' ou 'YYYY-MM-DD HH:MM' para unix timestamp."""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str, fmt).timestamp()
        except ValueError:
            continue
    return None

# ─────────────────────────────────────────────────────────────────────────────
# RESET DIÁRIO — zera tabela 'contadores' à meia-noite
# ─────────────────────────────────────────────────────────────────────────────

_last_reset_date: Optional[date] = None


def executar_reset_diario():
    """Zera os contadores em memória (tabela contadores) sem apagar o histórico."""
    global _last_reset_date
    hoje = date.today()
    if _last_reset_date == hoje:
        return  # Já resetou hoje
    try:
        conn = get_db_write()
        conn.execute("UPDATE contadores SET valor = 0")
        conn.commit()
        conn.close()
        _last_reset_date = hoje
        logger.info(f"[Reset] Contadores zerados para novo dia: {hoje}")
    except Exception as e:
        logger.error(f"[Reset] Erro ao zerar contadores: {e}")


async def reset_diario_loop():
    global _last_reset_date

    while True:
        agora = datetime.now()
        hoje = agora.date()

        # Executa apenas entre 00:00 e 00:01
        if agora.hour == 0 and agora.minute == 0:
            if _last_reset_date != hoje:
                executar_reset_diario()
                _last_reset_date = hoje

        await asyncio.sleep(30)  # checa a cada 30s

# ─────────────────────────────────────────────────────────────────────────────
# QUERIES
# ─────────────────────────────────────────────────────────────────────────────

def buscar_contadores() -> dict:
    """Contadores atuais (do dia) por câmera."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT rtsp_url FROM contadores ORDER BY rtsp_url")
        urls = [row["rtsp_url"] for row in cursor.fetchall()]

        cameras, total_geral = [], 0

        for url in urls:
            cursor.execute(
                "SELECT categoria, sentido, valor FROM contadores WHERE rtsp_url = ?", (url,)
            )
            rows = cursor.fetchall()
            cats = {
                "Carros":    {"ida": 0, "volta": 0},
                "Motos":     {"ida": 0, "volta": 0},
                "Caminhões": {"ida": 0, "volta": 0},
                "Ônibus":    {"ida": 0, "volta": 0},
            }
            for row in rows:
                cat, sent, val = row["categoria"], row["sentido"], row["valor"]
                if cat in cats and sent in cats[cat]:
                    cats[cat][sent] = val

            total_ida   = sum(v["ida"]   for v in cats.values())
            total_volta = sum(v["volta"] for v in cats.values())
            total_cam   = total_ida + total_volta
            total_geral += total_cam

            cameras.append({
                "rtsp_url":   url,
                "categorias": cats,
                "total":      {"ida": total_ida, "volta": total_volta, "geral": total_cam}
            })

        conn.close()
        return {
            "cameras":     cameras,
            "total_geral": total_geral,
            "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except FileNotFoundError as e:
        logger.error(str(e))
        return {"cameras": [], "total_geral": 0, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "erro": str(e)}
    except Exception as e:
        logger.error(f"Erro ao buscar contadores: {e}")
        return {"cameras": [], "total_geral": 0, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "erro": str(e)}


def buscar_historico(limite: int = 100) -> list:
    """Últimos N eventos — sem filtro."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.timestamp, h.categoria_id, h.sentido_id, c.rtsp_url
            FROM historico_v2 h
            JOIN cameras c ON h.camera_id = c.id
            ORDER BY h.timestamp DESC
            LIMIT ?
        """, (limite,))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "timestamp": ts_to_str(row["timestamp"]),
                "categoria": ID_MAP_CATEGORIA.get(row["categoria_id"], "?"),
                "sentido":   ID_MAP_SENTIDO.get(row["sentido_id"], "?"),
                "rtsp_url":  row["rtsp_url"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        return []


def buscar_historico_filtrado(
    inicio: Optional[float],
    fim: Optional[float],
    rtsp_url: Optional[str],
    categoria: Optional[str],
    sentido: Optional[str],
    limite: int = 500
) -> list:
    """
    Histórico com filtros de data/hora, câmera, categoria e sentido.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        where, params = [], []

        if inicio:
            where.append("h.timestamp >= ?")
            params.append(inicio)
        if fim:
            where.append("h.timestamp <= ?")
            params.append(fim)
        if rtsp_url:
            where.append("c.rtsp_url = ?")
            params.append(rtsp_url)
        if categoria and categoria in CAT_MAP_NOME:
            where.append("h.categoria_id = ?")
            params.append(CAT_MAP_NOME[categoria])
        if sentido and sentido in SENT_MAP_NOME:
            where.append("h.sentido_id = ?")
            params.append(SENT_MAP_NOME[sentido])

        sql = """
            SELECT h.timestamp, h.categoria_id, h.sentido_id, c.rtsp_url
            FROM historico_v2 h
            JOIN cameras c ON h.camera_id = c.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY h.timestamp DESC LIMIT ?"
        params.append(min(limite, 10000))

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "timestamp": ts_to_str(row["timestamp"]),
                "categoria": ID_MAP_CATEGORIA.get(row["categoria_id"], "?"),
                "sentido":   ID_MAP_SENTIDO.get(row["sentido_id"], "?"),
                "rtsp_url":  row["rtsp_url"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar histórico filtrado: {e}")
        return []


def buscar_historico_agregado(
    inicio: Optional[float],
    fim: Optional[float],
    rtsp_url: Optional[str],
    categoria: Optional[str],
    granularidade: str = "hora"   # "hora" | "dia"
) -> list:
    """
    Agrega o histórico por período (hora ou dia), retornando totais por categoria.
    Usado pelos gráficos de evolução temporal.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        where, params = [], []

        if inicio:
            where.append("h.timestamp >= ?")
            params.append(inicio)
        if fim:
            where.append("h.timestamp <= ?")
            params.append(fim)
        if rtsp_url:
            where.append("c.rtsp_url = ?")
            params.append(rtsp_url)
        if categoria and categoria in CAT_MAP_NOME:
            where.append("h.categoria_id = ?")
            params.append(CAT_MAP_NOME[categoria])

        # Formato de agrupamento SQLite
        if granularidade == "dia":
            fmt = "%Y-%m-%d"
        else:
            fmt = "%Y-%m-%d %H:00"

        sql = f"""
            SELECT
                strftime('{fmt}', datetime(h.timestamp, 'unixepoch', 'localtime')) AS periodo,
                h.categoria_id,
                COUNT(*) AS total
            FROM historico_v2 h
            JOIN cameras c ON h.camera_id = c.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY periodo, h.categoria_id ORDER BY periodo ASC"

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        # Pivotear: período → {Carros: N, Motos: N, ...}
        periodos: dict = {}
        for row in rows:
            p   = row["periodo"]
            cat = ID_MAP_CATEGORIA.get(row["categoria_id"], "Indefinido")
            tot = row["total"]
            if p not in periodos:
                periodos[p] = {"periodo": p, "Carros": 0, "Motos": 0, "Caminhões": 0, "Ônibus": 0, "total": 0}
            if cat in periodos[p]:
                periodos[p][cat] += tot
            periodos[p]["total"] += tot

        return list(periodos.values())

    except Exception as e:
        logger.error(f"Erro ao agregar histórico: {e}")
        return []


def buscar_cameras() -> list:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, rtsp_url, descricao FROM cameras ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        return [{"id": r["id"], "rtsp_url": r["rtsp_url"], "descricao": r["descricao"]} for r in rows]
    except Exception as e:
        logger.error(f"Erro ao buscar câmeras: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# ROTAS HTTP
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    if Path(DASHBOARD_PATH).exists():
        with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>dashboard.html não encontrado</h1>")


@app.get("/api/contadores")
async def get_contadores():
    """Contadores atuais do dia por câmera."""
    return buscar_contadores()


@app.get("/api/historico")
async def get_historico(limite: int = Query(default=100, le=500)):
    """Últimos N eventos sem filtro."""
    return buscar_historico(limite)


@app.get("/api/historico/filtrado")
async def get_historico_filtrado(
    inicio:    Optional[str] = Query(default=None, description="Datetime início: YYYY-MM-DDTHH:MM"),
    fim:       Optional[str] = Query(default=None, description="Datetime fim:    YYYY-MM-DDTHH:MM"),
    rtsp_url:  Optional[str] = Query(default=None, description="URL da câmera"),
    categoria: Optional[str] = Query(default=None, description="Categoria: Carros|Motos|Caminhões|Ônibus"),
    sentido:   Optional[str] = Query(default=None, description="Sentido: ida|volta"),
    limite:    int           = Query(default=500, le=10000)
):
    """
    Histórico detalhado com filtros.
    
    Exemplo:
        /api/historico/filtrado?inicio=2026-03-01T00:00&fim=2026-03-01T23:59&categoria=Carros
    """
    ts_inicio = str_to_ts(inicio)
    ts_fim    = str_to_ts(fim)
    # Se fim é só data (sem hora), avança até o final do dia
    if fim and "T" not in fim and " " not in fim:
        ts_fim = (datetime.strptime(fim, "%Y-%m-%d") + timedelta(days=1)).timestamp() - 1

    return buscar_historico_filtrado(ts_inicio, ts_fim, rtsp_url, categoria, sentido, limite)


@app.get("/api/historico/agregado")
async def get_historico_agregado(
    inicio:        Optional[str] = Query(default=None),
    fim:           Optional[str] = Query(default=None),
    rtsp_url:      Optional[str] = Query(default=None),
    categoria:     Optional[str] = Query(default=None),
    granularidade: str           = Query(default="hora", regex="^(hora|dia)$")
):
    """
    Totais agregados por hora ou dia — usado pelos gráficos de evolução.
    
    Retorna lista de objetos:
        [{"periodo": "2026-03-01 09:00", "Carros": 12, "Motos": 5, ..., "total": 20}, ...]
    """
    ts_inicio = str_to_ts(inicio)
    ts_fim    = str_to_ts(fim)
    if fim and "T" not in fim and " " not in fim:
        ts_fim = (datetime.strptime(fim, "%Y-%m-%d") + timedelta(days=1)).timestamp() - 1

    return buscar_historico_agregado(ts_inicio, ts_fim, rtsp_url, categoria, granularidade)


@app.get("/api/cameras")
async def get_cameras():
    """Lista todas as câmeras cadastradas."""
    return buscar_cameras()

# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    dados = buscar_contadores()
    await websocket.send_text(json.dumps({"tipo": "contadores", **dados}, ensure_ascii=False))
    try:
        while True:
            msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            if msg == "ping":
                await websocket.send_text(json.dumps({"tipo": "pong"}))
    except (WebSocketDisconnect, asyncio.TimeoutError):
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"[WS] Erro: {e}")
        manager.disconnect(websocket)

# ─────────────────────────────────────────────────────────────────────────────
# STARTUP TASKS
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())
    asyncio.create_task(reset_diario_loop())
    logger.info(f"[API] v2.0 iniciada em http://{HOST}:{PORT}")
    logger.info(f"[API] Dashboard:  http://localhost:{PORT}")
    logger.info(f"[API] WebSocket:  ws://localhost:{PORT}/ws")
    logger.info(f"[API] Reset diário ativo — zera contadores à meia-noite")


async def broadcast_loop():
    while True:
        await asyncio.sleep(PUSH_INTERVAL)
        if not manager.active_connections:
            continue
        try:
            dados = buscar_contadores()
            await manager.broadcast({"tipo": "contadores", **dados})
        except Exception as e:
            logger.error(f"[Broadcast] Erro: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  API MONITORAMENTO DE VEÍCULOS v2.0")
    print("=" * 60)
    print(f"  Dashboard:       http://localhost:{PORT}")
    print(f"  Contadores:      http://localhost:{PORT}/api/contadores")
    print(f"  Histórico:       http://localhost:{PORT}/api/historico")
    print(f"  Filtrado:        http://localhost:{PORT}/api/historico/filtrado")
    print(f"  Agregado:        http://localhost:{PORT}/api/historico/agregado")
    print(f"  Câmeras:         http://localhost:{PORT}/api/cameras")
    print(f"  Reset diário:    Automático à meia-noite")
    print("=" * 60)
    print()

    uvicorn.run("api:app", host=HOST, port=PORT, reload=False, log_level="warning")
