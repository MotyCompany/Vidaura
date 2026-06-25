# Vidaura
**Видеохостинг от MotyCo · 2026**

## Требования
- **Python 3.11 или 3.12** (3.13+ не поддерживается FastAPI на данный момент)

## Установка

```bash
cd vidaura
pip install -r requirements.txt
```

## Запуск

### 1. Сервер
```bash
# Из папки vidaura/
python run_server.py
```
Сервер запустится на `http://localhost:8000`.  
Swagger UI: `http://localhost:8000/docs`

### 2. Клиент (в отдельном терминале)
```bash
# Из папки vidaura/
python client/main.py
```

> ⚠️ Оба скрипта запускать **из папки `vidaura/`**, не из подпапок.

## Структура проекта

```
vidaura/
├── server/
│   ├── main.py
│   ├── database.py       # SQLite
│   ├── models.py         # User, Channel, Video, Comment, Like, Subscription
│   └── routers/
│       ├── auth.py       # JWT-авторизация
│       ├── videos.py     # Загрузка, стриминг, поиск, лайки
│       ├── channels.py   # Каналы, подписки
│       ├── comments.py   # Комментарии с ответами
│       └── admin.py      # Эндпоинты для панели администратора
├── client/
│   ├── api.py
│   └── ui/
│       ├── main_window.py
│       ├── login.py
│       ├── home.py
│       ├── player.py
│       ├── channel.py
│       └── upload.py
├── admin.html            # Открыть в браузере, без зависимостей
├── run_server.py
└── requirements.txt
```

## Права администратора

В файле `server/routers/admin.py` найди строку:

```python
ADMIN_USERNAMES = {"admin"}
```

Добавь своё имя пользователя. Этот аккаунт получит доступ к `/admin/*` и к `admin.html`.

## Запуск на хостинге

```bash
# Продакшн без --reload
uvicorn server.main:app --host 0.0.0.0 --port 8000
# Или через gunicorn
gunicorn server.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

`admin.html` — статичный файл, положи рядом или открывай локально. Адрес сервера вводится прямо в панели.
