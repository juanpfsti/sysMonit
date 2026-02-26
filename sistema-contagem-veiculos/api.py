#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API de Monitoramento de Veículos
---------------------------------
Expõe os dados do sistema de contagem via HTTP e WebSocket.

Como usar:
    1. Instale as dependências:
       pip install fastapi uvicorn

    2. Coloque este arquivo na pasta raiz do projeto
       (mesmo lugar onde está o contador.db)

    3. Rode a API:
       python api.py

    4. Acesse o dashboard em:
       http://localhost:8000

Endpoints disponíveis:
    GET  /api/contadores          → contadores atuais por câmera
    GET  /api/historico           → últimos 100 eventos
    GET  /api/cameras             → lista de câmeras cadastradas
    WS   /ws                      → websocket para atualizações em tempo real
"""

import sqlite3
import asyncio
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH = "contador.db"          # Caminho para o banco de dados do sistema
DASHBOARD_PATH = "dashboard.html" # Caminho para o arquivo HTML do dashboard
HOST = "0.0.0.0"                 # 0.0.0.0 = aceita conexões de qualquer IP da rede
PORT = 8000
PUSH_INTERVAL = 2.0              # Segundos entre cada push de dados via WebSocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# APP FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="API Monitoramento de Veículos",
    description="Exposição dos dados de contagem em tempo real",
    version="1.0.0"
)

# CORS: permite que o navegador acesse a API de qualquer origem
# (necessário se o dashboard estiver em outra porta ou domínio)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# GERENCIADOR DE CONEXÕES WEBSOCKET
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionManager:
    """
    Gerencia todas as conexões WebSocket ativas.
    
    WebSocket é diferente de HTTP normal:
    - HTTP: cliente pergunta → servidor responde → conexão fecha
    - WebSocket: conexão fica aberta → servidor envia dados quando quiser
    
    Isso é o que permite o dashboard atualizar sozinho sem o usuário apertar F5.
    """

    def __init__(self):
        # Lista de todos os clientes conectados ao dashboard
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Aceita e registra uma nova conexão"""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Nova conexão. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove uma conexão encerrada"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[WS] Conexão encerrada. Total: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        """
        Envia dados para TODOS os clientes conectados.
        Se um cliente desconectou, remove da lista.
        """
        if not self.active_connections:
            return  # Ninguém conectado, não faz nada

        message = json.dumps(data, ensure_ascii=False)
        dead = []

        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)  # Conexão morta

        # Limpar conexões mortas
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# ─────────────────────────────────────────────────────────────────────────────
# ACESSO AO BANCO DE DADOS
# ─────────────────────────────────────────────────────────────────────────────

# Mapeamentos (espelho do database.py original)
ID_MAP_CATEGORIA = {0: "Indefinido", 1: "Carros", 2: "Motos", 3: "Caminhões", 4: "Ônibus"}
ID_MAP_SENTIDO   = {0: "indefinido", 1: "ida",    2: "volta"}


def get_db():
    """
    Retorna uma conexão com o banco de dados.
    
    Usamos check_same_thread=False porque o FastAPI usa múltiplas threads.
    O modo WAL permite leitura enquanto o sistema principal está escrevendo.
    """
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(f"Banco de dados não encontrado: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas por nome: row['categoria']
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA query_only=ON")   # Segurança: API só lê, nunca escreve
    return conn


def buscar_contadores() -> dict:
    """
    Busca os contadores atuais de todas as câmeras.
    
    Retorna um dict no formato:
    {
        "cameras": [
            {
                "rtsp_url": "rtsp://...",
                "categorias": {
                    "Carros":    {"ida": 10, "volta": 8},
                    "Motos":     {"ida": 5,  "volta": 3},
                    "Caminhões": {"ida": 2,  "volta": 1},
                    "Ônibus":    {"ida": 1,  "volta": 0}
                },
                "total": {"ida": 18, "volta": 12, "geral": 30}
            }
        ],
        "total_geral": 30,
        "timestamp": "2026-02-26 14:30:00"
    }
    """
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Buscar todas as câmeras com contadores
        cursor.execute("""
            SELECT DISTINCT rtsp_url FROM contadores
            ORDER BY rtsp_url
        """)
        urls = [row["rtsp_url"] for row in cursor.fetchall()]

        cameras = []
        total_geral = 0

        for url in urls:
            cursor.execute("""
                SELECT categoria, sentido, valor
                FROM contadores
                WHERE rtsp_url = ?
            """, (url,))
            rows = cursor.fetchall()

            # Montar estrutura por categoria
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
            "cameras":      cameras,
            "total_geral":  total_geral,
            "timestamp":    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    except FileNotFoundError as e:
        logger.error(str(e))
        return {"cameras": [], "total_geral": 0, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "erro": str(e)}
    except Exception as e:
        logger.error(f"Erro ao buscar contadores: {e}")
        return {"cameras": [], "total_geral": 0, "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "erro": str(e)}


def buscar_historico(limite: int = 100) -> list:
    """
    Busca os últimos N eventos do histórico.
    Retorna lista de eventos com timestamp, categoria e sentido.
    """
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
                "timestamp": datetime.fromtimestamp(row["timestamp"]).strftime("%Y-%m-%d %H:%M:%S"),
                "categoria": ID_MAP_CATEGORIA.get(row["categoria_id"], "?"),
                "sentido":   ID_MAP_SENTIDO.get(row["sentido_id"], "?"),
                "rtsp_url":  row["rtsp_url"],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        return []


def buscar_cameras() -> list:
    """Lista todas as câmeras cadastradas no banco."""
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
    """Serve o dashboard HTML principal"""
    if Path(DASHBOARD_PATH).exists():
        with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>dashboard.html não encontrado</h1><p>Coloque o arquivo dashboard.html na mesma pasta que api.py</p>")


@app.get("/api/contadores")
async def get_contadores():
    """
    Retorna os contadores atuais de todas as câmeras.
    
    Exemplo de resposta:
    {
        "cameras": [...],
        "total_geral": 42,
        "timestamp": "2026-02-26 14:30:00"
    }
    """
    return buscar_contadores()


@app.get("/api/historico")
async def get_historico(limite: int = 100):
    """
    Retorna os últimos eventos de contagem.
    
    Parâmetro: ?limite=100 (padrão: 100, máximo recomendado: 500)
    """
    limite = min(limite, 500)  # Limite de segurança
    return buscar_historico(limite)


@app.get("/api/cameras")
async def get_cameras():
    """Lista todas as câmeras cadastradas no sistema."""
    return buscar_cameras()


# ─────────────────────────────────────────────────────────────────────────────
# WEBSOCKET — TEMPO REAL
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint WebSocket para atualizações em tempo real.
    
    Fluxo:
    1. Cliente (dashboard) abre conexão: ws://localhost:8000/ws
    2. Servidor manda dados imediatamente (primeiro snapshot)
    3. A cada PUSH_INTERVAL segundos, manda dados atualizados
    4. Se cliente fechar o browser, a conexão é removida
    """
    await manager.connect(websocket)

    # Manda snapshot imediato ao conectar (não espera o próximo ciclo)
    dados = buscar_contadores()
    await websocket.send_text(json.dumps({"tipo": "contadores", **dados}, ensure_ascii=False))

    try:
        # Loop: fica esperando mensagens do cliente (keepalive)
        # O broadcast periódico acontece na task separada (ver abaixo)
        while True:
            # Aguarda qualquer mensagem do cliente (ex: ping)
            # Se o cliente fechar, raise WebSocketDisconnect
            msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            # Responde ping com pong
            if msg == "ping":
                await websocket.send_text(json.dumps({"tipo": "pong"}))

    except (WebSocketDisconnect, asyncio.TimeoutError):
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"[WS] Erro: {e}")
        manager.disconnect(websocket)


