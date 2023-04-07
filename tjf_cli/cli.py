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

from enum import Enum
from tabulate import tabulate
from typing import List, Optional, Set
import textwrap
import argparse
import getpass
import urllib3
import logging
import time
import json
import yaml
import sys

from tjf_cli.api import ApiClient
from tjf_cli.errors import TjfCliError
from tjf_cli.loader import calculate_changes

# TODO: disable this for now, review later
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# for --wait: 5 minutes timeout, check every 5 seconds
WAIT_TIMEOUT = 60 * 5
WAIT_SLEEP = 5


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
    "retry": "Retry:",
    "status_short": "Status:",
    "status_long": "Hints:",
}

IMAGES_TABULATION_HEADERS = {
    "shortname": "Short name",
    "image": "Container image URL",
}


class ListDisplayMode(Enum):
    NORMAL = "normal"
    LONG = "long"

    def __str__(self) -> str:
        """Needed to play nice with argparse."""
        return self.value


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

    parser.add_argument(
        "--cert",
        required=False,
        help="override kubeconfig TLS cert path. Only useful for Toolforge admins.",
    )

    parser.add_argument(
        "--key",
        required=False,
        help="override kubeconfig TLS key path. Only useful for Toolforge admins.",
    )

    subparser = parser.add_subparsers(
        help="possible operations (pass -h to know usage of each)",
        dest="operation",
        required=True,
    )

    # TODO: remove this after a few months
    subparser.add_parser(
        "containers",
        help="Kept for compatibility reasons, use `images` instead.",
    )
    subparser.add_parser(
        "images",
        help="list information on available container image types for Toolforge jobs",
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
        "--image", required=True, help="image shortname (check them with `images`)"
    )
    runparser.add_argument(
        "--no-filelog",
        required=False,
        action="store_true",
        help="don't store job stdout in `jobname`.out and stderr in `jobname`.err files in the "
        "user home directory",
    )
    runparser.add_argument(
        "-o", "--filelog-stdout", required=False, help="location to store stdout logs for this job"
    )
    runparser.add_argument(
        "-e", "--filelog-stderr", required=False, help="location to store stderr logs for this job"
    )
    runparser.add_argument(
        "--retry",
        required=False,
        choices=[0, 1, 2, 3, 4, 5],
        default=0,
        type=int,
        help="specify the retry policy of failed jobs.",
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

    listparser = subparser.add_parser(
        "list",
        help="list all running jobs of your own in Toolforge",
    )
    listparser.add_argument(
        "-o",
        "--output",
        type=ListDisplayMode,
        choices=list(ListDisplayMode),
        default=ListDisplayMode.NORMAL,
        help="specify output format (defaults to %(default)s)",
    )
    # deprecated, remove in a few releases
    listparser.add_argument(
        "-l",
        "--long",
        required=False,
        action="store_true",
        help=argparse.SUPPRESS,
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
    loadparser.add_argument("--job", required=False, help="load a single job only")

    restartparser = subparser.add_parser("restart", help="restarts a running job")
    restartparser.add_argument("name", help="job name")

    return parser.parse_args()


def op_images(api: ApiClient):
    try:
        response = api.get("/images/")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code != 200:
        logging.error(f"unable to fetch information. Contact a Toolforge admin: {response.text}")
        sys.exit(1)

    try:
        images = json.loads(response.text)
    except Exception as e:
        logging.error(f"couldn't parse information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    try:
        output = tabulate(images, headers=IMAGES_TABULATION_HEADERS, tablefmt="pretty")
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def job_prepare_for_output(api: ApiClient, job, headers: List[str], suppress_hints=True):
    schedule = job.get("schedule", None)
    cont = job.get("continuous", None)
    retry = job.get("retry")
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

    if retry == 0:
        job["retry"] = "no"
    else:
        job["retry"] = f"yes: {retry} time(s)"

    mem = job.pop("memory", "default")
    cpu = job.pop("cpu", "default")
    if mem == "default" and cpu == "default":
        job["resources"] = "default"
    else:
        job["resources"] = f"mem: {mem}, cpu: {cpu}"

    if suppress_hints:
        if job.get("status_long", None) is not None:
            job.pop("status_long", None)
    else:
        job["status_long"] = textwrap.fill(job.get("status_long", "Unknown"))

    if job["image_state"] != "stable":
        job["image"] += " ({})".format(job["image_state"])

    # not interested in these fields ATM
    for key in job.copy():
        if key not in headers:
            logging.debug(f"supressing job API field '{key}' before output")
            job.pop(key)

    # normalize key names for easier printing
    for key in headers:
        if key == "status_long" and suppress_hints:
            continue

        oldkey = key
        newkey = headers[key]
        job[newkey] = job.pop(oldkey, "Unknown")


def _list_jobs(api: ApiClient):
    try:
        response = api.get("/list/")
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


def op_list(api: ApiClient, output_format: ListDisplayMode):
    list = _list_jobs(api)

    if len(list) == 0:
        logging.debug("no jobs to be listed")
        return

    try:
        if output_format == ListDisplayMode.LONG:
            headers = JOB_TABULATION_HEADERS_LONG
        else:
            headers = JOB_TABULATION_HEADERS_SHORT

        for job in list:
            logging.debug(f"job information from the API: {job}")
            job_prepare_for_output(api, job, headers=headers, suppress_hints=True)

        output = tabulate(list, headers=headers, tablefmt="pretty")
    except Exception as e:
        logging.error(f"couldn't format information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    print(output)


def _wait_for_job(api: ApiClient, name: str):
    curtime = starttime = time.time()
    while curtime - starttime < WAIT_TIMEOUT:
        time.sleep(WAIT_SLEEP)
        curtime = time.time()

        job = _show_job(api, name, missing_ok=True)
        if job is None:
            logging.info(f"job '{name}' completed (and already deleted)")
            return

        if job["status_short"] == "Completed":
            logging.info(f"job '{name}' completed")
            return

        if job["status_short"] == "Failed":
            logging.error(f"job '{name}' failed:")
            op_show(api, name)
            sys.exit(1)

    logging.error(f"timed out {WAIT_TIMEOUT} seconds waiting for job '{name}' to complete:")
    op_show(api, name)
    sys.exit(1)


def op_run(
    api: ApiClient,
    name: str,
    command: str,
    schedule: Optional[str],
    continuous: bool,
    image: str,
    wait: bool,
    no_filelog: bool,
    filelog_stdout: Optional[str],
    filelog_stderr: Optional[str],
    mem: Optional[str],
    cpu: Optional[str],
    retry: int,
    emails: str,
):
    payload = {"name": name, "imagename": image, "cmd": command, "emails": emails, "retry": retry}

    if continuous:
        payload["continuous"] = "true"
    elif schedule:
        payload["schedule"] = schedule

    if not no_filelog:
        # the default is to request the filelog
        payload["filelog"] = "true"

    if filelog_stdout:
        payload["filelog_stdout"] = filelog_stdout

    if filelog_stderr:
        payload["filelog_stderr"] = filelog_stderr

    if mem:
        payload["memory"] = mem

    if cpu:
        payload["cpu"] = cpu

    logging.debug(f"payload: {payload}")

    try:
        response = api.post("/run/", data=payload)
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
        _wait_for_job(api, name)


def _show_job(api: ApiClient, name: str, missing_ok: bool):
    try:
        response = api.get(f"/show/{name}")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    if response.status_code == 404:
        if missing_ok:
            return None  # the job doesn't exist, but that's ok!

        logging.error(f"job '{name}' does not exist")
        sys.exit(1)

    try:
        job = json.loads(response.text)
    except Exception as e:
        logging.error(f"couldn't parse information from the API. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug(f"job information from the API: {job}")
    return job


def op_show(api: ApiClient, name):
    job = _show_job(api, name, missing_ok=False)
    job_prepare_for_output(api, job, suppress_hints=False, headers=JOB_TABULATION_HEADERS_LONG)

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


def op_delete(api: ApiClient, name: str):
    try:
        api.delete(f"/delete/{name}")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug("job was deleted (if it existed anyway, we didn't check)")


def op_flush(api: ApiClient):
    try:
        api.delete("/flush/")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug("all jobs were flushed (if any existed anyway, we didn't check)")


def _delete_and_wait(api: ApiClient, names: Set[str]):
    for name in names:
        op_delete(api, name)

    curtime = starttime = time.time()
    while curtime - starttime < WAIT_TIMEOUT:
        logging.debug(f"waiting for {len(names)} job(s) to be gone, sleeping {WAIT_SLEEP} seconds")
        time.sleep(WAIT_SLEEP)
        curtime = time.time()

        jobs = _list_jobs(api)
        if not any([job for job in jobs if job["name"] in names]):
            # ok!
            return

    logging.error("could not load new jobs")
    logging.error(f"timed out ({WAIT_TIMEOUT} seconds) waiting for old jobs to be deleted")
    sys.exit(1)


def _load_job(api: ApiClient, job: dict, n: int):
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
    filelog_stdout = job.get("filelog-stdout", None)
    filelog_stderr = job.get("filelog-stderr", None)
    retry = job.get("retry", 0)
    mem = job.get("mem", None)
    cpu = job.get("cpu", None)
    emails = job.get("emails", "none")

    if not schedule and not continuous:
        wait = job.get("wait", False)
    else:
        wait = False

    op_run(
        api=api,
        name=name,
        command=command,
        schedule=schedule,
        continuous=continuous,
        image=image,
        wait=wait,
        no_filelog=no_filelog,
        filelog_stdout=filelog_stdout,
        filelog_stderr=filelog_stderr,
        retry=retry,
        mem=mem,
        cpu=cpu,
        emails=emails,
    )


def op_load(api: ApiClient, file: str, job_name: Optional[str]):
    try:
        with open(file) as f:
            jobslist = yaml.safe_load(f.read())
    except Exception as e:
        logging.error(f"couldn't read YAML file '{file}': {e}")
        sys.exit(1)

    logging.debug(f"loaded content from YAML file '{file}':")
    logging.debug(f"{jobslist}")

    changes = calculate_changes(
        api, jobslist, (lambda name: name == job_name) if job_name else None
    )

    if len(changes.delete) > 0 or len(changes.modify) > 0:
        _delete_and_wait(api, {*changes.delete, *changes.modify})

    for n, job in enumerate(jobslist, start=1):
        if "name" not in job:
            logging.error(f"Unable to load job number {n}. Missing configuration parameter name")
            sys.exit(1)

        name = job["name"]
        if name not in changes.add and name not in changes.modify:
            continue

        _load_job(api, job, n)


def op_restart(api: ApiClient, name: str):
    try:
        api.post(f"/restart/{name}")
    except Exception as e:
        logging.error(f"couldn't contact the API endpoint. Contact a Toolforge admin: {e}")
        sys.exit(1)

    logging.debug("job was restarted")


def main():
    args = parse_args()

    logging_format = "%(levelname)s: %(message)s"
    if args.debug:
        logging_level = logging.DEBUG
        logging_format = f"[%(asctime)s] [%(filename)s] {logging_format}"
    else:
        logging_level = logging.INFO

    logging.addLevelName(
        logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING)
    )
    logging.addLevelName(
        logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR)
    )
    logging.basicConfig(
        format=logging_format, level=logging_level, stream=sys.stdout, datefmt="%Y-%m-%d %H:%M:%S"
    )

    user = getpass.getuser()
    if not user.startswith("tools.") and not user.startswith("toolsbeta."):
        logging.warning(
            "not running as the tool account? Likely to fail. Perhaps you forgot `become <tool>`?"
        )

    try:
        api = ApiClient.create(args.cfg, args.cert, args.key)
    except TjfCliError:
        logging.exception("Failed to load configuration, please contact a Toolforge admin")
        sys.exit(1)

    logging.debug("session configuration generated correctly")

    if args.operation == "images":
        op_images(api)
    elif args.operation == "containers":
        # TODO: remove this after a few months
        logging.warning("the `containers` action is deprecated. Use `images` instead.")
        op_images(api)
    elif args.operation == "run":
        op_run(
            api=api,
            name=args.name,
            command=args.command,
            schedule=args.schedule,
            continuous=args.continuous,
            image=args.image,
            wait=args.wait,
            no_filelog=args.no_filelog,
            filelog_stdout=args.filelog_stdout,
            filelog_stderr=args.filelog_stderr,
            retry=args.retry,
            mem=args.mem,
            cpu=args.cpu,
            emails=args.emails,
        )
    elif args.operation == "show":
        op_show(api, args.name)
    elif args.operation == "delete":
        op_delete(api, args.name)
    elif args.operation == "list":
        output_format = args.output
        if args.long:
            logging.warning("the `--long` flag is deprecated, use `--output long` instead")
            output_format = ListDisplayMode.LONG
        op_list(api, output_format)
    elif args.operation == "flush":
        op_flush(api)
    elif args.operation == "load":
        op_load(api, args.file, args.job)
    elif args.operation == "restart":
        op_restart(api, args.name)

    logging.debug("-- end of operations")
