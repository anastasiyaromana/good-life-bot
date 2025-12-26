import os

BOT_TOKEN = os.environ.get["BOT_TOKEN", "8571782718:AAHIR4xEKr0NrPQU7eQIfZBpHQJ4PKsI_OU"]

DEFAULT_TZ = os.environ.get("DEFAULT_TZ", "Europe/Moscow")
INACTIVE_DAYS = int(os.environ.get("INACTIVE_DAYS", "7"))
NUDGE_COOLDOWN_DAYS = int(os.environ.get("NUDGE_COOLDOWN_DAYS", "7"))

