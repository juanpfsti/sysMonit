#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thread de detecção e tracking de veículos (Orquestrador)
Refatorado para incluir Captura RTSP Bufferizada e lógica robusta anti-crash.
"""

import cv2
import time
import logging
import threading
import queue
import os
import platform
import numpy as np
from contextlib import contextmanager
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

from .config import Config
from .counter import VehicleCounter
from .database import CounterDatabase

# ========================= Supressor de STDERR =========================
# Lock global para serializar manipulação de fd 2 (stderr) entre threads.
# Sem lock, duas threads em SuppressFFmpegOutput concorrentemente podem
# corromper a tabela de file descriptors do processo.
_ffmpeg_suppress_lock = threading.Lock()

@contextmanager
def SuppressFFmpegOutput():
    """Context manager para suprimir completamente output do FFMPEG/H.264 (thread-safe)"""
    if platform.system() == 'Windows':
        devnull = 'NUL'
    else:
        devnull = os.devnull

    _ffmpeg_suppress_lock.acquire()
    null_fd = None
    save_fd = None
    suppressed = False
    try:
        null_fd = os.open(devnull, os.O_RDWR)
        save_fd = os.dup(2)
        os.dup2(null_fd, 2)
        suppressed = True
    except Exception:
        pass  # Falha no setup: yield sem supressão, lock será liberado no finally
    try:
        yield
    finally:
        if suppressed:
            try:
                os.dup2(save_fd, 2)
                os.close(null_fd)
                os.close(save_fd)
            except Exception:
                pass
        _ffmpeg_suppress_lock.release()

# ========================= Detecção de PyAV =========================
try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False

# ========================= Classes de Captura =========================
class RTSPCapture:
    """Captura RTSP que usa PyAV (preferencial) ou OpenCV (fallback)."""
    def __init__(self, url, use_pyav=None):
        self.url = url
        self.container = None
        self.cap = None
        self.stream = None

        if use_pyav is None:
            use_pyav = PYAV_AVAILABLE and isinstance(url, str) and url.startswith('rtsp://')

        self.using_pyav = use_pyav

        if self.using_pyav and PYAV_AVAILABLE:
            self._open_pyav()
        else:
            self._open_opencv()

    def _open_pyav(self):
        try:
            options = {
                'rtsp_transport': 'tcp',
                'rtsp_flags': 'prefer_tcp',
                'stimeout': '5000000',
                'max_delay': '500000',
            }
            with SuppressFFmpegOutput():
                self.container = av.open(self.url, options=options)
            self.stream = self.container.streams.video[0]
            self.stream.thread_type = 'AUTO'
        except Exception as e:
            logging.error(f"Erro ao abrir com PyAV: {e}")
            # Fechar container se foi parcialmente aberto para evitar leak de conexão
            if self.container is not None:
                try:
                    self.container.close()
                except Exception:
                    pass
                self.container = None
            self.using_pyav = False
            self._open_opencv()

    def _open_opencv(self):
        if isinstance(self.url, str) and self.url.startswith('rtsp://'):
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|rtbufsize;100M|max_delay;5000000|stimeout;5000000|allowed_media_types;video|fflags;+genpts+igndts+discardcorrupt|flags;+low_delay|skip_loop_filter;all"
            )
        with SuppressFFmpegOutput():
            self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            raise Exception("Não foi possível abrir stream com OpenCV")
        # Limita bloqueio de cap.read() a 5s — evita que _read_loop fique suspenso
        # indefinidamente quando a rede cai, causando race condition no release()
        try:
            self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        except Exception:
            pass  # Não disponível em todas as builds do OpenCV

    def read(self):
        if self.using_pyav:
            return self._read_pyav()
        else:
            return self._read_opencv()

    def _read_pyav(self):
        try:
            with SuppressFFmpegOutput():
                for packet in self.container.demux(self.stream):
                    for frame in packet.decode():
                        img = frame.to_ndarray(format='bgr24')
                        return True, img
            return False, None
        except Exception:
            return False, None

    def _read_opencv(self):
        with SuppressFFmpegOutput():
            return self.cap.read()

    def release(self):
        if self.container:
            self.container.close()
        if self.cap:
            self.cap.release()

    def isOpened(self):
        if self.using_pyav:
            return self.container is not None
        else:
            return self.cap is not None and self.cap.isOpened()

    def get(self, prop):
        if self.using_pyav and self.stream:
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return self.stream.codec_context.width
            elif prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return self.stream.codec_context.height
            elif prop == cv2.CAP_PROP_FPS:
                return float(self.stream.average_rate) if self.stream.average_rate else 25.0
            return 0
        elif self.cap:
            return self.cap.get(prop)
        return 0
        
    def set(self, prop, value):
        if self.cap:
            self.cap.set(prop, value)

class RTSPBufferedCapture:
    """
    Captura RTSP com buffer circular e thread dedicada.
    Solução profissional: lê frames continuamente em background.
    Possui detecção de freeze: após FREEZE_TIMEOUT s sem novo frame real,
    read() retorna (False, None) para forçar reconexão em run().
    """
    FREEZE_TIMEOUT = 10.0  # segundos sem frame real → sinaliza freeze

    def __init__(self, url, buffer_size=2, stop_event=None):
        self.url = url
        self.buffer_size = buffer_size
        self.frame_queue = queue.Queue(maxsize=buffer_size)
        self.running = False
        self.thread = None
        self.base_capture = RTSPCapture(url)
        self.last_good_frame = None
        self.last_new_frame_time = 0.0   # epoch do último frame REAL recebido
        self._stop_event = stop_event    # Event externo para interromper esperas
        self.first_frame_ready = threading.Event()
        # Rastreamento da sub-thread de leitura ativa, para garantir que
        # base_capture.release() só é chamado após cap.read() retornar.
        self._read_thread_lock = threading.Lock()
        self._active_read_thread = None
        self.start()

        # Aguardar primeiro frame com suporte a interrupção (timeout de 10 segundos)
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if self._stop_event and self._stop_event.is_set():
                break                        # parada solicitada externamente
            if self.first_frame_ready.wait(timeout=0.3):
                break                        # frame recebido
        else:
            logging.warning("Timeout aguardando primeiro frame do stream RTSP")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()

    def _safe_base_read(self, timeout=6.0):
        """
        Executa base_capture.read() em sub-thread com timeout garantido.
        Isso evita que cap.read() bloqueie indefinidamente durante mudanças de
        topologia de rede (ex: looping de switch, reconvergência STP), onde o
        stimeout do FFmpeg não se aplica a conexões TCP já estabelecidas.
        Retorna (ret, frame, timed_out).
        """
        result = [None]

        def _target():
            try:
                result[0] = self.base_capture.read()
            except Exception:
                result[0] = (False, None)

        t = threading.Thread(target=_target, daemon=True)
        with self._read_thread_lock:
            self._active_read_thread = t
        t.start()
        t.join(timeout=timeout)
        with self._read_thread_lock:
            if self._active_read_thread is t:
                self._active_read_thread = None

        if t.is_alive():
            # cap.read() ainda bloqueado — sinaliza timeout para o loop reagir
            logging.warning("[RTSPCapture] Timeout em cap.read() — rede instável, aguardando...")
            return False, None, True

        if result[0] is None:
            return False, None, False
        return result[0][0], result[0][1], False

    def _read_loop(self):
        frame_count = 0
        while self.running:
            try:
                ret, frame, timed_out = self._safe_base_read(timeout=6.0)
                # Verificar running imediatamente após o read retornar,
                # para sair limpo quando release() chamar self.running = False
                if not self.running:
                    break
                if timed_out or not ret or frame is None:
                    time.sleep(0.01)
                    continue

                frame_count += 1
                try:
                    if self.frame_queue.full():
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.frame_queue.put_nowait(frame)

                    if frame_count == 1:
                        self.first_frame_ready.set()
                except queue.Full:
                    pass
            except Exception:
                if not self.running:
                    break
                time.sleep(0.01)

    def read(self):
        try:
            frame = self.frame_queue.get(timeout=1.0)
            self.last_new_frame_time = time.time()
            self.last_good_frame = frame
            return True, frame
        except queue.Empty:
            # Se já passou FREEZE_TIMEOUT desde o último frame real, sinaliza falha
            if self.last_new_frame_time > 0:
                elapsed = time.time() - self.last_new_frame_time
                if elapsed > self.FREEZE_TIMEOUT:
                    return False, None  # Força reconexão em process_video/run()
            if self.last_good_frame is not None:
                return True, self.last_good_frame.copy()
            return False, None

    def isOpened(self):
        return self.base_capture.isOpened() and self.running

    def get(self, prop):
        return self.base_capture.get(prop)
        
    def set(self, prop, value):
        return self.base_capture.set(prop, value)

    def release(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            # _safe_base_read() garante timeout de 6s por leitura, então
            # o loop deve encerrar em ≤6s após self.running=False.
            self.thread.join(timeout=8.0)
        # CRÍTICO: aguardar a sub-thread de leitura ativa antes de chamar release().
        # Sem isso, cap.release() pode ser chamado enquanto cap.read() ainda bloqueia
        # na sub-thread (que ficou pendurada além do timeout do join acima),
        # causando crash em nível C por acesso a memória já liberada.
        # Isso ocorre especialmente ao remover o switch que gerou o looping:
        # a reconvergência STP causa uma nova transição de rede que pode deixar
        # cap.read() bloqueado em estado TCP inconsistente.
        with self._read_thread_lock:
            active = self._active_read_thread
        if active and active.is_alive():
            active.join(timeout=7.0)
        try:
            self.base_capture.release()
        except Exception:
            pass
        
    @property
    def using_pyav(self):
        return self.base_capture.using_pyav

# ========================= Thread de Vídeo =========================
class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    update_counters = pyqtSignal(dict)
    update_fps = pyqtSignal(str)
    update_status = pyqtSignal(str)
    update_queue_stats = pyqtSignal(dict)  # Novo sinal para métricas de fila
    log_message = pyqtSignal(str)

    def __init__(self, config: Config, database=None, rtsp_url='', model_override=None, conf_override=None):
        super().__init__()
        self.config = config
        self.rtsp_url = rtsp_url
        self.model_override = model_override
        self.conf_override = conf_override  # Confiança fixa p/ evitar interferência com config compartilhado
        self.running = False
        self._stop_requested = threading.Event()  # Interrompe esperas bloqueantes
        
        # Flags de controle independentes
        self.monitoring_active = False
        self.queue_active = False
        
        # Database & Counter
        if database is None:
            database = CounterDatabase()
        self.database = database
        self.counter = VehicleCounter(database=database, rtsp_url=rtsp_url)

        # Queue Manager com banco dedicado (queue.db) — sem compartilhar lock com o contador
        from .queue_manager import QueueManager
        from .queue_database import QueueDatabase
        self._queue_db = QueueDatabase()
        self.queue_manager = QueueManager(config, database=self._queue_db, rtsp_url=rtsp_url or '')

        self.cap = None
        self.model = None

        # Tracking State
        self.track_last_center = {}
        self.track_last_center_xy = {}
        self.track_counted = {}
        self.track_last_zone = {}
        self.track_last_event_time = {}
        self.track_last_seen = {}
        self.track_ttl = 2.0
        self.last_frame = None

        # Validation Config
        self.validation_enabled = bool(self.config.get('rtsp_enable_frame_validation', True))
        self.skip_corrupted_frames = bool(self.config.get('rtsp_skip_corrupted_frames', True))
        self.last_valid_frame = None
        self.invalid_frame_count = 0
        
        # Visual Config
        self.show_labels = bool(self.config.get('show_labels', False))
        self.show_zone_tags = bool(self.config.get('show_zone_tags', True))
        self.hide_detection_lines = bool(self.config.get('hide_detection_lines', False))

        # Scene Drawer
        from .scene_drawer import SceneDrawer
        self.scene_drawer = SceneDrawer(self.config)

    def set_monitoring_active(self, active: bool):
        self.monitoring_active = active
        self.log_message.emit(f"Monitoramento {'ATIVADO' if active else 'DESATIVADO'}")

    def set_queue_active(self, active: bool):
        self.queue_active = active
        self.log_message.emit(f"Fila {'ATIVADO' if active else 'DESATIVADO'}")

    def set_visual_config(self, show_labels: bool, show_zone_tags: bool, hide_detection_lines: bool):
        self.show_labels = show_labels
        self.show_zone_tags = show_zone_tags
        self.hide_detection_lines = hide_detection_lines
        # Atualizar também o SceneDrawer se necessário, mas ele lê da config?
        # SceneDrawer recebe config no init. Se ele usa self.config['key'], precisamos atualizar self.config também.
        self.config.set('show_labels', show_labels)
        self.config.set('show_zone_tags', show_zone_tags)
        self.config.set('hide_detection_lines', hide_detection_lines)
        # SceneDrawer pode precisar de reload ou setters, mas por enquanto assumimos que o detector usa essas flags.

    def load_yolo_model(self):
        # Usar is not None para não confundir string vazia com ausência de override
        modelo_path = self.model_override if self.model_override is not None else self.config.get('modelo_yolo', 'yolo11s.pt')
        if not modelo_path:
            modelo_path = self.config.get('modelo_yolo', 'yolo11s.pt')
        try:
            import sys
            import os
            
            # Configuração prévia para evitar erros de DLL do PyTorch
            # Define variáveis de ambiente que ajudam PyTorch a encontrar suas DLLs
            os.environ['MKL_THREADING_LAYER'] = 'GNU'
            os.environ['OMP_NUM_THREADS'] = '4'
            
            # Lazy loading com tratamento robusto de DLL
            try:
                from ultralytics import YOLO
            except (OSError, RuntimeError, ImportError) as dll_error:
                # Erro de DLL do PyTorch - comum em PyInstaller
                error_msg = str(dll_error)
                if "DLL" in error_msg or "c10.dll" in error_msg or "torch" in error_msg.lower():
                    self.log_message.emit("⚠️  AVISO: Problema com bibliotecas PyTorch (DLL)")
                    self.log_message.emit("   Tentando alternativa de carregamento...")
                    
                    # Tenta importing com configuração alternativa
                    # Adiciona paths possíveis para DLLs do PyTorch
                    torch_dll_paths = [
                        os.path.join(os.getenv('TEMP'), 'torch_dll'),
                        os.path.join(os.path.dirname(sys.executable), 'Library', 'bin'),
                        os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages', 'torch', 'lib'),
                    ]
                    
                    for dll_path in torch_dll_paths:
                        if dll_path not in sys.path and os.path.exists(dll_path):
                            sys.path.insert(0, dll_path)
                    
                    # Tenta novamente
                    try:
                        from ultralytics import YOLO
                    except Exception as e2:
                        self.log_message.emit("❌ ERRO: Falha ao carregar PyTorch")
                        self.log_message.emit("   Solução 1: Instale Visual C++ Redistributable")
                        self.log_message.emit("   https://support.microsoft.com/en-us/help/2977003/")
                        self.log_message.emit("")
                        self.log_message.emit("   Solução 2: Execute 'python fix_pytorch_dll.py'")
                        self.log_message.emit("   Detalhes do erro: " + str(e2))
                        return False
                else:
                    raise
            
            self.log_message.emit(f"Carregando modelo {modelo_path}...")
            self.model = YOLO(modelo_path)
            self.log_message.emit(f"✅ Modelo {modelo_path} carregado com sucesso!")
            return True
            
        except ImportError as e:
            self.log_message.emit("❌ ERRO: Ultralytics não instalado. Instale: pip install ultralytics")
            self.log_message.emit(f"   Detalhes: {e}")
            return False
        except Exception as e:
            self.log_message.emit(f"❌ ERRO ao carregar modelo: {e}")
            return False

    def is_frame_valid(self, frame):
        if not self.validation_enabled or not self.skip_corrupted_frames:
            return True
        try:
            if frame is None or frame.size == 0: return False
            h, w = frame.shape[:2]
            if h < 10 or w < 10: return False
            # Verifica apenas o centro para performance
            center_h_start = h // 4
            center_h_end = 3 * h // 4
            center_w_start = w // 4
            center_w_end = 3 * w // 4
            sample = frame[center_h_start:center_h_end, center_w_start:center_w_end]
            gray_sample = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            mean_brightness = np.mean(gray_sample)
            if mean_brightness < 1 or mean_brightness > 254: return False
            return True
        except Exception:
            return True

    def apply_roi_crop(self, frame):
        use_roi = bool(self.config.get('use_roi_crop', False))
        if not use_roi:
            return frame, 0, 0
        
        roi_cfg = self.config.get('roi_crop', {})
        h, w = frame.shape[:2]
        
        top = max(0, min(50, roi_cfg.get('top_percent', 0)))
        bottom = max(0, min(50, roi_cfg.get('bottom_percent', 0)))
        left = max(0, min(50, roi_cfg.get('left_percent', 0)))
        right = max(0, min(50, roi_cfg.get('right_percent', 0)))
        
        y_start = int(h * top / 100)
        y_end = int(h * (100 - bottom) / 100)
        x_start = int(w * left / 100)
        x_end = int(w * (100 - right) / 100)
        
        if y_end <= y_start or (y_end - y_start) < 32: y_start, y_end = 0, h
        if x_end <= x_start or (x_end - x_start) < 32: x_start, x_end = 0, w
        
        return frame[y_start:y_end, x_start:x_end, :], y_start, x_start

    def crossed_horizontal_line(self, prev_xy, curr_xy, x1, x2, y, band=2):
        (px, py), (cx, cy) = prev_xy, curr_xy
        prev_side = py - y
        curr_side = cy - y
        if (prev_side > band and curr_side > band) or (prev_side < -band and curr_side < -band):
            return False, None, None
        denom = (cy - py)
        if abs(denom) < 1e-6: return False, None, None
        t = (y - py) / denom
        if not (0.0 <= t <= 1.0): return False, None, None
        x_cross = px + t * (cx - px)
        if x1 <= x_cross <= x2:
            if py >= y and cy < y: return True, x_cross, 'ida'
            elif py < y and cy >= y: return True, x_cross, 'volta'
        return False, None, None

    def run(self):
        self.running = True
        self.log_message.emit("Inicializando sistema v2.5...")

        if not self.load_yolo_model():
            self.update_status.emit("Erro Modelo")
            return

        # Usar URL passada ao construtor (ex: câmera de fila); senão cair no config
        rtsp_url = self.rtsp_url or self.config.get('rtsp_url') or 0
        
        MAX_FAST_RETRIES = 5
        SLOW_RETRY_INTERVAL_S = 60  # segundos entre tentativas lentas
        tentativa = 0

        while self.running:
            cap_local = None
            try:
                cap_local = RTSPBufferedCapture(
                    rtsp_url, buffer_size=3, stop_event=self._stop_requested
                )
                if not cap_local.isOpened():
                    raise Exception("Falha ao abrir stream")

                self.cap = cap_local
                tentativa = 0          # conexão bem-sucedida: resetar contador
                self.update_status.emit("Online")
                self.log_message.emit("Conectado ao stream")
                self.process_video()

                # process_video() retornou (freeze detectado ou self.running=False)
                if self.running:
                    self.log_message.emit("Stream interrompido — reconectando em 3s...")
                    self.update_status.emit("Reconectando...")
                    for _ in range(30):    # sleep(3) interrompível
                        if not self.running:
                            break
                        time.sleep(0.1)

            except Exception as e:
                if self.running:   # Só loga se não foi parada intencional
                    tentativa += 1
                    if tentativa <= MAX_FAST_RETRIES:
                        # Tentativas rápidas: a cada 5s
                        self.log_message.emit(f"Erro conexão ({tentativa}/{MAX_FAST_RETRIES}): {e}")
                        self.update_status.emit("Reconectando...")
                        for _ in range(50):    # sleep(5) interrompível
                            if not self.running:
                                break
                            time.sleep(0.1)
                    else:
                        # Servidor indisponível: tentativas lentas a cada 60s
                        if tentativa == MAX_FAST_RETRIES + 1:
                            self.log_message.emit(
                                f"Servidor indisponível. Reconexão automática a cada {SLOW_RETRY_INTERVAL_S}s..."
                            )
                            self.update_status.emit("Offline")
                        else:
                            self.log_message.emit(f"Tentando reconectar... (tentativa {tentativa})")
                        for _ in range(SLOW_RETRY_INTERVAL_S * 10):  # sleep(60) interrompível
                            if not self.running:
                                break
                            time.sleep(0.1)

            finally:
                self.cap = None
                if cap_local is not None:
                    try:
                        cap_local.release()
                    except Exception:
                        pass

    def process_video(self):
        fps_counter = 0
        fps_start = time.time()
        tracker_yaml = self.config.get('tracker', 'bytetrack.yaml')
        # conf_override garante que a thread de fila usa sua própria confiança,
        # sem interferir com o config compartilhado do monitoramento
        if self.conf_override is not None:
            conf_value = float(self.conf_override)
        else:
            conf_value = float(self.config.get('confianca_minima', 0.5))
        
        while self.running:
            try:
                # 1. Captura — RTSPBufferedCapture.read() faz apenas queue.get(),
                # sem operações FFmpeg, portanto não precisa de SuppressFFmpegOutput.
                # Usar o wrapper aqui causava manipulação concorrente de fd (stderr)
                # com a thread de background, corrompendo a tabela de file descriptors.
                ret, frame = self.cap.read()
                
                if not ret or frame is None:
                    # Se falhar leitura, quebra loop para tentar reconexão em run()
                    break

                # Armazenar frame bruto para diálogos de config (ROI, Queue)
                self.last_frame = frame

                # 2. Validação e Crop
                if not self.is_frame_valid(frame): continue
                
                proc_frame, oy, ox = self.apply_roi_crop(frame)
                ph, pw = proc_frame.shape[:2]
                annotated = proc_frame.copy()

                # 3. Controle de Inferência
                if not self.monitoring_active and not self.queue_active:
                    pass
                else:
                    # 4. Inferência YOLO
                    # Sem filtro fixo de classes: compatível com modelos customizados e COCO
                    results = self.model.track(
                        proc_frame,
                        conf=conf_value,
                        persist=True,
                        tracker=tracker_yaml,
                        verbose=False,
                    )
                    
                    # 5. Extração de Tracks
                    current_tracks = []
                    if results and results[0].boxes and results[0].boxes.id is not None:
                        boxes = results[0].boxes
                        ids = boxes.id.cpu().numpy().astype(int)
                        clss = boxes.cls.cpu().numpy().astype(int)
                        xyxys = boxes.xyxy.cpu().numpy().astype(int)
                        
                        for i, tid in enumerate(ids):
                            current_tracks.append({
                                'id': tid,
                                'box': xyxys[i],
                                'label': self.model.names[clss[i]],
                                'class_id': clss[i],
                                'color': (0, 255, 0) # Default
                            })

                        # 6. Monitoramento (Contagem)
                        if self.monitoring_active:
                            # Configs de Contagem
                            mode = self.config.get('counting_mode', 'line')
                            lc = self.config.get('line_config', {})
                            lx1 = int(pw * lc.get('x1_ratio', 0.10))
                            lx2 = int(pw * lc.get('x2_ratio', 0.90))
                            ly  = int(ph * lc.get('y_ratio',  0.55))
                            band= int(lc.get('band_px', 2))
                            
                            zc = self.config.get('zones_config', {})
                            zones_dir = self.config.get('zones_direction', {'down': 'ida', 'up': 'volta'})
                            cooldown = float(self.config.get('zone_event_cooldown', 0.8))
                            current_time = time.time()

                            def in_rect(pt, rect_norm):
                                x1=int(rect_norm[0]*pw); y1=int(rect_norm[1]*ph)
                                x2=int(rect_norm[2]*pw); y2=int(rect_norm[3]*ph)
                                return x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2

                            for track_data in current_tracks:
                                try:
                                    track_id = track_data['id']
                                    class_name = track_data['label']
                                    x1, y1, x2, y2 = track_data['box']
                                    cx, cy = (x1+x2)//2, (y1+y2)//2
                                    curr_xy = (cx, cy)
                                    
                                    if class_name not in self.config.get('categorias'): continue
                                    
                                    if track_id not in self.track_counted:
                                        self.track_counted[track_id] = {'ida': False, 'volta': False}
                                        
                                    prev_xy = self.track_last_center_xy.get(track_id, curr_xy)
                                    
                                    # Lógica Line vs Zone
                                    sentido_live = 'volta'
                                    if mode == 'line':
                                        crossed, x_cross, s_event = self.crossed_horizontal_line(prev_xy, curr_xy, lx1, lx2, ly, band)
                                        if crossed:
                                            # Separação por faixa (posição horizontal) se x_mid_ratio configurado
                                            x_mid_ratio = lc.get('x_mid_ratio')
                                            if x_mid_ratio is not None and x_cross is not None:
                                                x_mid_px = int(pw * x_mid_ratio)
                                                s_event = 'ida' if x_cross < x_mid_px else 'volta'
                                            # Inverter sentido
                                            if lc.get('invert_direction', False):
                                                s_event = 'volta' if s_event == 'ida' else 'ida'
                                            # Filtro de sentido único
                                            direction_mode = lc.get('direction_mode', 'both')
                                            if direction_mode == 'ida_only' and s_event == 'volta':
                                                crossed = False
                                            elif direction_mode == 'volta_only' and s_event == 'ida':
                                                crossed = False
                                        if crossed:
                                            if s_event == 'ida' and not self.track_counted[track_id]['ida']:
                                                self.counter.adicionar(class_name, 'ida')
                                                self.track_counted[track_id]['ida'] = True
                                                self.log_message.emit(f"CONTADO: {class_name} ID:{track_id} (IDA)")
                                            elif s_event == 'volta' and not self.track_counted[track_id]['volta']:
                                                self.counter.adicionar(class_name, 'volta')
                                                self.track_counted[track_id]['volta'] = True
                                                self.log_message.emit(f"CONTADO: {class_name} ID:{track_id} (VOLTA)")
                                        sentido_live = 'ida' if cy < ly else 'volta'
                                        if lc.get('invert_direction', False):
                                            sentido_live = 'volta' if sentido_live == 'ida' else 'ida'
                                    else: # Zone
                                        down_r = zc.get('down', [0.1,0.6,0.9,0.95])
                                        up_r = zc.get('up', [0.1,0.05,0.9,0.4])
                                        now = 'down' if in_rect(curr_xy, down_r) else ('up' if in_rect(curr_xy, up_r) else None)
                                        was = self.track_last_zone.get(track_id)
                                        
                                        if now and now != was:
                                            target = zones_dir.get(now)
                                            last_t = self.track_last_event_time.get(track_id, 0)
                                            if target and (current_time - last_t > cooldown):
                                                if target == 'ida' and not self.track_counted[track_id]['ida']:
                                                    self.counter.adicionar(class_name, 'ida')
                                                    self.track_counted[track_id]['ida'] = True
                                                    self.track_last_event_time[track_id] = current_time
                                                elif target == 'volta' and not self.track_counted[track_id]['volta']:
                                                    self.counter.adicionar(class_name, 'volta')
                                                    self.track_counted[track_id]['volta'] = True
                                                    self.track_last_event_time[track_id] = current_time
                                        self.track_last_zone[track_id] = now
                                        sentido_live = zones_dir.get(now, 'volta') if now else 'volta'

                                    # Update track
                                    track_data['color'] = (0,255,0) if sentido_live == 'ida' else (255,0,0)
                                    self.track_last_center_xy[track_id] = curr_xy
                                    self.track_last_seen[track_id] = current_time
                                    
                                except Exception as e:
                                    continue

                        # 7. Fila
                        if self.queue_active:
                            self.queue_manager.update(current_tracks, (ph, pw))
                            self.update_queue_stats.emit(self.queue_manager.get_stats())
                            
                        # 8. Desenho Tracks
                        self.scene_drawer.draw_tracks(annotated, current_tracks)

                # 9. Overlays Globais
                # Linha/zonas de contagem só quando o monitoramento estiver ativo
                if self.monitoring_active:
                    self.scene_drawer.draw_overlays(annotated)

                # Overlay de fila só quando o modo fila estiver ativo
                if self.queue_active:
                    q_render = self.queue_manager.get_render_data()
                    self.scene_drawer.draw_queue_overlays(annotated, q_render)

                # 10. Cleanup de Tracks Antigos
                now_t = time.time()
                to_del = [t for t, ts in self.track_last_seen.items() if now_t - ts > self.track_ttl]
                for t in to_del:
                    self.track_last_center_xy.pop(t, None)
                    self.track_counted.pop(t, None)
                    self.track_last_seen.pop(t, None)
                    self.track_last_zone.pop(t, None)

                # 11. Sinais
                self.update_counters.emit(self.counter.contadores)
                
                fps_counter += 1
                if time.time() - fps_start >= 1.0:
                    fps = fps_counter / (time.time() - fps_start)
                    self.update_fps.emit(f"FPS: {fps:.1f}")
                    fps_counter = 0
                    fps_start = time.time()

                # 12. Emitir Imagem
                rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb.shape
                # CRÍTICO: .copy() para evitar crash
                qt_img = QImage(rgb.data, w, h, w*ch, QImage.Format_RGB888).copy()
                self.change_pixmap_signal.emit(qt_img)

            except Exception as e:
                self.log_message.emit(f"Erro processamento: {e}")
                time.sleep(1)

    def stop(self):
        self.running = False
        self._stop_requested.set()   # interrompe esperas bloqueantes em RTSPBufferedCapture
        if not self.wait(5000):      # até 5 s para terminar limpo
            self.terminate()
            self.wait(2000)
        self.cleanup()

    def cleanup(self):
        if self.cap:
            self.cap.release()
        try:
            if self.counter and self.counter.database:
                self.counter.save_to_database()
        except:
            pass
        try:
            if hasattr(self, '_queue_db') and self._queue_db:
                self._queue_db.close()
        except:
            pass
