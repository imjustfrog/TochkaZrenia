# camera_emulator_720p.py
import time
import random
import math
import os
from datetime import datetime
from typing import Dict, List, Optional

class TextGraphics:
    """
    Графика для текстового режима
    """
    
    @staticmethod
    def create_box(width: int, height: int, title: str = "") -> List[str]:
        """Создает текстовое окно с рамкой"""
        lines = []
        # Верхняя граница
        lines.append("┌" + "─" * (width - 2) + "┐")
        
        # Заголовок
        if title:
            title_line = f"│ {title:<{width-4}} │"
            lines.append(title_line)
            lines.append("├" + "─" * (width - 2) + "┤")
        
        # Пустые строки
        for _ in range(height - 3 - (1 if title else 0)):
            lines.append("│" + " " * (width - 2) + "│")
        
        # Нижняя граница
        lines.append("└" + "─" * (width - 2) + "┘")
        return lines
    
    @staticmethod
    def draw_meter(value: float, max_value: float = 100.0, label: str = "", width: int = 50) -> str:
        """Рисует текстовый индикатор"""
        bar_width = width - 25
        filled = int((value / max_value) * bar_width)
        bar = "[" + "█" * filled + "░" * (bar_width - filled) + "]"
        return f"{label:<15} {bar} {value:>6.1f}"

class NetworkEffects:
    """
    Сетевые эффекты
    """
    
    @staticmethod
    def apply_network_effects(packet_loss_rate: float, latency_ms: float, jitter_ms: float, freeze_probability: float) -> Dict:
        """Применение сетевых эффектов"""
        effects = {
            'packet_lost': False,
            'actual_latency': 0.0,
            'freeze_occurred': False,
            'frame_skipped': False
        }
        
        # Эмуляция потерь пакетов
        if random.random() < packet_loss_rate:
            effects['packet_lost'] = True
            return effects
        
        # Эмуляция задержки
        effects['actual_latency'] = latency_ms + random.uniform(-jitter_ms, jitter_ms)
        time.sleep(max(0, effects['actual_latency']) / 1000.0)
        
        # Эмуляция пропуска кадра
        if random.random() < packet_loss_rate * 2:
            effects['frame_skipped'] = True
        
        # Эмуляция фриза
        if random.random() < freeze_probability:
            freeze_time = random.uniform(0.05, 0.5)
            time.sleep(freeze_time)
            effects['freeze_occurred'] = True
        
        return effects

