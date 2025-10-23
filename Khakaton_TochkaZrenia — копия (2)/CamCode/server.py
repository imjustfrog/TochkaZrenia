import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import cv2
import time
import numpy as np
from datetime import datetime
import threading
import subprocess
import platform
import logging
import psutil
import collections

# Настройка путей для Flask
import os
template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Site', 'templates')
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Site', 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Глобальные переменные
monitor_thread = None
is_monitoring = False
current_mode = None
current_camera_url = "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"

# Путь к файлу логов, который читает фронтенд через /api/logs
log_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Site', 'templates', 'log.txt')

# Неблокирующий логгер с буфером (для снижения IO при 1000+ событиях/сек)
class AsyncFileLogger:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.queue = collections.deque()
        self._file = None
        self._running = False

    def start(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            self._file = open(self.file_path, 'a', encoding='utf-8', buffering=1)
            self._running = True
            # Запускаем фонового писателя на eventlet
            eventlet.spawn_n(self._writer_loop)
        except Exception as e:
            print(f"[LOG_INIT_ERROR] {datetime.now().strftime('%H:%M:%S')} - {e}")

    def stop(self):
        self._running = False
        try:
            if self._file:
                self._file.flush()
                self._file.close()
        except Exception:
            pass

    def log(self, text: str):
        try:
            self.queue.append(text)
        except Exception:
            pass

    def _writer_loop(self):
        # Периодически сбрасываем пакет записей, чтобы уменьшить количество fsync
        while self._running:
            batch = []
            try:
                # собираем до 200 строк или до 100 мс
                start = time.time()
                while len(batch) < 200 and (time.time() - start) < 0.1:
                    try:
                        line = self.queue.popleft()
                        batch.append(line)
                    except IndexError:
                        eventlet.sleep(0.01)
                if batch and self._file:
                    self._file.write("\n".join(batch) + "\n")
                    self._file.flush()
            except Exception as e:
                print(f"[LOG_WRITE_ERROR] {datetime.now().strftime('%H:%M:%S')} - {e}")
            finally:
                eventlet.sleep(0.05)

file_logger = AsyncFileLogger(log_file_path)
file_logger.start()

def append_log_to_file(text: str):
    file_logger.log(text)

class WebCameraMonitor:
    def __init__(self, rtsp_url, camera_id, socketio, mode='basic'):
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.socketio = socketio
        self.mode = mode
        self.bitrate_history = []
        self.fps_history = []
        self.window_size = 30
        self.threshold_ratio = 0.3
        self.low_bitrate_count = 0
        self.max_low_bitrate_count = 3
        # Метрики нагрузки
        self.process = psutil.Process()
        self._primed_cpu = False
        self.loop_time_history = []  # мс за цикл
        # Параметры переподключения
        self.reconnect_delay_sec = 5
        self.max_reconnect_delay_sec = 5
        # Пинг-охлаждение
        self.last_ping_time = 0.0
        self.ping_cooldown_sec = 60.0
        
    def extract_host(self):
        """Извлечение host из RTSP URL"""
        try:
            if '@' in self.rtsp_url:
                host_part = self.rtsp_url.split('@')[1]
            else:
                host_part = self.rtsp_url.split('//')[1]
            return host_part.split(':')[0]
        except:
            return None
    
    def ping_camera(self, host):
        """Пинг камеры ТОЛЬКО при проблемах, не чаще 1 раза в 60 секунд на камеру"""
        now = time.time()
        if (now - self.last_ping_time) < self.ping_cooldown_sec:
            return "cooldown"
        self.last_ping_time = now
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", host]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            return "success" if result.returncode == 0 else "failed"
        except Exception:
            return "error"
    
    def check_bitrate_drop(self, current_bitrate):
        """Проверка падения битрейта"""
        if len(self.bitrate_history) < self.window_size:
            return False
        window = self.bitrate_history[-self.window_size:]
        avg_bitrate = (sum(window) / len(window)) if window else 0
        return current_bitrate < avg_bitrate * self.threshold_ratio and avg_bitrate > 1000
    
    def check_fps_drop(self, current_fps):
        """Проверка падения FPS"""
        if len(self.fps_history) < 10:
            return False
        window = self.fps_history[-10:]
        avg_fps = (sum(window) / len(window)) if window else 0
        return current_fps < 5 or (avg_fps > 10 and current_fps < avg_fps * 0.2)
    
    def analyze_image_quality(self, frame):
        """Анализ качества изображения (для расширенного режима)"""
        if frame is None or self.mode != 'advanced':
            return {}
        
        quality_metrics = {}
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Детекция черного/белого экрана
            mean_brightness = np.mean(gray)
            quality_metrics['brightness'] = mean_brightness
            if mean_brightness < 10:
                quality_metrics['black_screen'] = True
            elif mean_brightness > 240:
                quality_metrics['white_screen'] = True
            
            # Анализ резкости
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            quality_metrics['sharpness'] = laplacian_var
            quality_metrics['blurry'] = laplacian_var < 50
            
            # Анализ контраста
            contrast = np.std(gray)
            quality_metrics['contrast'] = contrast
            quality_metrics['low_contrast'] = contrast < 20
            
        except Exception as e:
            print(f"Ошибка анализа изображения: {e}")
            
        return quality_metrics
    
    def send_status_update(self, data):
        """Отправка данных через WebSocket"""
        self.socketio.emit('status_update', data)
        # Дублируем в консоль и файл
        try:
            summary = (f"STATUS {datetime.now().strftime('%H:%M:%S')} - "
                       f"bitrate: {data.get('bitrate', '--')}kbps, "
                       f"fps: {data.get('fps', '--')}, "
                       f"quality: {data.get('quality', '--')}, "
                       f"conn: {data.get('connectionStatus', '--')}, "
                       f"alert: {data.get('alert', False)}")
            print(summary)
            append_log_to_file(summary)
        except Exception as e:
            print(f"[STATUS_LOG_ERROR] {datetime.now().strftime('%H:%M:%S')} - {e}")
    
    def send_log_entry(self, message, log_type='info'):
        """Отправка лога через WebSocket"""
        ts = datetime.now().strftime('%H:%M:%S')
        payload = {
            'message': message,
            'type': log_type,
            'time': ts
        }
        self.socketio.emit('log_entry', payload)
        # Дублируем в консоль и файл
        prefix = 'INFO'
        if log_type == 'error':
            prefix = 'ERROR'
        elif log_type == 'warning':
            prefix = 'WARNING'
        elif log_type == 'success':
            prefix = 'SUCCESS'
        line = f"[{prefix}] {ts} - {message}"
        print(line)
        append_log_to_file(line)
    
    def monitor_stream(self):
        """Основной цикл мониторинга"""
        global is_monitoring
        
        self.send_log_entry(f'Запуск мониторинга ({self.mode} режим)...', 'info')
        
        def open_capture():
            try:
                return cv2.VideoCapture(self.rtsp_url)
            except Exception:
                return cv2.VideoCapture()  # пустой cap

        cap = open_capture()
        if not cap.isOpened():
            self.send_log_entry('ERROR: Не удалось подключиться к RTSP потоку. Переподключение...', 'error')
            self.send_status_update({
                'connectionStatus': 'Переподключение...',
                'alert': True
            })
            delay = self.reconnect_delay_sec
            attempt = 1
            while is_monitoring and not cap.isOpened():
                self.send_log_entry(f"INFO: Попытка переподключения #{attempt} через {delay} сек", 'warning')
                time.sleep(delay)
                try:
                    cap.release()
                except Exception:
                    pass
                cap = open_capture()
                if cap.isOpened():
                    break
                delay = self.reconnect_delay_sec
                attempt += 1
            if not is_monitoring:
                return
            if not cap.isOpened():
                self.send_log_entry('CRITICAL: Не удалось переподключиться к RTSP', 'error')
                return
        
        self.send_log_entry('Успешное подключение к RTSP потоку', 'success')
        
        frame_count = 0
        start_time = time.time()
        last_status_time = time.time()
        last_frame_time = time.time()
        last_loop_time = time.time()
        
        try:
            while is_monitoring:
                ret, frame = cap.read()
                current_time = time.time()
                # расчет времени цикла (нагрузка алгоритма по времени)
                loop_ms = (current_time - last_loop_time) * 1000.0
                last_loop_time = current_time
                self.loop_time_history.append(loop_ms)
                if len(self.loop_time_history) > 50:
                    self.loop_time_history.pop(0)
                
                if not ret:
                    self.send_log_entry('WARNING: Потерян видеопоток', 'warning')
                    host = self.extract_host()
                    if host:
                        ping_result = self.ping_camera(host)
                        if ping_result == "success":
                            self.send_log_entry('Камера доступна по ping - проблема с RTSP потоком', 'info')
                        else:
                            self.send_log_entry('CRITICAL: Камера недоступна по ping!', 'error')
                    # Переподключение к RTSP потоку с экспоненциальной задержкой
                    self.send_status_update({
                        'connectionStatus': 'Переподключение...',
                        'alert': True
                    })
                    delay = self.reconnect_delay_sec
                    attempt = 1
                    try:
                        cap.release()
                    except Exception:
                        pass
                    while is_monitoring:
                        self.send_log_entry(f"INFO: Попытка переподключения #{attempt} через {delay} сек", 'warning')
                        time.sleep(delay)
                        cap = open_capture()
                        if cap.isOpened():
                            self.send_log_entry('SUCCESS: Переподключение к RTSP выполнено', 'success')
                            self.send_status_update({
                                'connectionStatus': 'Активно',
                                'alert': False
                            })
                            break
                        delay = self.reconnect_delay_sec
                        attempt += 1
                    continue
                
                # Расчет метрик
                current_bitrate = len(frame) * 8 if frame is not None else 0
                current_fps = 1.0 / (current_time - last_frame_time) if current_time - last_frame_time > 0 else 0
                
                self.bitrate_history.append(current_bitrate)
                self.fps_history.append(current_fps)
                
                # Ограничение истории
                if len(self.bitrate_history) > self.window_size * 2:
                    self.bitrate_history.pop(0)
                if len(self.fps_history) > 20:
                    self.fps_history.pop(0)
                
                frame_count += 1
                last_frame_time = current_time
                
                # Анализ качества в расширенном режиме
                quality_metrics = {}
                quality_status = "Хорошее"
                if self.mode == 'advanced':
                    quality_metrics = self.analyze_image_quality(frame)
                    if quality_metrics.get('black_screen'):
                        quality_status = "Черный экран"
                    elif quality_metrics.get('white_screen'):
                        quality_status = "Белый экран"
                    elif quality_metrics.get('blurry'):
                        quality_status = "Размытое"
                    elif quality_metrics.get('low_contrast'):
                        quality_status = "Низкая контрастность"
                
                # Проверка проблем каждые 2 секунды
                if current_time - last_status_time >= 2:
                    bitrate_problem = self.check_bitrate_drop(current_bitrate)
                    fps_problem = self.check_fps_drop(current_fps)
                    
                    alert_triggered = False
                    
                    if bitrate_problem or fps_problem:
                        self.low_bitrate_count += 1
                        if self.low_bitrate_count >= self.max_low_bitrate_count:
                            alert_triggered = True
                            self.send_log_entry('ALERT: Проблема с качеством видео', 'warning')
                            
                            host = self.extract_host()
                            if host:
                                ping_result = self.ping_camera(host)
                                if ping_result == "success":
                                    self.send_log_entry('Камера доступна - проблема в качестве потока', 'info')
                                else:
                                    self.send_log_entry('CRITICAL: Камера недоступна по ping!', 'error')
                    else:
                        self.low_bitrate_count = max(0, self.low_bitrate_count - 1)
                    
                    # Метрики нагрузки процесса
                    try:
                        # Первый вызов cpu_percent возвращает 0, прогреваем один раз
                        if not self._primed_cpu:
                            self.process.cpu_percent(interval=None)
                            self._primed_cpu = True
                        proc_cpu = self.process.cpu_percent(interval=None)  # % за интервал с прошлого вызова
                        mem_mb = self.process.memory_info().rss / (1024 * 1024)
                        avg_loop_ms = np.mean(self.loop_time_history[-20:]) if len(self.loop_time_history) >= 5 else loop_ms
                    except Exception:
                        proc_cpu = 0.0
                        mem_mb = 0.0
                        avg_loop_ms = 0.0

                    # Отправка данных в веб-интерфейс
                    avg_bitrate = (sum(self.bitrate_history[-10:]) / min(len(self.bitrate_history), 10)) if self.bitrate_history else current_bitrate
                    avg_fps = (sum(self.fps_history[-10:]) / min(len(self.fps_history), 10)) if self.fps_history else current_fps
                    
                    status_data = {
                        'bitrate': f"{(current_bitrate/1000):.1f}",
                        'fps': f"{current_fps:.1f}",
                        'connectionStatus': 'Активно',
                        'quality': quality_status,
                        'frameCount': frame_count,
                        'avgBitrate': f"{(avg_bitrate/1000):.1f}",
                        'alert': alert_triggered,
                        'uptime': int(current_time - start_time),
                        # Доп. нагрузка алгоритма
                        'procCpuPercent': float(f"{proc_cpu:.1f}"),
                        'procMemMB': float(f"{mem_mb:.1f}"),
                        'loopMs': float(f"{loop_ms:.1f}"),
                        'avgLoopMs': float(f"{avg_loop_ms:.1f}")
                    }
                    
                    self.send_status_update(status_data)
                    last_status_time = current_time
                
                time.sleep(0.01)
                
        except Exception as e:
            self.send_log_entry(f'ERROR: {str(e)}', 'error')
        finally:
            cap.release()
            self.send_log_entry('Мониторинг остановлен', 'warning')
            self.send_status_update({
                'connectionStatus': 'Не активно',
                'alert': False
            })

# WebSocket события
@socketio.on('connect')
def handle_connect():
    print('Клиент подключился')
    emit('log_entry', {
        'message': 'Подключение к серверу установлено',
        'type': 'success',
        'time': datetime.now().strftime('%H:%M:%S')
    })
    append_log_to_file(f"[SUCCESS] {datetime.now().strftime('%H:%M:%S')} - Подключение к серверу установлено")

@socketio.on('disconnect')
def handle_disconnect():
    print('Клиент отключился')
    append_log_to_file(f"[INFO] {datetime.now().strftime('%H:%M:%S')} - Клиент отключился")

@socketio.on('start_monitoring')
def handle_start_monitoring(data):
    global monitor_thread, is_monitoring, current_mode
    
    if is_monitoring:
        emit('log_entry', {
            'message': 'Мониторинг уже запущен',
            'type': 'warning',
            'time': datetime.now().strftime('%H:%M:%S')
        })
        append_log_to_file(f"[WARNING] {datetime.now().strftime('%H:%M:%S')} - Мониторинг уже запущен")
        return
    
    mode = data.get('mode', 'basic')
    current_mode = mode
    is_monitoring = True
    
    monitor = WebCameraMonitor(current_camera_url, "cam_001", socketio, mode)
    
    # Запуск мониторинга в отдельном потоке
    monitor_thread = threading.Thread(target=monitor.monitor_stream)
    monitor_thread.daemon = True
    monitor_thread.start()
    
    emit('log_entry', {
        'message': f'Запущен {mode} мониторинг',
        'type': 'success',
        'time': datetime.now().strftime('%H:%M:%S')
    })
    append_log_to_file(f"[SUCCESS] {datetime.now().strftime('%H:%M:%S')} - Запущен {mode} мониторинг")

@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    global is_monitoring
    
    is_monitoring = False
    
    emit('log_entry', {
        'message': 'Остановка мониторинга...',
        'type': 'warning',
        'time': datetime.now().strftime('%H:%M:%S')
    })
    append_log_to_file(f"[WARNING] {datetime.now().strftime('%H:%M:%S')} - Остановка мониторинга...")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/logs')
def get_logs():
    """Получение логов из файла log.txt"""
    try:
        # Используем абсолютный путь относительно корня проекта
        import os
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'Site', 'templates', 'log.txt')
        with open(log_path, 'r', encoding='utf-8') as f:
            logs = f.read()
        return jsonify({'logs': logs})
    except FileNotFoundError:
        return jsonify({'logs': 'Файл логов не найден'})
    except Exception as e:
        return jsonify({'logs': f'Ошибка чтения логов: {str(e)}'})

if __name__ == '__main__':
    print("Запуск сервера мониторинга камер...")
    print("Откройте http://localhost:5000 в браузере")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)