# (C) 2021 Arturo Borrero Gonzalez <aborrero@wikimedia.org>
# (C) 2022 Taavi Väänänen <hi@taavi.wtf>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Some funcionts of this code were copy-pasted from the tools-webservice package.
# Copyright on that TBD.

import os
import socket
from logging import getLogger
from typing import Any, Dict, Optional

import requests
import yaml

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


def _find_cfg_obj(config: Dict[str, Any], kind: str, name: str):
    """Lookup a named object in our config."""
    for obj in config[kind]:
        if obj["name"] == name:
            return obj[kind[:-1]]
    raise TjfCliConfigLoadError(f"Key '{name}' not found in '{kind}' section of config")


def _make_http_error(original: requests.exceptions.HTTPError) -> TjfCliHttpError:
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


class ApiClient:
    """Client to work with the jobs-framework API."""

    def __init__(self, *, session: requests.Session, api_url: str) -> None:
        """Constructor"""
        self._session = session
        self._api_url = api_url

    @classmethod
    def create(cls, cfg_file: str, cert_file: Optional[str], key_file: Optional[str]):
        """Creates an ApiClient based on details in a config file."""

        try:
            with open(cfg_file) as f:
                cfg = yaml.safe_load(f.read())
        except Exception as e:
            raise TjfCliConfigLoadError(f"Failed to read config file '{cfg_file}'") from e

        try:
            api_url = cfg.get("api_url")
        except KeyError as e:
            raise TjfCliConfigLoadError(
                f"Missing key '{str(e)}' in config file '{cfg_file}'"
            ) from e

        kubeconfig = cfg.get("kubeconfig", "~/.kube/config")
        customhdr = cfg.get("customhdr", None)
        customaddr = cfg.get("customaddr", None)
        customfqdn = cfg.get("customfqdn", None)

        k8s_config_file = os.path.expanduser(kubeconfig)

        try:
            with open(k8s_config_file) as f:
                k8s_config = yaml.safe_load(f.read())
        except Exception as e:
            raise TjfCliConfigLoadError(
                f"Failed to read Kubernetes config file '{k8s_config_file}"
            ) from e

        LOGGER.debug(f"loaded kubeconfig file '{k8s_config_file}'")

        # load the paths from the kubeconfig file relative to itself just like the
        # official libraries
        old_dir = os.curdir
        os.chdir(os.path.dirname(k8s_config_file))
        session = requests.Session()
        try:
            context = _find_cfg_obj(k8s_config, "contexts", k8s_config["current-context"])
            namespace = context["namespace"]
            user = _find_cfg_obj(k8s_config, "users", context["user"])

            cert = cert_file if cert_file else user["client-certificate"]
            key = key_file if key_file else user["client-key"]
            session.cert = (os.path.realpath(cert), os.path.realpath(key))
        except KeyError as e:
            raise TjfCliConfigLoadError(
                f"Missing key '{str(e)}' in Kubernetes config file '{k8s_config_file}'"
            ) from e
        except Exception as e:
            raise TjfCliConfigLoadError(
                f"Failed to parse Kubernetes config file '{k8s_config_file}"
            ) from e

        os.chdir(old_dir)
        host = socket.gethostname()
        pyrequest_ua = requests.utils.default_user_agent()
        session.headers.update(
            {"User-Agent": f"jobs-framework-cli {namespace}@{host} {pyrequest_ua}"}
        )

        if customhdr is not None:
            session.headers.update(customhdr)

        # don't verify server-side TLS for now
        session.verify = False

        if customaddr is not None and customfqdn is not None:
            from forcediphttpsadapter.adapters import ForcedIPHTTPSAdapter

            session.mount(f"https://{customfqdn}", ForcedIPHTTPSAdapter(dest_ip=customaddr))

        return cls(
            session=session,
            api_url=api_url,
        )

    def _make_kwargs(self, url_path: str, **kwargs) -> dict:
        kwargs["url"] = f"{self._api_url}{url_path}"
        return kwargs

    def _make_request(self, method: str, url_path: str, **kwargs) -> requests.Response:
        try:
            response = self._session.request(method, **self._make_kwargs(url_path, **kwargs))
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            new_error = _make_http_error(e)
            raise new_error from e

    def get(self, url_path: str, **kwargs) -> requests.Response:
        """Make a GET request."""
        return self._make_request("GET", url_path, **kwargs)

    def post(self, url_path: str, **kwargs) -> requests.Response:
        """Make a POST request."""
        return self._make_request("POST", url_path, **kwargs)

    def delete(self, url_path: str, **kwargs) -> requests.Response:
        """Make a DELETE request."""
        return self._make_request("DELETE", url_path, **kwargs)