class CameraEmulator720p:
    """
    Эмулятор камеры 1280×720 @ 25FPS
    """
    
    def __init__(self, actual_width: int = 1280, actual_height: int = 720, target_fps: int = 25,
                 text_width: int = 80, text_height: int = 24):
        
        # Реальное разрешение камеры
        self.actual_width = actual_width
        self.actual_height = actual_height
        self.target_fps = target_fps
        
        # Текстовое разрешение
        self.text_width = min(text_width, 100)
        self.text_height = min(text_height, 30)
        
        self.is_running = False
        self.frame_count = 0
        self.start_time = 0
        
        # Параметры сети для 720p
        self.network_params = {
            'packet_loss': 0.001,           # 0.1%
            'latency_ms': 15.0,             # milliseconds
            'jitter_ms': 3.0,               # milliseconds
            'freeze_probability': 0.001,    # 0.1%
            'bitrate_kbps': 2500,           # kilobits per second (рекомендовано для 720p)
        }
        
        # Статистика
        self.stats = {
            'frames_generated': 0,
            'frames_displayed': 0,
            'frames_lost': 0,
            'frames_skipped': 0,
            'total_latency': 0.0,
            'freezes_detected': 0,
            'start_time': 0,
            'min_fps': float('inf'),
            'max_fps': 0,
        }
        
        self.current_pattern = "stream_info"
        self.patterns = ["stream_info", "network_monitor", "quality_meter", "simple_visual"]
        
        print("🎥 Эмулятор камеры 1280×720 инициализирован")
        print(f"📏 Разрешение: {actual_width}×{actual_height}")
        print(f"🎞️  Целевой FPS: {target_fps}")
        print(f"🔍 Текстовый масштаб: {text_width}×{text_height}")
    
    def set_network_parameters(self, 
                             packet_loss: float = 0.1,
                             latency_ms: float = 15.0,
                             jitter_ms: float = 3.0,
                             freeze_probability: float = 0.1,
                             bitrate_kbps: float = 2500):
        """
        Настройка параметров сети для 720p
        """
        self.network_params = {
            'packet_loss': max(0.0, min(5.0, packet_loss)) / 100.0,
            'latency_ms': max(0.0, latency_ms),
            'jitter_ms': max(0.0, jitter_ms),
            'freeze_probability': max(0.0, min(5.0, freeze_probability)) / 100.0,
            'bitrate_kbps': max(500, bitrate_kbps),
        }
        
        print("\n🔧 Параметры сети установлены:")
        print(f"   📉 Потери пакетов: {packet_loss}%")
        print(f"   ⏱️  Задержка: {latency_ms}ms")
        print(f"   📏 Джиттер: {jitter_ms}ms")
        print(f"   ❄️  Вероятность фриза: {freeze_probability}%")
        print(f"   📊 Битрейт: {bitrate_kbps} kbps")
        
        # Рекомендации для 720p
        recommended = self._get_recommended_bitrate()
        if bitrate_kbps < recommended['min']:
            print(f"   ⚠️  Низкий битрейт! Рекомендуется: {recommended['min']}-{recommended['max']} kbps")
        elif bitrate_kbps > recommended['max']:
            print(f"   💡 Высокий битрейт! Оптимально: {recommended['optimal']} kbps")
        else:
            print(f"   ✅ Битрейт в норме. Рекомендация: {recommended['optimal']} kbps")
    
    def _get_recommended_bitrate(self) -> Dict:
        """Рекомендованные битрейты для 720p"""
        return {
            'min': 1500,
            'optimal': 2500,
            'max': 4000
        }
    
    def set_display_pattern(self, pattern: str):
        """Установка паттерна отображения"""
        if pattern in self.patterns:
            self.current_pattern = pattern
            print(f"🎨 Установлен паттерн: {pattern}")
        else:
            print(f"❌ Неизвестный паттерн. Доступные: {', '.join(self.patterns)}")
    
    def _clear_screen(self):
        """Очистка экрана"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _generate_stream_info_frame(self) -> List[str]:
        """Генерация кадра с информацией о потоке"""
        lines = TextGraphics.create_box(self.text_width, self.text_height, 
                                      "🎥 720p VIDEO STREAM")
        
        # Расчет качества
        quality_score = self._calculate_quality_score()
        
        # Основная информация
        info_lines = [
            f"Frame: {self.frame_count:06d}",
            f"Time: {datetime.now().strftime('%H:%M:%S')}",
            f"Resolution: {self.actual_width}×{self.actual_height}",
            f"FPS: {self.target_fps}",
            f"Pattern: {self.current_pattern}",
            "",
            "📊 СЕТЕВЫЕ ПАРАМЕТРЫ:",
            f"  Bitrate:     {self.network_params['bitrate_kbps']:5d} kbps",
            f"  Packet Loss: {self.network_params['packet_loss']*100:5.2f}%",
            f"  Latency:     {self.network_params['latency_ms']:5.1f}ms",
            f"  Jitter:     ±{self.network_params['jitter_ms']:4.1f}ms",
            f"  Freeze Prob: {self.network_params['freeze_probability']*100:5.2f}%",
            "",
            "🎯 КАЧЕСТВО ПОТОКА:",
            f"  Score: {quality_score:.1f}/100",
            f"  Status: {self._get_quality_status(quality_score)}",
        ]
        
        # Заполняем информацией
        for i, info in enumerate(info_lines):
            if i + 2 < len(lines):
                lines[i + 2] = f"│ {info:<{self.text_width-4}} │"
        
        # Анимированный элемент
        anim_pos = (self.frame_count * 2) % (self.text_width - 10)
        anim_line = "  " + " " * anim_pos + "███" + " " * (self.text_width - anim_pos - 15)
        if len(lines) > self.text_height - 2:
            lines[self.text_height - 2] = f"│{anim_line}│"
        
        return lines
    
    def _generate_network_monitor_frame(self) -> List[str]:
        """Мониторинг сетевых параметров"""
        lines = TextGraphics.create_box(self.text_width, self.text_height, 
                                      "📊 NETWORK MONITOR")
        
        # Расчет качества
        quality_score = self._calculate_quality_score()
        
        # Индикаторы
        indicators = [
            TextGraphics.draw_meter(self.network_params['bitrate_kbps'], 5000, "Bitrate", self.text_width - 4),
            TextGraphics.draw_meter(self.network_params['packet_loss'] * 100, 5, "Packet Loss", self.text_width - 4),
            TextGraphics.draw_meter(self.network_params['latency_ms'], 100, "Latency", self.text_width - 4),
            TextGraphics.draw_meter(self.network_params['jitter_ms'], 20, "Jitter", self.text_width - 4),
            TextGraphics.draw_meter(quality_score, 100, "Quality", self.text_width - 4),
        ]
        
        # Заполняем индикаторами
        for i, indicator in enumerate(indicators):
            if i + 2 < len(lines):
                lines[i + 2] = f"│ {indicator} │"
        
        # Простой график качества
        if len(lines) > self.text_height - 3:
            graph_line = "│ "
            for i in range(self.text_width - 4):
                time_point = (self.frame_count + i) * 0.1
                value = 50 + 40 * math.sin(time_point * 0.3)
                graph_line += "█" if value > 70 else "░"
            graph_line += " │"
            lines[self.text_height - 3] = graph_line
        
        # Статус
        status = self._get_quality_status(quality_score)
        status_line = f"Status: {status} | Frame: {self.frame_count}"
        if len(lines) > self.text_height - 2:
            lines[self.text_height - 2] = f"│ {status_line:<{self.text_width-4}} │"
        
        return lines
    
    def _generate_quality_meter_frame(self) -> List[str]:
        """Измеритель качества потока"""
        lines = TextGraphics.create_box(self.text_width, self.text_height, 
                                      "🎯 QUALITY METER")
        
        # Расчет метрик качества
        quality_score = self._calculate_quality_score()
        stability_score = self._calculate_stability_score()
        
        # Индикаторы
        indicators = [
            TextGraphics.draw_meter(quality_score, 100, "Overall", self.text_width - 4),
            TextGraphics.draw_meter(stability_score, 100, "Stability", self.text_width - 4),
            TextGraphics.draw_meter(100 - self.network_params['packet_loss'] * 1000, 100, "Reliability", self.text_width - 4),
            TextGraphics.draw_meter(max(0, 100 - self.network_params['latency_ms']), 100, "Latency", self.text_width - 4),
        ]
        
        # Заполняем индикаторами
        for i, indicator in enumerate(indicators):
            if i + 2 < len(lines):
                lines[i + 2] = f"│ {indicator} │"
        
        # Визуализация параметров
        if len(lines) > self.text_height - 4:
            params_info = [
                f"Packet Loss: {self.network_params['packet_loss']*100:.2f}%",
                f"Latency: {self.network_params['latency_ms']:.1f}ms",
                f"Jitter: ±{self.network_params['jitter_ms']:.1f}ms",
                f"Freeze Risk: {self.network_params['freeze_probability']*100:.2f}%",
            ]
            
            for i, param in enumerate(params_info):
                line_idx = self.text_height - 6 + i
                if line_idx < len(lines):
                    lines[line_idx] = f"│ {param:<{self.text_width-4}} │"
        
        return lines
    
    def _generate_simple_visual_frame(self) -> List[str]:
        """Простая визуализация видеопотока"""
        lines = TextGraphics.create_box(self.text_width, self.text_height, 
                                      "🔲 720p VIDEO PREVIEW")
        
        # Создаем простую анимацию
        for row in range(2, self.text_height - 1):
            if row < len(lines):
                visual_line = ""
                for col in range(1, self.text_width - 1):
                    # Создаем движущийся паттерн
                    x = col / (self.text_width - 2)
                    y = row / (self.text_height - 2)
                    
                    time_val = self.frame_count * 0.2
                    pattern1 = math.sin(x * 10 + time_val) * 0.5
                    pattern2 = math.cos(y * 8 + time_val * 1.3) * 0.3
                    pattern3 = math.sin((x + y) * 15 + time_val * 0.7) * 0.2
                    
                    combined = pattern1 + pattern2 + pattern3
                    
                    if combined > 0.6:
                        visual_line += "█"
                    elif combined > 0.2:
                        visual_line += "▓"
                    elif combined > -0.2:
                        visual_line += "▒"
                    elif combined > -0.6:
                        visual_line += "░"
                    else:
                        visual_line += " "
                
                lines[row] = f"│{visual_line}│"
        
        # Информация
        info_line = f"1280×720 @ 25FPS | Frame: {self.frame_count} | Bitrate: {self.network_params['bitrate_kbps']}kbps"
        if len(lines) > self.text_height - 2:
            lines[self.text_height - 2] = f"│ {info_line:<{self.text_width-4}} │"
        
        return lines
    
    def _calculate_quality_score(self) -> float:
        """Расчет общего показателя качества для 720p"""
        # Штрафы за плохие параметры
        loss_penalty = self.network_params['packet_loss'] * 800  # 1% потерь = -8 пунктов
        latency_penalty = min(25, self.network_params['latency_ms'] / 4)  # 40ms = -10 пунктов
        jitter_penalty = self.network_params['jitter_ms'] * 2.5  # 4ms jitter = -10 пунктов
        freeze_penalty = self.network_params['freeze_probability'] * 400  # 1% фризов = -4 пунктов
        
        # Бонус за хороший битрейт (для 720p)
        bitrate_bonus = min(15, (self.network_params['bitrate_kbps'] - 1000) / 100)  # 2500kbps = +15 пунктов
        
        quality = 100 - loss_penalty - latency_penalty - jitter_penalty - freeze_penalty + bitrate_bonus
        return max(0, min(100, quality))
    
    def _calculate_stability_score(self) -> float:
        """Расчет стабильности потока"""
        stability = 100
        stability -= self.network_params['jitter_ms'] * 4  # Штраф за джиттер
        stability -= self.network_params['freeze_probability'] * 200  # Штраф за фризы
        stability -= self.network_params['packet_loss'] * 300  # Штраф за потери
        return max(0, min(100, stability))
    
    def _get_quality_status(self, score: float) -> str:
        """Получение текстового статуса качества"""
        if score >= 85:
            return "💎 ОТЛИЧНО"
        elif score >= 70:
            return "✅ ХОРОШО"
        elif score >= 55:
            return "⚠️  НОРМА"
        elif score >= 40:
            return "❌ ПЛОХО"
        else:
            return "💀 КРИТИЧЕСКИ"
    
    def generate_frame(self) -> Optional[List[str]]:
        """Генерация кадра с применением сетевых эффектов"""
        
        # Применяем эффекты сети
        effects = NetworkEffects.apply_network_effects(
            self.network_params['packet_loss'],
            self.network_params['latency_ms'], 
            self.network_params['jitter_ms'],
            self.network_params['freeze_probability']
        )
        
        if effects['packet_lost']:
            self.stats['frames_lost'] += 1
            return None
        
        if effects['frame_skipped']:
            self.stats['frames_skipped'] += 1
        
        self.stats['total_latency'] += effects['actual_latency']
        
        if effects['freeze_occurred']:
            self.stats['freezes_detected'] += 1
        
        # Генерация кадра
        if self.current_pattern == "stream_info":
            return self._generate_stream_info_frame()
        elif self.current_pattern == "network_monitor":
            return self._generate_network_monitor_frame()
        elif self.current_pattern == "quality_meter":
            return self._generate_quality_meter_frame()
        elif self.current_pattern == "simple_visual":
            return self._generate_simple_visual_frame()
        
        return self._generate_stream_info_frame()
    
    def display_frame(self, frame: List[str]):
        """Отображение кадра"""
        self._clear_screen()
        for line in frame:
            print(line)
    
    def get_statistics(self) -> Dict:
        """Получение статистики"""
        if self.stats['frames_displayed'] == 0:
            return self.stats
        
        elapsed = time.time() - self.stats['start_time']
        current_fps = self.stats['frames_displayed'] / elapsed
        
        # Обновляем min/max FPS
        self.stats['min_fps'] = min(self.stats['min_fps'], current_fps)
        self.stats['max_fps'] = max(self.stats['max_fps'], current_fps)
        
        quality_score = self._calculate_quality_score()
        
        return {
            'total_frames': self.stats['frames_generated'],
            'frames_displayed': self.stats['frames_displayed'],
            'frames_lost': self.stats['frames_lost'],
            'packet_loss_rate': (self.stats['frames_lost'] / self.stats['frames_generated']) * 100 if self.stats['frames_generated'] > 0 else 0,
            'avg_latency': self.stats['total_latency'] / self.stats['frames_displayed'] if self.stats['frames_displayed'] > 0 else 0,
            'freezes_detected': self.stats['freezes_detected'],
            'current_fps': current_fps,
            'min_fps': self.stats['min_fps'],
            'max_fps': self.stats['max_fps'],
            'fps_stability': (current_fps / self.target_fps) * 100,
            'quality_score': quality_score,
            'quality_status': self._get_quality_status(quality_score),
            'elapsed_time': elapsed
        }
    
    def start_stream(self, duration: int = 30):
        """Запуск видеопотока"""
        if self.is_running:
            print("⚠️  Поток уже запущен")
            return
        
        self.is_running = True
        self.frame_count = 0
        self.stats = {
            'frames_generated': 0,
            'frames_displayed': 0,
            'frames_lost': 0,
            'frames_skipped': 0,
            'total_latency': 0.0,
            'freezes_detected': 0,
            'start_time': time.time(),
            'min_fps': float('inf'),
            'max_fps': 0,
        }
        
        print(f"\n🎥 Запуск потока 1280×720 @ {self.target_fps}FPS")
        print(f"⏱️  Длительность: {duration} секунд")
        print("⏹️  Для остановки нажмите Ctrl+C")
        time.sleep(1)
        
        end_time = time.time() + duration
        
        try:
            while self.is_running and time.time() < end_time:
                frame_start = time.time()
                self.stats['frames_generated'] += 1
                
                # Генерируем и отображаем кадр
                frame = self.generate_frame()
                if frame is not None:
                    self.display_frame(frame)
                    self.stats['frames_displayed'] += 1
                    self.frame_count += 1
                
                # Поддержание FPS
                frame_time = time.time() - frame_start
                target_frame_time = 1.0 / self.target_fps
                sleep_time = max(0, target_frame_time - frame_time)
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n🛑 Остановка по запросу пользователя")
        finally:
            self.is_running = False
            self._show_stats()
    
    def _show_stats(self):
        """Показать статистику"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 50)
        print("📊 СТАТИСТИКА ПОТОКА 720p")
        print("=" * 50)
        print(f"🎯 Всего кадров: {stats['total_frames']}")
        print(f"✅ Отображено: {stats['frames_displayed']}")
        print(f"❌ Потеряно: {stats['frames_lost']}")
        print(f"📉 Потери: {stats['packet_loss_rate']:.2f}%")
        print(f"⏱️  Задержка: {stats['avg_latency']:.2f}ms")
        print(f"❄️  Фризов: {stats['freezes_detected']}")
        print(f"🎞️  FPS: {stats['current_fps']:.2f}")
        print(f"📈 Min/Max FPS: {stats['min_fps']:.2f}/{stats['max_fps']:.2f}")
        print(f"🎯 Качество: {stats['quality_score']:.1f}/100")
        print(f"🏆 Статус: {stats['quality_status']}")
        print("=" * 50)

