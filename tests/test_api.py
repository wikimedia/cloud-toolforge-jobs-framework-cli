import pytest

from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.kubernetes_config import fake_kube_config
from tjf_cli.api import TjfCliHttpError, TjfCliHttpUserError, handle_http_exception


@pytest.fixture()
def mock_api_client(requests_mock) -> ToolforgeClient:
    server = "http://xyz"

    requests_mock.get(
        f"{server}/error/json/object/400/",
        status_code=400,
        json={
            "error": "Failed to create foo",
            "data": {"k8s_json": {"kind": "Foo"}, "k8s_error": "Invalid name foo"},
        },
    )
    requests_mock.get(
        f"{server}/error/json/object/403/",
        status_code=403,
        json={"error": "You do not have access to do that"},
    )
    requests_mock.get(
        f"{server}/error/json/object/500/",
        status_code=500,
        json={"error": "Failed to load running jobs", "data": {"k8s_error": "Timed out"}},
    )

    requests_mock.get(
        f"{server}/error/json/string/400/",
        status_code=400,
        json="HTTP 400: Failed to do something",
    )

    requests_mock.get(
        f"{server}/error/plaintext/400/", status_code=400, text="HTTP 400: Failed to do something"
    )

    yield ToolforgeClient(
        server=server,
        user_agent="xyz",
        kubeconfig=fake_kube_config(),
        exception_handler=handle_http_exception,
    )


@pytest.mark.parametrize(
    ["status_code", "expected_class"],
    [
        [400, TjfCliHttpUserError],
        [403, TjfCliHttpUserError],
        [500, TjfCliHttpError],
    ],
)
def test_make_http_error_picks_correct_class(
    mock_api_client: ToolforgeClient, status_code: int, expected_class
):
    with pytest.raises(expected_class) as excinfo:
        mock_api_client.get(f"error/json/object/{status_code}/")
    assert excinfo.type == expected_class  # to ensure exact match instead of subclasses
    assert excinfo.value.status_code == status_code


@pytest.mark.parametrize(["endpoint"], [["json/string"], ["plaintext"]])
def test_make_http_error_parses_string_error_messages(
    mock_api_client: ToolforgeClient, endpoint: str
):
    with pytest.raises(TjfCliHttpError) as excinfo:
        mock_api_client.get(f"error/{endpoint}/400/")
    assert excinfo.value.message == "HTTP 400: Failed to do something"


def test_make_http_error_parses_json_object_error_messages(mock_api_client: ToolforgeClient):
    with pytest.raises(TjfCliHttpError) as excinfo:
        mock_api_client.get("error/json/object/400/")
    assert excinfo.value.message == "Failed to create foo"
    assert excinfo.value.context == {"k8s_json": {"kind": "Foo"}, "k8s_error": "Invalid name foo"}
