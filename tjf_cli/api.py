# (C) 2021 Arturo Borrero Gonzalez <aborrero@wikimedia.org>
# (C) 2022 Taavi Väänänen <hi@taavi.wtf>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#

from logging import getLogger
from typing import Any, Dict

import requests

from tjf_cli.errors import TjfCliError, TjfCliUserError

LOGGER = getLogger(__name__)


class TjfCliConfigLoadError(TjfCliError):
    """Raised when the configuration fails to load."""


class TjfCliHttpError(TjfCliError):
    """Raised when a HTTP request fails."""

    def __init__(self, message: str, status_code: int, context: Dict[str, Any]) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.context = context


class TjfCliHttpUserError(TjfCliHttpError, TjfCliUserError):
    """Raised when a HTTP request fails with a 4xx status code."""


def handle_http_exception(original: requests.exceptions.HTTPError) -> TjfCliHttpError:
    error_class = (
        TjfCliHttpUserError
        if (original.response.status_code >= 400 and original.response.status_code <= 499)
        else TjfCliHttpError
    )

    message = original.response.text
    context = {}
    try:
        json = original.response.json()
        if isinstance(json, dict):
            if "error" in json:
                message = json["error"]
            elif "message" in json:
                # flask-restful internal errors use this format
                message = json["message"]

            if "data" in json:
                context = json["data"]
        elif isinstance(json, str):
            message = json
    except requests.exceptions.InvalidJSONError:
        pass

    return error_class(message=message, status_code=original.response.status_code, context=context)
