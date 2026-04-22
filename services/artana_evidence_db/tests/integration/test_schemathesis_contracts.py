from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

from artana_evidence_db.app import create_app
from artana_evidence_db.tests.support import (
    build_graph_admin_headers,
    build_seeded_space_fixture,
    reset_graph_service_database,
)
from fastapi.testclient import TestClient
from schemathesis import openapi
from schemathesis.specs.openapi.checks import ignored_auth

if TYPE_CHECKING:
    from collections.abc import Iterator

    from schemathesis.schemas import APIOperation


@contextmanager
def _temporary_graph_testing_env() -> Iterator[None]:
    original_testing = os.environ.get("TESTING")
    os.environ["TESTING"] = "true"
    try:
        yield
    finally:
        if original_testing is None:
            os.environ.pop("TESTING", None)
        else:
            os.environ["TESTING"] = original_testing


with _temporary_graph_testing_env():
    reset_graph_service_database()
    schema = openapi.from_asgi("/openapi.json", create_app())


def _request_case(client: TestClient, case) -> object:
    request_kwargs = case.as_transport_kwargs(str(client.base_url))
    request_kwargs.pop("cookies", None)
    return client.request(**request_kwargs)


def _get_operation(path: str, method: str) -> APIOperation:
    for result in schema.get_all_operations():
        operation = result._value
        if operation.path == path and operation.method.upper() == method.upper():
            return operation
    message = f"Operation {method} {path} not found in graph-service OpenAPI schema"
    raise AssertionError(message)


HEALTH_OPERATION = _get_operation("/health", "GET")
ENTITY_CREATE_OPERATION = _get_operation("/v1/spaces/{space_id}/entities", "POST")
ADMIN_SPACE_LIST_OPERATION = _get_operation("/v1/admin/spaces", "GET")


def test_graph_service_health_contract() -> None:
    with _temporary_graph_testing_env():
        case = schema.make_case(
            operation=HEALTH_OPERATION,
            method=HEALTH_OPERATION.method,
            path=HEALTH_OPERATION.path,
        )
        with TestClient(create_app()) as client:
            response = _request_case(client, case)
            case.validate_response(response)


def test_graph_service_admin_space_list_contract() -> None:
    reset_graph_service_database()
    try:
        with _temporary_graph_testing_env():
            case = schema.make_case(
                operation=ADMIN_SPACE_LIST_OPERATION,
                method=ADMIN_SPACE_LIST_OPERATION.method,
                path=ADMIN_SPACE_LIST_OPERATION.path,
                headers=build_graph_admin_headers(),
            )
            with TestClient(create_app()) as client:
                response = _request_case(client, case)
                case.validate_response(response, excluded_checks=[ignored_auth])
    finally:
        reset_graph_service_database()


def test_graph_service_entity_create_contract_supports_aliases() -> None:
    fixture = build_seeded_space_fixture(slug_prefix="schemathesis-graph-service")

    with _temporary_graph_testing_env():
        case = schema.make_case(
            operation=ENTITY_CREATE_OPERATION,
            method=ENTITY_CREATE_OPERATION.method,
            path=ENTITY_CREATE_OPERATION.path,
            path_parameters={"space_id": str(fixture["space_id"])},
            headers=fixture["headers"],
            body={
                "entity_type": "GENE",
                "display_label": "MED13",
                "aliases": ["THRAP1"],
                "metadata": {},
                "identifiers": {},
            },
        )
        with TestClient(create_app()) as client:
            response = _request_case(client, case)
            case.validate_response(response, excluded_checks=[ignored_auth])
            assert "aliases" in response.json()["entity"]
