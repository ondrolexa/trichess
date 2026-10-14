"""Maintenance mode: an admin-only switch (profile page) that shuts every
non-admin out of the app with a "back soon" page, and pauses bots and cron
reminders until it's turned off. Stored in the `setting` table so all
processes agree on it.
"""

from webapp.main import db
from webapp.models import Setting

KEY = "maintenance"


def is_maintenance() -> bool:
    row = db.session.get(Setting, KEY)
    return row is not None and row.value == "on"


def set_maintenance(on: bool) -> None:
    row = db.session.get(Setting, KEY)
    if row is None:
        row = Setting(key=KEY, value="off")
        db.session.add(row)
    row.value = "on" if on else "off"
    db.session.commit()
