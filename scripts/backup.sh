#!/bin/bash

# Переходим в директорию проекта (замени на реальный путь на сервере позже)
cd "$(dirname "$0")/.."

# Загружаем переменные из .env
export $(grep -v '^#' .env | xargs)

# Формируем имя файла с текущей датой
BACKUP_FILE="db_backup_$(date +%Y-%m-%d_%H-%M-%S).sql.gz"

# Делаем дамп базы прямо из контейнера и сразу сжимаем его
docker exec sniffer_db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | gzip > "$BACKUP_FILE"

# Отправляем архив в Telegram (используем токен бота и твой ADMIN_ID)
curl -s -F document=@"$BACKUP_FILE" \
  "https://api.telegram.org/bot8324969833:AAHW1LNANc_aURNWV8QNL0UlkD2GyzDBRp0/sendDocument?chat_id=336185466&caption=📦 Бэкап БД Sniffer" > /dev/null

# Удаляем локальный архив, чтобы не забивать диск сервера
rm "$BACKUP_FILE"