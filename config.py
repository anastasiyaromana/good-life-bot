import os

BOT_TOKEN = os.environ["BOT_TOKEN"]

# Если пользователь не выбрал регион — считаем Москву
DEFAULT_TZ = os.environ.get("DEFAULT_TZ", "Europe/Moscow")

# Тихое правило
INACTIVE_DAYS = int(os.environ.get("INACTIVE_DAYS", "7"))          # через сколько дней молчания писать
NUDGE_COOLDOWN_DAYS = int(os.environ.get("NUDGE_COOLDOWN_DAYS", "7"))  # не чаще чем раз в N дней
