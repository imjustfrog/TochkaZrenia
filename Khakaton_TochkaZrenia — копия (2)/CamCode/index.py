import cv2
import time
import numpy as np
from datetime import datetime
import subprocess
import platform
import logging
import sys

class TeeLogger:
    def __init__(self, filename):
        self.file = open(filename, 'a', encoding='utf-8')
        self.console = sys.stdout

    def write(self, message):
        self.file.write(message)
        self.file.flush()
        self.console.write(message)

    def flush(self):
        self.file.flush()
        self.console.flush()

sys.stdout = TeeLogger("Site/templates/log.txt")
sys.stderr = sys.stdout


class BasicCameraMonitor:
    def __init__(self, rtsp_url, camera_id="cam_1"):
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.bitrate_history = []
        self.fps_history = []
        self.window_size = 30
        self.threshold_ratio = 0.3
        self.low_bitrate_count = 0
        self.max_low_bitrate_count = 3
        self.last_ping_time = 0
        self.ping_cooldown = 60
        
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
        """Пинг камеры ТОЛЬКО при проблемах"""
        current_time = time.time()
        if current_time - self.last_ping_time < self.ping_cooldown:
            return "cooldown"
        
        self.last_ping_time = current_time
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", host]
        
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            return "success" if result.returncode == 0 else "failed"
        except:
            return "error"
    
    def check_bitrate_drop(self, current_bitrate):
        """Проверка падения битрейта"""
        if len(self.bitrate_history) < self.window_size:
            return False
        avg_bitrate = np.mean(self.bitrate_history[-self.window_size:])
        return current_bitrate < avg_bitrate * self.threshold_ratio and avg_bitrate > 1000
    
    def check_fps_drop(self, current_fps):
        """Проверка падения FPS"""
        if len(self.fps_history) < 10:
            return False
        avg_fps = np.mean(self.fps_history[-10:])
        return current_fps < 5 or (avg_fps > 10 and current_fps < avg_fps * 0.2)
    
    def monitor(self):
        """Основной мониторинг - пинг только при проблемах"""
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            print(f"[{self.camera_id}] ERROR: Не удалось подключиться к RTSP потоку")
            return
        
        print(f"[{self.camera_id}] Мониторинг запущен")
        print("[INFO] Нажмите Ctrl+C для остановки\n")
        
        frame_count = 0
        start_time = time.time()
        last_status_time = time.time()
        last_frame_time = time.time()
        
        try:
            while True:
                ret, frame = cap.read()
                current_time = time.time()
                
                if not ret:
                    print(f"[{self.camera_id}] WARNING: {datetime.now().strftime('%H:%M:%S')} - Потерян видеопоток")
                    host = self.extract_host()
                    if host:
                        ping_result = self.ping_camera(host)
                        if ping_result == "success":
                            print(f"[{self.camera_id}] INFO: Камера доступна по ping - проблема с RTSP потоком")
                        elif ping_result == "cooldown":
                            print(f"[{self.camera_id}] INFO: Пинг пропущен (cooldown)")
                        else:
                            print(f"[{self.camera_id}] CRITICAL: Камера недоступна по ping!")
                    time.sleep(5)
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
                
                # Проверка проблем каждые 10 секунд
                if current_time - last_status_time >= 10:
                    bitrate_problem = self.check_bitrate_drop(current_bitrate)
                    fps_problem = self.check_fps_drop(current_fps)
                    
                    status = "NORMAL"
                    alert_triggered = False
                    
                    if bitrate_problem or fps_problem:
                        self.low_bitrate_count += 1
                        if self.low_bitrate_count >= self.max_low_bitrate_count:
                            alert_triggered = True
                            status = "PROBLEM"
                            print(f"[{self.camera_id}] ALERT: {datetime.now().strftime('%H:%M:%S')} - Проблема с качеством видео")
                            
                            host = self.extract_host()
                            if host:
                                ping_result = self.ping_camera(host)
                                if ping_result == "success":
                                    print(f"[{self.camera_id}] INFO: Камера доступна - проблема в качестве потока")
                                elif ping_result == "cooldown":
                                    print(f"[{self.camera_id}] INFO: Пинг пропущен (cooldown)")
                                else:
                                    print(f"[{self.camera_id}] CRITICAL: Камера недоступна по ping!")
                    else:
                        self.low_bitrate_count = max(0, self.low_bitrate_count - 1)
                    
                    # Вывод статуса
                    avg_bitrate = np.mean(self.bitrate_history[-10:]) if len(self.bitrate_history) >= 10 else current_bitrate
                    avg_fps = np.mean(self.fps_history[-10:]) if len(self.fps_history) >= 10 else current_fps
                    
                    print(f"[{self.camera_id}] STATUS: {datetime.now().strftime('%H:%M:%S')} - "
                          f"Битрейт: {current_bitrate/1000:.1f}kbps (avg: {avg_bitrate/1000:.1f}kbps) | "
                          f"FPS: {current_fps:.1f} (avg: {avg_fps:.1f}) | {status}")
                    
                    last_status_time = current_time
                
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            print(f"\n[{self.camera_id}] INFO: Мониторинг остановлен пользователем")
        except Exception as e:
            print(f"[{self.camera_id}] ERROR: {str(e)}")
        finally:
            cap.release()
            cv2.destroyAllWindows()