def main():
    """Главная функция"""
    emulator = CameraEmulator720p(
        actual_width=1280,
        actual_height=720, 
        target_fps=25,
        text_width=80,
        text_height=24
    )
    
    while True:
        print("\n" + "=" * 50)
        print("🎥 ЭМУЛЯТОР КАМЕРЫ 1280×720 @ 25FPS")
        print("=" * 50)
        print("1. 🚀 Быстрый старт")
        print("2. ⚙️  Настроить параметры")
        print("3. 🎨 Выбрать отображение") 
        print("4. 📊 Запустить поток")
        print("5. 🚪 Выход")
        
        choice = input("\nВыберите действие (1-5): ").strip()
        
        if choice == '1':
            # Быстрый старт с параметрами для 720p
            emulator.set_network_parameters(
                packet_loss=0.1,
                latency_ms=15,
                jitter_ms=4,
                freeze_probability=0.05,
                bitrate_kbps=2500
            )
            emulator.set_display_pattern("stream_info")
            emulator.start_stream(20)
            
        elif choice == '2':
            # Настройка параметров
            print("\n⚙️  НАСТРОЙКА ПАРАМЕТРОВ ДЛЯ 720p")
            print("(оставьте пустым для значений по умолчанию)")
            
            packet_loss = input("Потери пакетов % [0.1]: ") or "0.1"
            latency_ms = input("Задержка (ms) [15.0]: ") or "15.0"
            jitter_ms = input("Джиттер (ms) [4.0]: ") or "4.0"
            freeze_prob = input("Вероятность фриза % [0.05]: ") or "0.05"
            bitrate = input("Битрейт (kbps) [2500]: ") or "2500"
            
            emulator.set_network_parameters(
                packet_loss=float(packet_loss),
                latency_ms=float(latency_ms),
                jitter_ms=float(jitter_ms),
                freeze_probability=float(freeze_prob),
                bitrate_kbps=float(bitrate)
            )
            
        elif choice == '3':
            # Выбор паттерна
            print("\n🎨 ВЫБЕРИТЕ ОТОБРАЖЕНИЕ:")
            for i, pattern in enumerate(emulator.patterns, 1):
                print(f"{i}. {pattern}")
            
            pattern_choice = input(f"Выберите (1-{len(emulator.patterns)}): ").strip()
            if pattern_choice.isdigit() and 1 <= int(pattern_choice) <= len(emulator.patterns):
                emulator.set_display_pattern(emulator.patterns[int(pattern_choice) - 1])
            else:
                print("❌ Неверный выбор")
                
        elif choice == '4':
            # Запуск потока
            duration = input("Длительность (секунд) [20]: ") or "20"
            emulator.start_stream(int(duration))
            
        elif choice == '5':
            print("👋 Выход")
            break
            
        else:
            print("❌ Неверный выбор")

if __name__ == "__main__":
    main()