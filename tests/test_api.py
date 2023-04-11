import pytest
import requests

from tjf_cli.api import ApiClient, TjfCliHttpError, TjfCliHttpUserError


@pytest.fixture()
def mock_api_client(requests_mock) -> ApiClient:
    api_url = "http://nonexistent"

    session = requests.Session()
    requests_mock.get(
        f"{api_url}/error/json/object/400/",
        status_code=400,
        json={
            "error": "Failed to create foo",
            "data": {"k8s_json": {"kind": "Foo"}, "k8s_error": "Invalid name foo"},
        },
    )
    requests_mock.get(
        f"{api_url}/error/json/object/403/",
        status_code=403,
        json={"error": "You do not have access to do that"},
    )
    requests_mock.get(
        f"{api_url}/error/json/object/500/",
        status_code=500,
        json={"error": "Failed to load running jobs", "data": {"k8s_error": "Timed out"}},
    )

    requests_mock.get(
        f"{api_url}/error/json/string/400/",
        status_code=400,
        json="HTTP 400: Failed to do something",
    )

    requests_mock.get(
        f"{api_url}/error/plaintext/400/", status_code=400, text="HTTP 400: Failed to do something"
    )

    yield ApiClient(session=session, api_url=api_url)


@pytest.mark.parametrize(
    ["status_code", "expected_class"],
    [
        [400, TjfCliHttpUserError],
        [403, TjfCliHttpUserError],
        [500, TjfCliHttpError],
    ],
)
def test_make_http_error_picks_correct_class(
    mock_api_client: ApiClient, status_code: int, expected_class
):
    with pytest.raises(expected_class) as excinfo:
        mock_api_client.get(f"/error/json/object/{status_code}/")
    assert excinfo.type == expected_class  # to ensure exact match instead of subclasses
    assert excinfo.value.status_code == status_code


@pytest.mark.parametrize(["endpoint"], [["json/string"], ["plaintext"]])
def test_make_http_error_parses_string_error_messages(mock_api_client: ApiClient, endpoint: str):
    with pytest.raises(TjfCliHttpError) as excinfo:
        mock_api_client.get(f"/error/{endpoint}/400/")
    assert excinfo.value.message == "HTTP 400: Failed to do something"


def test_make_http_error_parses_json_object_error_messages(mock_api_client: ApiClient):
    with pytest.raises(TjfCliHttpError) as excinfo:
        mock_api_client.get("/error/json/object/400/")
    assert excinfo.value.message == "Failed to create foo"
    assert excinfo.value.context == {"k8s_json": {"kind": "Foo"}, "k8s_error": "Invalid name foo"}
