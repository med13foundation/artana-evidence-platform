"""Regression tests for graph-intelligence factory delegation."""

from __future__ import annotations

from types import SimpleNamespace

from src.infrastructure.dependency_injection.service_factories import (
    ApplicationServiceFactoryMixin,
)


class _Factory(ApplicationServiceFactoryMixin):
    """Minimal concrete factory for delegation tests."""


def test_create_graph_connection_service_delegates_to_graph_service_composition(
    monkeypatch,
) -> None:
    factory = _Factory()
    session = object()
    expected_service = object()
    captured: dict[str, object] = {}

    def _build(session_arg: object) -> object:
        captured["session"] = session_arg
        return expected_service

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.build_graph_connection_service",
        _build,
    )

    result = factory.create_graph_connection_service(session)

    assert result is expected_service
    assert captured == {"session": session}


def test_create_graph_search_service_delegates_to_graph_service_composition(
    monkeypatch,
) -> None:
    factory = _Factory()
    session = object()
    expected_service = object()
    captured: dict[str, object] = {}

    def _build(session_arg: object) -> object:
        captured["session"] = session_arg
        return expected_service

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.build_graph_search_service",
        _build,
    )

    result = factory.create_graph_search_service(session)

    assert result is expected_service
    assert captured == {"session": session}


def test_get_entity_recognition_agent_uses_ai_owned_configs(monkeypatch) -> None:
    factory = _Factory()
    factory._entity_recognition_agent = None  # type: ignore[attr-defined]
    factory._graph_domain_pack = None  # type: ignore[attr-defined]
    factory._graph_domain_ai_config = None  # type: ignore[attr-defined]
    prompt_config = object()
    payload_config = object()
    pack = SimpleNamespace(name="biomedical")
    ai_config = SimpleNamespace(
        entity_recognition_prompt=prompt_config,
        entity_recognition_payload=payload_config,
    )
    captured: dict[str, object] = {}
    expected_agent = object()

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.create_graph_domain_pack",
        lambda: pack,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.create_graph_domain_ai_config",
        lambda pack_name: ai_config,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5-mini",
            ),
        ),
    )

    def _build_adapter(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected_agent

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.ArtanaEntityRecognitionAdapter",
        _build_adapter,
    )

    result = factory.get_entity_recognition_agent()

    assert result is expected_agent
    assert captured["prompt_config"] is prompt_config
    assert captured["payload_config"] is payload_config
    assert captured["model"] == "openai:gpt-5-mini"


def test_get_extraction_agent_uses_ai_owned_configs(monkeypatch) -> None:
    factory = _Factory()
    factory._extraction_agent = None  # type: ignore[attr-defined]
    factory._graph_domain_pack = None  # type: ignore[attr-defined]
    factory._graph_domain_ai_config = None  # type: ignore[attr-defined]
    prompt_config = object()
    payload_config = object()
    pack = SimpleNamespace(name="biomedical")
    ai_config = SimpleNamespace(
        extraction_prompt=prompt_config,
        extraction_payload=payload_config,
    )
    captured: dict[str, object] = {}
    expected_agent = object()

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.create_graph_domain_pack",
        lambda: pack,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.create_graph_domain_ai_config",
        lambda pack_name: ai_config,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5-mini",
            ),
        ),
    )

    def _build_adapter(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected_agent

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.ArtanaExtractionAdapter",
        _build_adapter,
    )

    result = factory.get_extraction_agent()

    assert result is expected_agent
    assert captured["prompt_config"] is prompt_config
    assert captured["payload_config"] is payload_config
    assert captured["model"] == "openai:gpt-5-mini"


def test_graph_service_factory_caches_graph_domain_pack(monkeypatch) -> None:
    factory = _Factory()
    factory._entity_recognition_agent = None  # type: ignore[attr-defined]
    factory._extraction_agent = None  # type: ignore[attr-defined]
    factory._graph_domain_pack = None  # type: ignore[attr-defined]
    factory._graph_domain_ai_config = None  # type: ignore[attr-defined]
    pack = SimpleNamespace(name="biomedical")
    ai_config = SimpleNamespace(
        pack_name="biomedical",
        entity_recognition_prompt=object(),
        entity_recognition_payload=object(),
        extraction_prompt=object(),
        extraction_payload=object(),
    )
    resolve_calls: list[object] = []

    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.create_graph_domain_pack",
        lambda: resolve_calls.append(object()) or pack,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.create_graph_domain_ai_config",
        lambda pack_name: ai_config,
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5-mini",
            ),
        ),
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.ArtanaEntityRecognitionAdapter",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        "src.infrastructure.dependency_injection.service_factories.ArtanaExtractionAdapter",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

    entity_agent = factory.get_entity_recognition_agent()
    extraction_agent = factory.get_extraction_agent()

    assert entity_agent.prompt_config is ai_config.entity_recognition_prompt
    assert extraction_agent.prompt_config is ai_config.extraction_prompt
    assert len(resolve_calls) == 1
