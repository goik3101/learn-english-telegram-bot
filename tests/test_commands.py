import re

from app import menu

_VALID_COMMAND = re.compile(r"^[a-z0-9_]{1,32}$")


def test_general_and_admin_commands_match_telegram_naming_rules():
    for command, description in menu.GENERAL_COMMANDS + menu.ADMIN_ONLY_COMMANDS:
        assert _VALID_COMMAND.match(command), f"invalid command name: {command}"
        assert description
