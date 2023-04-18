# Copyright (C) 2023 Taavi Väänänen <hi@taavi.wtf>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import json
from logging import getLogger
from typing import Any, Dict

LOGGER = getLogger(__name__)


class TjfCliError(Exception):
    """Custom error class for jobs-framework-cli errors."""

    def __init__(self, message: str, *args) -> None:
        super().__init__(message, *args)
        self.message = message

    context: Dict[str, Any] = {}


class TjfCliUserError(TjfCliError):
    """Custom error class for jobs-framework-cli errors from user actions like invalid input."""


def print_error_context(error: TjfCliError):
    if len(error.context.keys()) == 0:
        if error.__cause__ and isinstance(error.__cause__, TjfCliError):
            print_error_context(error.__cause__)

        return

    LOGGER.error("Some additional context for the issue follows:")
    for k, v in error.context.items():
        LOGGER.error(" %s = %s", k, json.dumps(v))
