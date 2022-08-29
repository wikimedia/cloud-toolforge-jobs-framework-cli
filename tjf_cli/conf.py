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
import sys
from logging import getLogger

import requests
import yaml

LOGGER = getLogger(__name__)


class Conf:
    """
    Class that represents the configuration for this CLI session
    """

    JOB_TABULATION_HEADERS_SHORT = {
        "name": "Job name:",
        "type": "Job type:",
        "status_short": "Status:",
    }

    JOB_TABULATION_HEADERS_LONG = {
        "name": "Job name:",
        "cmd": "Command:",
        "type": "Job type:",
        "image": "Image:",
        "filelog": "File log:",
        "filelog_stdout": "Output log:",
        "filelog_stderr": "Error log:",
        "emails": "Emails:",
        "resources": "Resources:",
        "status_short": "Status:",
        "status_long": "Hints:",
    }

    IMAGES_TABULATION_HEADERS = {
        "shortname": "Short name",
        "image": "Container image URL",
    }

    def __init__(self, cfg_file: str):
        """Constructor"""

        try:
            with open(cfg_file) as f:
                cfg = yaml.safe_load(f.read())
        except Exception as e:
            LOGGER.error(f"couldn't read config file '{cfg_file}': {e}. Contact a Toolforge admin.")
            sys.exit(1)

        try:
            self.api_url = cfg.get("api_url")
        except KeyError as e:
            LOGGER.error(
                f"missing key '{str(e)}' in config file '{cfg_file}'. Contact a Toolforge admin."
            )
            sys.exit(1)

        kubeconfig = cfg.get("kubeconfig", "~/.kube/config")
        customhdr = cfg.get("customhdr", None)
        customaddr = cfg.get("customaddr", None)
        customfqdn = cfg.get("customfqdn", None)
        self.kubeconfigfile = os.path.expanduser(kubeconfig)

        try:
            with open(self.kubeconfigfile) as f:
                self.k8sconf = yaml.safe_load(f.read())
        except Exception as e:
            LOGGER.error(
                f"couldn't read kubeconfig file '{self.kubeconfigfile}': {e}. "
                "Contact a Toolforge admin."
            )
            sys.exit(1)

        LOGGER.debug(f"loaded kubeconfig file '{self.kubeconfigfile}'")

        self.session = requests.Session()
        try:
            self.context = self._find_cfg_obj("contexts", self.k8sconf["current-context"])
            self.cluster = self._find_cfg_obj("clusters", self.context["cluster"])
            self.server = self.cluster["server"]
            self.namespace = self.context["namespace"]
            self.user = self._find_cfg_obj("users", self.context["user"])
            self.session.cert = (self.user["client-certificate"], self.user["client-key"])
        except KeyError as e:
            LOGGER.error(
                "couldn't build session configuration from file "
                f"'{self.kubeconfigfile}': missing key {e}. Contact a Toolforge admin."
            )
            sys.exit(1)
        except Exception as e:
            LOGGER.error(
                "couldn't build session configuration from file "
                f"'{self.kubeconfigfile}': {e}. Contact a Toolforge admin."
            )
            sys.exit(1)

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
        raise KeyError(f"key '{name}' not found in '{kind}' section of config")
