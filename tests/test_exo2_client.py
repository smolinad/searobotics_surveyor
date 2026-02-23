from unittest.mock import patch

import pytest

from surveyor_lib.clients.exo2_client import Exo2Client


@pytest.fixture
def exo2_mock_params():
    return {
        1: "Temperature (C)",
        2: "Temperature (F)",
        3: "Temperature (K)",
    }


@pytest.fixture
def exo2_client_with_mock_params(exo2_mock_params):
    with (
        patch.object(Exo2Client, "initialize_server_serial_connection"),
        patch.object(
            Exo2Client, "get_exo2_params", return_value=exo2_mock_params
        ),
    ):
        return Exo2Client(server_ip="127.0.0.1", server_port="5000")


def test_get_data_from_command_mocked(
    requests_mock, exo2_client_with_mock_params
):
    url = "http://127.0.0.1:5000/data"
    requests_mock.post(url, text="101 202 303")

    response = exo2_client_with_mock_params.get_data_from_command("para")
    assert response == "101 202 303"


def test_get_data_mocked(requests_mock, exo2_client_with_mock_params):
    url = "http://127.0.0.1:5000/data"
    requests_mock.get(url, text="1.0 2.0 3.0")

    response = exo2_client_with_mock_params._get_data()
    assert response == "1.0 2.0 3.0"


def test_get_data_full_pipeline(requests_mock, exo2_mock_params):
    url = "http://127.0.0.1:5000/data"

    # Setup param response (via "para" command)
    param_response = "1 2 3"
    requests_mock.post(url, text=param_response)

    # Setup sensor reading response
    data_response = "10.5 20.5 30.5"
    requests_mock.get(url, text=data_response)

    with patch.object(Exo2Client, "initialize_server_serial_connection"):
        client = Exo2Client(server_ip="127.0.0.1", server_port="5000")
        client.get_exo2_params = lambda: {
            1: "Temperature (C)",
            2: "Temperature (F)",
            3: "Temperature (K)",
        }

        data = client.get_data()
        assert data == {
            "Temperature (C)": 10.5,
            "Temperature (F)": 20.5,
            "Temperature (K)": 30.5,
        }
