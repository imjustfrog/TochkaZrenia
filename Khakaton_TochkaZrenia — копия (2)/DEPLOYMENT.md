# 🚀 Инструкция по развертыванию

## 📋 Подготовка к загрузке в Git

### 1. Очистка проекта

Перед загрузкой в Git необходимо удалить большие файлы:

```bash
# Удаляем папку OpenCV (слишком большая для Git)
rm -rf CamCode/opencv/

# Удаляем логи (будут созданы автоматически)
rm -f Site/templates/log.txt
```

### 2. Создание Git репозитория

```bash
# Инициализация Git
git init

# Добавление файлов
git add .

# Первый коммит
git commit -m "Initial commit: Camera monitoring system"

# Добавление удаленного репозитория
git remote add origin <URL_ВАШЕГО_РЕПОЗИТОРИЯ>

# Загрузка в репозиторий
git push -u origin main
```

## 🛠️ Установка на новом сервере

### 1. Клонирование репозитория

```bash
git clone <URL_ВАШЕГО_РЕПОЗИТОРИЯ>
cd Khakaton_TochkaZrenia
```

### 2. Установка зависимостей

```bash
# Установка Python зависимостей
pip install -r requirements.txt

# Или установка OpenCV отдельно (если нужно)
pip install opencv-python
```

### 3. Запуск системы

```bash
# Запуск веб-сервера
python CamCode/server.py
```

## 📁 Структура для Git

```
Khakaton_TochkaZrenia/
├── .gitignore                 # Исключения для Git
├── requirements.txt           # Python зависимости
├── README.md                  # Основная документация
├── QUICK_START.md            # Быстрый старт
├── DEPLOYMENT.md             # Инструкция по развертыванию
├── CamCode/
│   ├── index.py              # Основной скрипт мониторинга
│   └── server.py             # Flask сервер
└── Site/
    ├── templates/
    │   └── index.html        # Веб-интерфейс
    └── static/
        ├── app.js           # JavaScript
        └── styles.css        # Стили
```

## ⚠️ Важные замечания

### Файлы, которые НЕ попадут в Git:

- `CamCode/opencv/` - папка OpenCV (слишком большая)
- `Site/templates/log.txt` - файл логов (создается автоматически)
- `__pycache__/` - кэш Python
- `.env` - переменные окружения
- Большие медиафайлы

### Что нужно сделать после клонирования:

1. **Установить OpenCV** (если не установлен):
   ```bash
   pip install opencv-python
   ```

2. **Создать файл логов**:
   ```bash
   touch Site/templates/log.txt
   ```

3. **Настроить RTSP URL** в файлах:
   - `CamCode/index.py`
   - `CamCode/server.py`

## 🔧 Настройка для продакшена

### 1. Переменные окружения

Создайте файл `.env`:

```env
RTSP_URL=rtsp://username:password@ip:port/path
FLASK_ENV=production
SECRET_KEY=your-secret-key
```

### 2. Настройка веб-сервера

Для продакшена рекомендуется использовать:

- **Nginx** + **Gunicorn**
- **Apache** + **mod_wsgi**
- **Docker** контейнер

### 3. Мониторинг

- Настройте **systemd** для автозапуска
- Добавьте **логирование** в системные логи
- Настройте **мониторинг** процесса

## 🐳 Docker развертывание

Создайте `Dockerfile`:

```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "CamCode/server.py"]
```

Запуск:

```bash
docker build -t camera-monitor .
docker run -p 5000:5000 camera-monitor
```

## 📊 Мониторинг производительности

### Логи системы

```bash
# Просмотр логов в реальном времени
tail -f Site/templates/log.txt

# Просмотр логов сервера
journalctl -u camera-monitor -f
```

### Проверка состояния

```bash
# Проверка портов
netstat -tlnp | grep :5000

# Проверка процессов
ps aux | grep python
```

## 🔒 Безопасность

1. **Измените SECRET_KEY** в `server.py`
2. **Настройте HTTPS** для продакшена
3. **Ограничьте доступ** по IP
4. **Используйте VPN** для доступа к камерам
5. **Регулярно обновляйте** зависимости

## 📞 Поддержка

При проблемах с развертыванием:

1. Проверьте логи: `tail -f Site/templates/log.txt`
2. Проверьте зависимости: `pip list`
3. Проверьте порты: `netstat -tlnp | grep :5000`
4. Проверьте права доступа к файлам

---

**🎉 Готово! Теперь ваша система готова к развертыванию!**
