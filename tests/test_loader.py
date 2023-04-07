# (C) 2022 Taavi Väänänen <hi@taavi.wtf>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
from typing import Callable, Dict, Optional, Set

import pytest
import requests

from tjf_cli.api import ApiClient
from tjf_cli.loader import calculate_changes, jobs_are_same

SIMPLE_TEST_JOB = {
    "name": "test-job",
    "command": "./myothercommand.py -v",
    "image": "bullseye",
    "emails": "none",
}

SIMPLE_TEST_JOB_API = {
    "name": "test-job",
    "cmd": "./myothercommand.py -v",
    "image": "bullseye",
    "image_state": "stable",
    "filelog": "True",
    "status_short": "Running",
    "status_long": (
        "Last run at 2022-10-08T09:28:37Z. Pod in 'Running' phase. "
        "State 'running'. Started at '2022-10-08T09:28:39Z'."
    ),
    "emails": "none",
    "retry": 0,
}


@pytest.fixture
def mock_api(requests_mock) -> ApiClient:
    api_base_url = "http://nonexistent"

    session = requests.Session()
    requests_mock.get(f"{api_base_url}/list/", json=[SIMPLE_TEST_JOB_API])

    class FakeApi:
        def __init__(self, session, api_url) -> None:
            self.session = session
            self.api_url = api_url

    yield FakeApi(session, api_base_url)


def merge(first: Dict, second: Dict, unset=None) -> Dict:
    data = {**first, **second}
    if unset:
        for key in unset:
            del data[key]
    return data


@pytest.mark.parametrize(
    "config,api,expected",
    [
        [SIMPLE_TEST_JOB, SIMPLE_TEST_JOB_API, True],
        # basic parameter change
        [merge(SIMPLE_TEST_JOB, {"image": "tf-foobar"}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"image": "tf-foobar"}), False],
        # optional parameter change
        [merge(SIMPLE_TEST_JOB, {"schedule": "* * * * *"}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"schedule": "* * * * *"}), False],
        # emails are complicated
        [merge(SIMPLE_TEST_JOB, {}, unset=["emails"]), SIMPLE_TEST_JOB_API, True],
        [merge(SIMPLE_TEST_JOB, {"emails": "onfailure"}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"emails": "onfailure"}), False],
        # so is logging
        [merge(SIMPLE_TEST_JOB, {"no-filelog": False}), SIMPLE_TEST_JOB_API, True],
        [merge(SIMPLE_TEST_JOB, {"no-filelog": True}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"filelog": "False"}), False],
        # and retries
        [merge(SIMPLE_TEST_JOB, {"retry": 0}), SIMPLE_TEST_JOB_API, True],
        [merge(SIMPLE_TEST_JOB, {"retry": 1}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"retry": 2}), False],
        # filelog_stdout
        [
            merge(SIMPLE_TEST_JOB, {"filelog-stdout": "xyz"}),
            merge(SIMPLE_TEST_JOB_API, {"filelog_stdout": "xyz"}),
            True,
        ],
        [merge(SIMPLE_TEST_JOB, {"filelog-stdout": "xyz"}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"filelog_stdout": "xyz"}), False],
        # filelog_stderr
        [
            merge(SIMPLE_TEST_JOB, {"filelog-stderr": "xyz"}),
            merge(SIMPLE_TEST_JOB_API, {"filelog_stderr": "xyz"}),
            True,
        ],
        [merge(SIMPLE_TEST_JOB, {"filelog-stderr": "xyz"}), SIMPLE_TEST_JOB_API, False],
        [SIMPLE_TEST_JOB, merge(SIMPLE_TEST_JOB_API, {"filelog_stderr": "xyz"}), False],
    ],
)
def test_jobs_are_same(config: Dict, api: Dict, expected: bool):
    assert jobs_are_same(config, api) == expected


@pytest.mark.parametrize(
    "jobs_data,filter,add,modify,delete,yaml_warning",
    [
        # simple cases
        [[], None, set(), set(), {"test-job"}, False],
        [[SIMPLE_TEST_JOB], None, set(), set(), set(), False],
        # job data changes
        [[merge(SIMPLE_TEST_JOB, {"mem": "2Gi"})], None, set(), {"test-job"}, set(), False],
        # rename
        [
            [merge(SIMPLE_TEST_JOB, {"name": "foobar"})],
            None,
            {"foobar"},
            set(),
            {"test-job"},
            False,
        ],
        # configured jobs do not match filter
        [[SIMPLE_TEST_JOB], lambda s: False, set(), set(), set(), False],
        # filter set and matches
        [[SIMPLE_TEST_JOB], lambda s: True, set(), set(), set(), False],
        [
            [merge(SIMPLE_TEST_JOB, {"mem": "2Gi"})],
            lambda s: True,
            set(),
            {"test-job"},
            set(),
            False,
        ],
        # filter and rename
        [
            [merge(SIMPLE_TEST_JOB, {"name": "foobar"})],
            lambda s: s == "foobar",
            {"foobar"},
            set(),
            set(),
            False,
        ],
        [
            [merge(SIMPLE_TEST_JOB, {"name": "foobar"})],
            lambda s: s == "test-job",
            set(),
            set(),
            {"test-job"},
            False,
        ],
        # unknown yaml keys
        [[merge(SIMPLE_TEST_JOB, {"xyz": "xyz"})], None, set(), set(), set(), True],
    ],
)
def test_calculate_changes(
    caplog,
    mock_api: ApiClient,
    jobs_data: Dict,
    filter: Optional[Callable[[str], bool]],
    add: Set[str],
    modify: Set[str],
    delete: Set[str],
    yaml_warning,
):
    result = calculate_changes(mock_api, jobs_data, filter)

    assert result.add == add
    assert result.modify == modify
    assert result.delete == delete
    assert yaml_warning == ("Unknown key" in caplog.text)
