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
from typing import Optional

import requests
import yaml

from tjf_cli.errors import TjfCliError

LOGGER = getLogger(__name__)


class TjfCliConfigLoadError(TjfCliError):
    """Raised when the configuration fails to load."""


class ApiClient:
    """Client to work with the jobs-framework API."""

    def __init__(self, cfg_file: str, cert_file: Optional[str], key_file: Optional[str]):
        """Constructor"""

        try:
            with open(cfg_file) as f:
                cfg = yaml.safe_load(f.read())
        except Exception as e:
            raise TjfCliConfigLoadError(f"Failed to read config file '{cfg_file}") from e

        try:
            self.api_url = cfg.get("api_url")
        except KeyError as e:
            raise TjfCliConfigLoadError(
                f"Missing key '{str(e)}' in config file '{cfg_file}'"
            ) from e

        kubeconfig = cfg.get("kubeconfig", "~/.kube/config")
        customhdr = cfg.get("customhdr", None)
        customaddr = cfg.get("customaddr", None)
        customfqdn = cfg.get("customfqdn", None)
        self.kubeconfigfile = os.path.expanduser(kubeconfig)

        try:
            with open(self.kubeconfigfile) as f:
                self.k8sconf = yaml.safe_load(f.read())
        except Exception as e:
            raise TjfCliConfigLoadError(
                f"Failed to read Kubernetes config file '{self.kubeconfigfile}"
            ) from e

        LOGGER.debug(f"loaded kubeconfig file '{self.kubeconfigfile}'")

        self.session = requests.Session()
        try:
            self.context = self._find_cfg_obj("contexts", self.k8sconf["current-context"])
            self.cluster = self._find_cfg_obj("clusters", self.context["cluster"])
            self.server = self.cluster["server"]
            self.namespace = self.context["namespace"]
            self.user = self._find_cfg_obj("users", self.context["user"])
            _cert = cert_file if cert_file else self.user["client-certificate"]
            _key = key_file if key_file else self.user["client-key"]
            self.session.cert = (_cert, _key)
        except KeyError as e:
            raise TjfCliConfigLoadError(
                f"Missing key '{str(e)}' in Kubernetes config file '{self.kubeconfigfile}'"
            ) from e
        except Exception as e:
            raise TjfCliConfigLoadError(
                f"Failed to parse Kubernetes config file '{self.kubeconfigfile}"
            ) from e

        self._configure_user_agent()

        if customhdr is not None:
            self.session.headers.update(customhdr)

        # don't verify server-side TLS for now
        self.session.verify = False

        if customaddr is not None and customfqdn is not None:
            from forcediphttpsadapter.adapters import ForcedIPHTTPSAdapter

            self.session.mount(f"https://{customfqdn}", ForcedIPHTTPSAdapter(dest_ip=customaddr))

    def _configure_user_agent(self):
        """Configure User-Agent header."""
        host = socket.gethostname()
        pyrequest_ua = requests.utils.default_user_agent()
        ua_str = f"jobs-framework-cli {self.namespace}@{host} {pyrequest_ua}"
        self.session.headers.update({"User-Agent": ua_str})

    def _find_cfg_obj(self, kind, name):
        """Lookup a named object in our config."""
        for obj in self.k8sconf[kind]:
            if obj["name"] == name:
                return obj[kind[:-1]]
        raise TjfCliConfigLoadError(f"Key '{name}' not found in '{kind}' section of config")
