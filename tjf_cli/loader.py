# (C) 2022 Taavi Väänänen <hi@taavi.wtf>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
import sys
from dataclasses import dataclass
from logging import getLogger
from typing import Callable, Dict, Optional, Set

from tjf_cli.api import ApiClient

LOGGER = getLogger(__name__)

# TODO: perhaps this could be extracted from argparse?
KNOWN_YAML_KEYS = [
    "name",
    "command",
    "schedule",
    "continuous",
    "image",
    "mem",
    "cpu",
    "retry",
    "emails",
    "wait",
    "no-filelog",
    "filelog-stdout",
    "filelog-stderr",
]


@dataclass
class LoadChanges:
    delete: Set[str]
    add: Set[str]
    modify: Set[str]


def jobs_are_same(job_config: Dict, api_obj: Dict) -> bool:
    """Determines if a job api object matches its configuration."""

    # TODO: some renames to make things easier. See also T327280
    api_obj["command"] = api_obj["cmd"]
    api_obj["memory"] = api_obj.get("mem", None)
    api_obj["filelog-stdout"] = api_obj.get("filelog_stdout", None)
    api_obj["filelog-stderr"] = api_obj.get("filelog_stderr", None)

    # TODO: explicitely setting default CPU/memory should not count as a difference
    dont_evaluate_here = ["name", "emails", "no-filelog", "wait", "retry"]
    keys = [k for k in KNOWN_YAML_KEYS if k not in dont_evaluate_here]
    for key in keys:
        if api_obj.get(key, None) != job_config.get(key, None):
            LOGGER.debug(
                "currently existing job %s has different '%s' than the definition",
                api_obj["name"],
                key,
            )
            return False

    emails_config = job_config.get("emails", "none")
    if api_obj["emails"] != emails_config:
        LOGGER.debug(
            "currently existing job %s has different 'emails' than the definition", api_obj["name"]
        )
        return False

    retry_config = job_config.get("retry", 0)
    if api_obj["retry"] != retry_config:
        LOGGER.debug(
            "currently existing job %s has different 'retry' than the definition", api_obj["name"]
        )
        return False

    # TODO: make the api emit proper json booleans, See also T327280
    filelog_api = api_obj.get("filelog") in (True, "True")
    filelog_config = not job_config.get("no-filelog", False)
    if filelog_config != filelog_api:
        LOGGER.debug(
            "currently existing job %s has different 'no-filelog' than the definition",
            api_obj["name"],
        )
        return False

    LOGGER.debug("currently existing job %s matches its definition", api_obj["name"])
    return True


def calculate_changes(
    conf: ApiClient, configured_job_data: Dict, filter: Optional[Callable[[str], bool]]
) -> LoadChanges:
    for job in configured_job_data:
        for key in job:
            if key not in KNOWN_YAML_KEYS:
                LOGGER.warning(f"Unknown key '{key}' in job '{job['name']}' definition")

    wanted_jobs = {
        job["name"]: job for job in configured_job_data if not filter or filter(job["name"])
    }

    try:
        response = conf.session.get(f"{conf.api_url}/list/")
        response.raise_for_status()
        current_job_data = response.json()
    except Exception:
        LOGGER.exception("Could not load data about current jobs. Contact a Toolforge admin.")
        sys.exit(1)

    current_jobs = {
        job["name"]: job for job in current_job_data if not filter or filter(job["name"])
    }

    to_delete = current_jobs.keys() - wanted_jobs.keys()
    to_add = wanted_jobs.keys() - current_jobs.keys()

    to_modify = set()
    for job_name, job_data in wanted_jobs.items():
        if job_name in current_jobs and not jobs_are_same(job_data, current_jobs[job_name]):
            to_modify.add(job_name)

    return LoadChanges(to_delete, to_add, to_modify)
