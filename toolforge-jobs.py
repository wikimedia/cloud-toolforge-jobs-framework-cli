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
import textwrap
import requests
import argparse
import getpass
import urllib3
import logging
import socket
import time
import json
import yaml
import sys
import os


# TODO: disable this for now, review later
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# for --wait: 5 minutes timeout, check every 5 seconds
WAIT_TIMEOUT = 60 * 5
WAIT_SLEEP = 5


class Conf:
    """
    Class that represents the configuration for this CLI session
    """

    JOB_TABULATION_HEADERS = {
        "name": "Job name:",
        "cmd": "Command:",
        "type": "Job type:",
        "image": "Container:",
        "filelog": "File log:",
        "emails": "Emails:",
        "resources": "Resources:",
        "status_short": "Status:",
        "status_long": "Hints:",
    }

    CONTAINER_TABULATION_HEADERS = {
        "shortname": "Short name",
        "image": "Docker container image",
    }

    def __init__(self, cfg_file: str):
        """Constructor"""

        try:
            with open(cfg_file) as f:
                cfg = yaml.safe_load(f.read())
        except Exception as e:
            logging.error(
                f"couldn't read config file '{cfg_file}': {e}. Contact a Toolforge admin."
            )
            sys.exit(1)

        try:
            self.api_url = cfg.get("api_url")
        except KeyError as e:
            logging.error(
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
            logging.error(
                f"couldn't read kubeconfig file '{self.kubeconfigfile}': {e}. "
                "Contact a Toolforge admin."
            )
            sys.exit(1)

        logging.debug(f"loaded kubeconfig file '{self.kubeconfigfile}'")

        self.session = requests.Session()
        try:
            self.context = self._find_cfg_obj("contexts", self.k8sconf["current-context"])
            self.cluster = self._find_cfg_obj("clusters", self.context["cluster"])
            self.server = self.cluster["server"]
            self.namespace = self.context["namespace"]
            self.user = self._find_cfg_obj("users", self.context["user"])
            self.session.cert = (self.user["client-certificate"], self.user["client-key"])
        except KeyError as e:
            logging.error(
                "couldn't build session configuration from file "
                f"'{self.kubeconfigfile}': missing key {e}. Contact a Toolforge admin."
            )
            sys.exit(1)
        except Exception as e:
            logging.error(
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


def parse_args():
    description = "Toolforge Jobs Framework, command line interface"
    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("--debug", action="store_true", help="activate debug mode")
    parser.add_argument(
        "--cfg",
        default="/etc/toolforge-jobs-framework-cli.cfg",
        help="YAML config for the CLI. Defaults to '%(default)s'. "
        "Only useful for Toolforge admins.",
    )

    subparser = parser.add_subparsers(
        help="possible operations (pass -h to know usage of each)",
        dest="operation",
        required=True,
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
    runparser.add_argument(
        "--no-filelog",
        required=False,
        action="store_true",
        help="don't store job stdout in `jobname`.out and stderr in `jobname`.err files in the "
        "user home directory",
    )
    runparser.add_argument(
        "--mem",
        required=False,
        help="specify additional memory limit required for this job",
    )
    runparser.add_argument(
        "--cpu",
        required=False,
        help="specify additional CPU limit required for this job",
    )
    runparser.add_argument(
        "--emails",
        required=False,
        choices=["none", "all", "onfinish", "onfailure"],
        default="none",
        help="specify if the system should email notifications about this job. "
        "Defaults to '%(default)s'.",
    )

    runparser_exclusive_group = runparser.add_mutually_exclusive_group()
    runparser_exclusive_group.add_argument(
        "--schedule",
        required=False,
        help="run a job with a cron-like schedule (example '1 * * * *')",
    )
    runparser_exclusive_group.add_argument(
        "--continuous", required=False, action="store_true", help="run a continuous job"
    )
    runparser_exclusive_group.add_argument(
        "--wait",
        required=False,
        action="store_true",
        help=f"run a job and wait for completition. Timeout is {WAIT_TIMEOUT} seconds.",
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

    loadparser = subparser.add_parser(
        "load",
        help="flush all jobs and load a YAML file with job definitions and run them",
    )
    loadparser.add_argument("file", help="path to YAML file to load")

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
        output = tabulate(containers, headers=conf.CONTAINER_TABULATION_HEADERS, tablefmt="pretty")
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def job_prepare_for_output(conf: Conf, job, supress_hints=True):
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

    filelog = job.get("filelog", "false")
    if filelog == "True":
        job["filelog"] = "yes"
    else:
        job["filelog"] = "no"

    mem = job.pop("memory", "default")
    cpu = job.pop("cpu", "default")
    if mem == "default" and cpu == "default":
        job["resources"] = "default"
    else:
        job["resources"] = f"mem: {mem}, cpu: {cpu}"

    if supress_hints:
        if job.get("status_long", None) is not None:
            job.pop("status_long", None)
    else:
        job["status_long"] = textwrap.fill(job.get("status_long", "Unknown"))

    # not interested in these fields ATM
    for key in job.copy():
        if key not in conf.JOB_TABULATION_HEADERS:
            logging.debug(f"supressing job API field '{key}' before output")
            job.pop(key)

    # normalize key names for easier printing
    for key in conf.JOB_TABULATION_HEADERS:
        if key == "status_long" and supress_hints:
            continue

        oldkey = key
        newkey = conf.JOB_TABULATION_HEADERS[key]
        job[newkey] = job.pop(oldkey, "Unknown")


def _list_jobs(conf: Conf):
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

    return list


def op_list(conf: Conf):
    list = _list_jobs(conf)

    if len(list) == 0:
        logging.debug("no jobs to be listed")
        return

    try:
        for job in list:
            logging.debug(f"job information from the API: {job}")
            job_prepare_for_output(conf, job, supress_hints=True)

        output = tabulate(list, headers=conf.JOB_TABULATION_HEADERS, tablefmt="pretty")
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def _wait_for_job(conf: Conf, name: str):
    curtime = starttime = time.time()
    while curtime - starttime < WAIT_TIMEOUT:
        time.sleep(WAIT_SLEEP)
        curtime = time.time()

        job = _show_job(conf, name, missing_ok=True)
        if job is None:
            logging.info(f"job '{name}' completed (and already deleted)")
            return

        if job["status_short"] == "Completed":
            logging.info(f"job '{name}' completed")
            return

        if job["status_short"] == "Failed":
            logging.error(f"job '{name}' failed:")
            op_show(conf, name)
            sys.exit(1)

    logging.error(f"timed out {WAIT_TIMEOUT} seconds waiting for job '{name}' to complete:")
    op_show(conf, name)
    sys.exit(1)


def op_run(
    conf: Conf,
    name,
    command,
    schedule,
    continuous,
    image,
    wait,
    no_filelog: bool,
    mem: str,
    cpu: str,
    emails: str,
):
    payload = {"name": name, "imagename": image, "cmd": command, "emails": emails}

    if continuous:
        payload["continuous"] = "true"
    elif schedule:
        payload["schedule"] = schedule

    if not no_filelog:
        # the default is to request the filelog
        payload["filelog"] = "true"

    if mem:
        payload["memory"] = mem

    if cpu:
        payload["cpu"] = cpu

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

    if wait:
        _wait_for_job(conf, name)


def _show_job(conf: Conf, name: str, missing_ok: bool):
    try:
        response = conf.session.get(conf.api_url + f"/show/{name}")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code == 404:
        if missing_ok:
            return None  # the job doesn't exist, but that's ok!

        logging.error(f"job '{name}' does not exists")
        sys.exit(1)

    try:
        job = json.loads(response.text)
    except Exception as e:
        logging.error(f"couldn't parse information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug(f"job information from the API: {job}")
    return job


def op_show(conf: Conf, name):
    job = _show_job(conf, name, missing_ok=False)
    job_prepare_for_output(conf, job, supress_hints=False)

    # change table direction
    kvlist = []
    for key in job:
        kvlist.append([key, job[key]])

    try:
        output = tabulate(kvlist, tablefmt="grid")
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


def _flush_and_wait(conf: Conf):
    op_flush(conf)

    curtime = starttime = time.time()
    while curtime - starttime < WAIT_TIMEOUT:
        logging.debug(f"waiting for jobs list to be empty, sleeping {WAIT_SLEEP} seconds")
        time.sleep(WAIT_SLEEP)
        curtime = time.time()

        list = _list_jobs(conf)

        if len(list) == 0:
            # ok!
            return

    logging.error("could not load new jobs")
    logging.error(f"timed out ({WAIT_TIMEOUT} seconds) waiting for previous jobs to be flushed")
    sys.exit(1)


def _load_job(conf: Conf, job: dict, n: int):
    # these are mandatory
    try:
        name = job["name"]
        command = job["command"]
        image = job["image"]
    except KeyError as e:
        logging.error(f"Unable to load job number {n}. Missing configuration parameter {str(e)}")
        sys.exit(1)

    # these are optional
    schedule = job.get("schedule", None)
    continuous = job.get("continuous", False)
    no_filelog = job.get("no-filelog", False)
    mem = job.get("mem", None)
    cpu = job.get("cpu", None)
    emails = job.get("emails", "none")

    if not schedule and not continuous:
        wait = job.get("wait", False)
    else:
        wait = False

    op_run(
        conf=conf,
        name=name,
        command=command,
        schedule=schedule,
        continuous=continuous,
        image=image,
        wait=wait,
        no_filelog=no_filelog,
        mem=mem,
        cpu=cpu,
        emails=emails,
    )


def op_load(conf: Conf, file: str):
    try:
        with open(file) as f:
            jobslist = yaml.safe_load(f.read())
    except Exception as e:
        logging.error(f"couldn't read YAML file '{file}': {e}")
        sys.exit(1)

    logging.debug(f"loaded content from YAML file '{file}':")
    logging.debug(f"{jobslist}")

    # before loading new jobs, flush and wait for them to go away
    _flush_and_wait(conf)
    logging.debug("jobs list is confirmed to be empty, now loading new jobs")

    for n, job in enumerate(jobslist, start=1):
        _load_job(conf, job, n)


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

    user = getpass.getuser()
    if not user.startswith("tools.") and not user.startswith("toolsbeta."):
        logging.warning(
            "not running as the tool account? Likely to fail. Perhaps you forgot `become <tool>`?"
        )

    conf = Conf(args.cfg)
    logging.debug("session configuration generated correctly")

    if args.operation == "containers":
        op_containers(conf)
    elif args.operation == "run":
        op_run(
            conf,
            args.name,
            args.command,
            args.schedule,
            args.continuous,
            args.image,
            args.wait,
            args.no_filelog,
            args.mem,
            args.cpu,
            args.emails,
        )
    elif args.operation == "show":
        op_show(conf, args.name)
    elif args.operation == "delete":
        op_delete(conf, args.name)
    elif args.operation == "list":
        op_list(conf)
    elif args.operation == "flush":
        op_flush(conf)
    elif args.operation == "load":
        op_load(conf, args.file)

    logging.debug("-- end of operations")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
