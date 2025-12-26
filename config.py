import os

BOT_TOKEN = os.environ["BOT_TOKEN"]

DEFAULT_TZ = os.environ.get("DEFAULT_TZ", "Europe/Moscow")
INACTIVE_DAYS = int(os.environ.get("INACTIVE_DAYS", "7"))
NUDGE_COOLDOWN_DAYS = int(os.environ.get("NUDGE_COOLDOWN_DAYS", "7"))
