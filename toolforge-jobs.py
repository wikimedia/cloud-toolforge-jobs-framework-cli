#!/usr/bin/env python3

# (C) 2021 by Arturo Borrero Gonzalez <aborrero@wikimedia.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# Some funcionts of this code were copy-pasted from the tools-webservice package.
# Copyright on that TBD.
#
# This program is the command line interface part of the Toolforge Jobs Framework.
#

from tabulate import tabulate
import requests
import argparse
import urllib3
import logging
import json
import yaml
import sys
import os


# TODO: disable this for now, review later
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Conf:
    """
    Class that represents the configuration for this CLI session
    """

    JOB_TABULATION_HEADERS = {
        "name": "Job id",
        "cmd": "Job command",
        "type": "Job type",
        "image": "image shortname",
        "status": "Job status",
    }

    CONTAINER_TABULATION_HEADERS = {
        "shortname": "Short name",
        "image": "Docker container image",
    }

    def __init__(self, kubeconfig, customurl, customhdr):
        """Constructor"""
        self.kubeconfigfile = os.path.expanduser(kubeconfig)

        try:
            with open(self.kubeconfigfile) as f:
                self.k8sconf = yaml.safe_load(f.read())
        except Exception as e:
            logging.error(f"couldn't read kubeconfig file '{self.kubeconfigfile}': {e}")
            sys.exit(1)

        self.context = self._find_cfg_obj("contexts", self.k8sconf["current-context"])
        self.cluster = self._find_cfg_obj("clusters", self.context["cluster"])
        self.server = self.cluster["server"]
        self.namespace = self.context["namespace"]

        self.user = self._find_cfg_obj("users", self.context["user"])
        self.session = requests.Session()
        self.session.cert = (self.user["client-certificate"], self.user["client-key"])

        if customhdr is not None:
            self.session.headers.update(customhdr)

        # don't verify server-side TLS for now
        self.session.verify = False

        if customurl is not None:
            self.api_url = customurl
            # we are done here!
            return

        projectfile = "/etc/wmcs-project"
        try:
            with open(projectfile) as f:
                project = f.read().strip()
        except Exception as e:
            logging.error(f"couldn't read file '{projectfile}': {e}")
            sys.exit(1)

        # TODO: hardcoded? can't we have some kind of service discovery?
        if project == "toolsbeta":
            self.api_url = "https://jobs.svc.toolsbeta.eqiad1.wikimedia.cloud:30001/api/v1"
        elif project == "tools":
            self.api_url = "https://jobs.svc.tools.eqiad1.wikimedia.cloud:30001/api/v1"
        else:
            logging.error(f"unknown API endpoint in project '{project}'")
            sys.exit(1)

    def _find_cfg_obj(self, kind, name):
        """Lookup a named object in our config."""
        for obj in self.k8sconf[kind]:
            if obj["name"] == name:
                return obj[kind[:-1]]
        raise KeyError(f"key '{name}' not found in '{kind}' section of config")


def parse_args():
    description = "Toolforge Jobs Framework, command line interface"
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("--debug", action="store_true", help="activate debug mode")
    parser.add_argument(
        "--kubeconfig",
        default="~/.kube/config",
        help="user kubeconfig file. Defaults to '%(default)s'. Only useful for Toolforge admins.",
    )
    parser.add_argument(
        "--url",
        help="use custom URL for the Toolforge jobs framework API endpoint. "
        "Only useful for Toolforge admins.",
    )
    parser.add_argument(
        "--hdr",
        type=json.loads,
        help="use custom HTTP headers (in JSON dictinary format) to contact the Toolforge jobs "
        "framework API endpoint. Only useful for Toolforge admins.",
    )

    subparser = parser.add_subparsers(
        help="possible operations (pass -h to know usage of each)", dest="operation"
    )

    subparser.add_parser(
        "containers",
        help="list information on available container types for Toolforge jobs",
    )

    runparser = subparser.add_parser(
        "run",
        help="run a new job of your own in Toolforge",
    )

    runparser.add_argument("name", help="new job name")
    runparser.add_argument(
        "--command", required=True, help="full path of command to run in this job"
    )
    runparser.add_argument(
        "--image", required=True, help="image shortname (check them with `containers`)"
    )
    runparser.add_argument("--schedule", required=False, help="run a job with a cron-like schedule")
    runparser.add_argument(
        "--continuous", required=False, action="store_true", help="run a continuous job"
    )

    showparser = subparser.add_parser(
        "show",
        help="show details of a job of your own in Toolforge",
    )
    showparser.add_argument("name", help="job name")

    subparser.add_parser(
        "list",
        help="list all running jobs of your own in Toolforge",
    )

    deleteparser = subparser.add_parser(
        "delete",
        help="delete a running job of your own in Toolforge",
    )
    deleteparser.add_argument("name", help="job name")

    subparser.add_parser(
        "flush",
        help="delete all running jobs of your own in Toolforge",
    )

    return parser.parse_args()