class AdvancedCameraMonitor(BasicCameraMonitor):
    def __init__(self, rtsp_url, camera_id="cam_1"):
        super().__init__(rtsp_url, camera_id)
        self.quality_history = []
        self.freeze_detector = []  # Для детекции замороженного изображения
        self.last_frame_hash = None
        
    def analyze_image_quality(self, frame):
        """Анализ качества изображения"""
        quality_metrics = {}
        
        if frame is None:
            return quality_metrics
        
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 1. Детекция черного/белого экрана
            mean_brightness = np.mean(gray)
            quality_metrics['brightness'] = mean_brightness
            if mean_brightness < 10:
                quality_metrics['black_screen'] = True
            elif mean_brightness > 240:
                quality_metrics['white_screen'] = True
            
            # 2. Анализ резкости (вариация Лапласа)
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            quality_metrics['sharpness'] = laplacian_var
            quality_metrics['blurry'] = laplacian_var < 50  # Порог для размытости
            
            # 3. Детекция замороженного изображения
            current_hash = hash(gray.tobytes())
            if self.last_frame_hash == current_hash:
                self.freeze_detector.append(True)
            else:
                self.freeze_detector.append(False)
            
            self.last_frame_hash = current_hash
            if len(self.freeze_detector) > 30:
                self.freeze_detector.pop(0)
            
            # Если 10 из последних 30 кадров идентичны - заморозка
            if sum(self.freeze_detector) > 10:
                quality_metrics['frozen'] = True
            
            # 4. Анализ контраста
            contrast = np.std(gray)
            quality_metrics['contrast'] = contrast
            quality_metrics['low_contrast'] = contrast < 20
            
        except Exception as e:
            print(f"[{self.camera_id}] WARNING: Ошибка анализа изображения: {e}")
            
        return quality_metrics
    
    def detect_problems(self, quality_metrics):
        """Определение конкретных проблем"""
        problems = []
        
        if quality_metrics.get('black_screen'):
            problems.append("Черный экран")
        if quality_metrics.get('white_screen'):
            problems.append("Белый экран") 
        if quality_metrics.get('blurry'):
            problems.append("Размытое изображение")
        if quality_metrics.get('frozen'):
            problems.append("Замороженное изображение")
        if quality_metrics.get('low_contrast'):
            problems.append("Низкая контрастность")
            
        return problems
    
    def monitor(self):
        """Расширенный мониторинг с анализом качества"""
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            print(f"[{self.camera_id}] ERROR: Не удалось подключиться к RTSP потоку")
            return
        
        print(f"[{self.camera_id}] Расширенный мониторинг запущен")
        print("[INFO] Нажмите Ctrl+C для остановки\n")
        
        frame_count = 0
        start_time = time.time()
        last_status_time = time.time()
        last_frame_time = time.time()
        last_quality_check = time.time()
        
        try:
            while True:
                ret, frame = cap.read()
                current_time = time.time()
                
                if not ret:
                    print(f"[{self.camera_id}] WARNING: {datetime.now().strftime('%H:%M:%S')} - Потерян видеопоток")
                    host = self.extract_host()
                    if host:
                        ping_result = self.ping_camera(host)
                        if ping_result == "success":
                            print(f"[{self.camera_id}] INFO: Камера доступна по ping - проблема с RTSP потоком")
                        elif ping_result == "cooldown":
                            print(f"[{self.camera_id}] INFO: Пинг пропущен (cooldown)")
                        else:
                            print(f"[{self.camera_id}] CRITICAL: Камера недоступна по ping!")
                    time.sleep(5)
                    continue
                
                # Расчет базовых метрик
                current_bitrate = len(frame) * 8 if frame is not None else 0
                current_fps = 1.0 / (current_time - last_frame_time) if current_time - last_frame_time > 0 else 0
                
                self.bitrate_history.append(current_bitrate)
                self.fps_history.append(current_fps)
                
                # Анализ качества изображения каждые 5 секунд
                if current_time - last_quality_check >= 5:
                    quality_metrics = self.analyze_image_quality(frame)
                    problems = self.detect_problems(quality_metrics)
                    
                    if problems:
                        print(f"[{self.camera_id}] QUALITY ISSUES: {datetime.now().strftime('%H:%M:%S')} - {', '.join(problems)}")
                        # При проблемах с качеством тоже проверяем пинг
                        host = self.extract_host()
                        if host:
                            ping_result = self.ping_camera(host)
                            if ping_result != "success" and ping_result != "cooldown":
                                print(f"[{self.camera_id}] CRITICAL: Камера недоступна при проблемах с качеством")
                    
                    last_quality_check = current_time
                
                # Ограничение истории
                if len(self.bitrate_history) > self.window_size * 2:
                    self.bitrate_history.pop(0)
                if len(self.fps_history) > 20:
                    self.fps_history.pop(0)
                
                frame_count += 1
                last_frame_time = current_time
                
                # Проверка проблем с битрейтом/FPS
                if current_time - last_status_time >= 10:
                    bitrate_problem = self.check_bitrate_drop(current_bitrate)
                    fps_problem = self.check_fps_drop(current_fps)
                    
                    status = "NORMAL"
                    alert_triggered = False
                    
                    if bitrate_problem or fps_problem:
                        self.low_bitrate_count += 1
                        if self.low_bitrate_count >= self.max_low_bitrate_count:
                            alert_triggered = True
                            status = "PROBLEM"
                            print(f"[{self.camera_id}] ALERT: {datetime.now().strftime('%H:%M:%S')} - Проблема с битрейтом/FPS")
                            
                            host = self.extract_host()
                            if host:
                                ping_result = self.ping_camera(host)
                                if ping_result == "success":
                                    print(f"[{self.camera_id}] INFO: Камера доступна - проблема в качестве потока")
                                elif ping_result == "cooldown":
                                    print(f"[{self.camera_id}] INFO: Пинг пропущен (cooldown)")
                                else:
                                    print(f"[{self.camera_id}] CRITICAL: Камера недоступна по ping!")
                    else:
                        self.low_bitrate_count = max(0, self.low_bitrate_count - 1)
                    
                    # Вывод статуса
                    avg_bitrate = np.mean(self.bitrate_history[-10:]) if len(self.bitrate_history) >= 10 else current_bitrate
                    avg_fps = np.mean(self.fps_history[-10:]) if len(self.fps_history) >= 10 else current_fps
                    
                    quality_info = ""
                    if hasattr(self, 'last_quality_metrics'):
                        quality_info = f" | Резкость: {self.last_quality_metrics.get('sharpness', 0):.1f}"
                    
                    print(f"[{self.camera_id}] STATUS: {datetime.now().strftime('%H:%M:%S')} - "
                          f"Битрейт: {current_bitrate/1000:.1f}kbps | "
                          f"FPS: {current_fps:.1f} | {status}{quality_info}")
                    
                    last_status_time = current_time
                
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            print(f"\n[{self.camera_id}] INFO: Мониторинг остановлен пользователем")
        except Exception as e:
            print(f"[{self.camera_id}] ERROR: {str(e)}")
        finally:
            cap.release()
            cv2.destroyAllWindows()


# Использование
if __name__ == "__main__":
    RTSP_URL = "rtsp://ins046msc:wQpQk35t@85.141.77.197:7554/ISAPI/Streaming/Channels/103"
    
    print("=== Мониторинг камер видеонаблюдения ===")
    print("1 - Базовая версия (только битрейт/FPS)")
    print("2 - Расширенная версия (с анализом качества изображения)")
    
    choice = input("Выберите версию (1 или 2): ").strip()
    
    if choice == "2":
        print("\nЗапуск расширенной версии с анализом качества...")
        monitor = AdvancedCameraMonitor(RTSP_URL, "cam_001")
    else:
        print("\nЗапуск базовой версии...")
        monitor = BasicCameraMonitor(RTSP_URL, "cam_001")
    
    monitor.monitor()

    