# ─────────────────────────────────────────────────────────────────────────────
# TASK DE BROADCAST PERIÓDICO
# ─────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def start_broadcast_task():
    """
    Ao iniciar a API, cria uma task assíncrona que fica rodando
    em background e envia dados para todos os clientes conectados
    a cada PUSH_INTERVAL segundos.
    
    asyncio.create_task() cria uma "coroutine" que roda em paralelo
    sem bloquear o servidor principal.
    """
    asyncio.create_task(broadcast_loop())
    logger.info(f"[API] Iniciada em http://{HOST}:{PORT}")
    logger.info(f"[API] Dashboard em http://localhost:{PORT}")
    logger.info(f"[API] WebSocket em ws://localhost:{PORT}/ws")


async def broadcast_loop():
    """
    Loop que roda para sempre em background, enviando dados
    atualizados a todos os clientes WebSocket conectados.
    """
    while True:
        await asyncio.sleep(PUSH_INTERVAL)

        if not manager.active_connections:
            continue  # Ninguém conectado, economiza processamento

        try:
            dados = buscar_contadores()
            await manager.broadcast({"tipo": "contadores", **dados})
        except Exception as e:
            logger.error(f"[Broadcast] Erro: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 55)
    print("  API MONITORAMENTO DE VEÍCULOS")
    print("=" * 55)
    print(f"  Dashboard: http://localhost:{PORT}")
    print(f"  API JSON:  http://localhost:{PORT}/api/contadores")
    print(f"  Câmeras:   http://localhost:{PORT}/api/cameras")
    print(f"  Histórico: http://localhost:{PORT}/api/historico")
    print("=" * 55)
    print()

    uvicorn.run(
        "api:app",
        host=HOST,
        port=PORT,
        reload=False,       # True = reinicia ao salvar o arquivo (útil em desenvolvimento)
        log_level="warning" # Reduz logs do uvicorn para não poluir o terminal
    )