def op_containers(conf: Conf):
    try:
        response = conf.session.get(conf.api_url + "/containers/")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code != 200:
        logging.error(f"unable to fetch information. Contact a Toolforge admin: {response.text}")
        sys.exit(1)

    try:
        containers = json.loads(response.text)
    except Exception as e:
        logging.error(f"couldn't parse information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    try:
        output = tabulate(containers, headers=conf.CONTAINER_TABULATION_HEADERS)
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def job_prepare_for_output(job):
    schedule = job.get("schedule", None)
    cont = job.get("continuous", None)
    if schedule is not None:
        job["type"] = f"schedule: {schedule}"
        job.pop("schedule", None)
    elif cont is not None:
        job["type"] = "continuous"
        job.pop("continuous", None)
    else:
        job["type"] = "normal"

    # not interested in these fields ATM
    if job.get("user", None) is not None:
        job.pop("user", None)
    if job.get("namespace", None) is not None:
        job.pop("namespace", None)


def op_list(conf: Conf):
    try:
        response = conf.session.get(conf.api_url + "/list/")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code != 200:
        logging.error(f"unable to fetch information. Contact a Toolforge admin: {response.text}")
        sys.exit(1)

    try:
        list = json.loads(response.text)
    except Exception as e:
        logging.error(f"couldn't parse information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if len(list) == 0:
        logging.debug("no jobs to be listed")
        return

    for job in list:
        logging.debug(f"job information from the API: {job}")
        job_prepare_for_output(job)

    try:
        output = tabulate(list, headers=conf.JOB_TABULATION_HEADERS)
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def op_run(conf: Conf, name, command, schedule, continuous, image):
    payload = {"name": name, "imagename": image, "cmd": command}

    if continuous:
        payload["continuous"] = "true"
    elif schedule:
        payload["schedule"] = schedule

    logging.debug(f"payload: {payload}")

    try:
        response = conf.session.post(conf.api_url + "/run/", data=payload)
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code == 409:
        logging.error(f"a job with the same name '{name}' exists already")
        sys.exit(1)

    if response.status_code >= 300:
        logging.error(f"unable to create job: {response.text.strip()}")
        sys.exit(1)

    logging.debug("job was created")


def op_show(conf: Conf, name):
    try:
        response = conf.session.get(conf.api_url + f"/show/{name}")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code == 404:
        logging.error(f"job '{name}' does not exists")
        sys.exit(1)

    try:
        job = json.loads(response.text)
    except Exception as e:
        logging.error(f"couldn't parse information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug(f"job information from the API: {job}")
    job_prepare_for_output(job)

    try:
        output = tabulate([job], headers=conf.JOB_TABULATION_HEADERS)
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def op_delete(conf: Conf, name):
    try:
        conf.session.delete(conf.api_url + f"/delete/{name}")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug("job was deleted (if it existed anyway, we didn't check)")


def op_flush(conf: Conf):
    try:
        conf.session.delete(conf.api_url + "/flush/")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug("all jobs were flushed (if any existed anyway, we didn't check)")


def main():
    args = parse_args()

    logging_format = "[%(filename)s] %(levelname)s: %(message)s"
    if args.debug:
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO
    logging.addLevelName(
        logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING)
    )
    logging.addLevelName(
        logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR)
    )
    logging.basicConfig(format=logging_format, level=logging_level, stream=sys.stdout)

    conf = Conf(args.kubeconfig, args.url, args.hdr)
    logging.debug("session configuration generated correctly")

    if args.operation == "containers":
        op_containers(conf)
    elif args.operation == "run":
        op_run(conf, args.name, args.command, args.schedule, args.continuous, args.image)
    elif args.operation == "show":
        op_show(conf, args.name)
    elif args.operation == "delete":
        op_delete(conf, args.name)
    elif args.operation == "list":
        op_list(conf)
    elif args.operation == "flush":
        op_flush(conf)

    logging.debug("-- end of operations")


if __name__ == "__main__":
    main()
