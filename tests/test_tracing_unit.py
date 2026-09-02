# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit tests for Phoenix tracing configuration and setup in tracing.py module.

Tracing is optional and additive, so these tests focus on the property that
matters most: no tracing failure may ever propagate into application startup.
"""
import builtins

import yaml
import pytest

import backend.tracing as tracing
from backend.config import Config


def _config(tmp_path, section):
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(section, f)
    return Config(config_path=str(config_file))


class TestTracingConfig:
    """Tests for Config.get_tracing_config."""

    def test_defaults_when_section_absent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TRACING_ENABLED", raising=False)
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_PROJECT_NAME", raising=False)

        result = _config(tmp_path, {"llm": {"url": "u", "model": "m"}}).get_tracing_config()

        assert result["enabled"] is False
        assert result["endpoint"] == "http://localhost:6006/v1/traces"
        assert result["project_name"] == "catalog-enrichment"

    def test_yaml_section_is_used(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TRACING_ENABLED", raising=False)
        monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
        monkeypatch.delenv("PHOENIX_PROJECT_NAME", raising=False)

        result = _config(tmp_path, {"tracing": {
            "enabled": True,
            "endpoint": "http://phoenix:6006/v1/traces",
            "project_name": "from-yaml",
        }}).get_tracing_config()

        assert result["enabled"] is True
        assert result["endpoint"] == "http://phoenix:6006/v1/traces"
        assert result["project_name"] == "from-yaml"

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACING_ENABLED", "true")
        monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://env:6006/v1/traces")
        monkeypatch.setenv("PHOENIX_PROJECT_NAME", "from-env")

        result = _config(tmp_path, {"tracing": {
            "enabled": False,
            "endpoint": "http://phoenix:6006/v1/traces",
            "project_name": "from-yaml",
        }}).get_tracing_config()

        assert result["enabled"] is True
        assert result["endpoint"] == "http://env:6006/v1/traces"
        assert result["project_name"] == "from-env"

    @pytest.mark.parametrize("value,expected", [
        ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
        ("false", False), ("0", False), ("no", False), ("", False), ("  ", False),
    ])
    def test_enabled_flag_parsing(self, tmp_path, monkeypatch, value, expected):
        monkeypatch.setenv("TRACING_ENABLED", value)
        result = _config(tmp_path, {"tracing": {"enabled": False}}).get_tracing_config()
        assert result["enabled"] is expected

    def test_env_false_overrides_yaml_true(self, tmp_path, monkeypatch):
        """An operator must be able to switch tracing off without editing config."""
        monkeypatch.setenv("TRACING_ENABLED", "false")
        result = _config(tmp_path, {"tracing": {"enabled": True}}).get_tracing_config()
        assert result["enabled"] is False


class TestSetupTracing:
    """Tests for setup_tracing / shutdown_tracing failure-safety."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        tracing._tracer_provider = None
        yield
        tracing._tracer_provider = None

    def test_disabled_is_a_noop(self, monkeypatch):
        monkeypatch.setattr(tracing, "get_config", lambda: _Cfg(False))
        assert tracing.setup_tracing() is False
        assert tracing._tracer_provider is None

    def test_register_failure_does_not_raise(self, monkeypatch):
        """A broken collector config must degrade to 'no traces', not an exception."""
        monkeypatch.setattr(tracing, "get_config", lambda: _Cfg(True))
        import phoenix.otel

        def boom(**kwargs):
            raise RuntimeError("collector unreachable")

        monkeypatch.setattr(phoenix.otel, "register", boom)
        assert tracing.setup_tracing() is False
        assert tracing._tracer_provider is None

    def test_import_error_that_is_not_importerror_does_not_raise(self, monkeypatch):
        """Regression: importing phoenix.otel runs the phoenix package body.

        With the full `arize-phoenix` server package installed alongside, that
        body raised `ValueError: mutable default <class 'mappingproxy'>` on
        Python 3.11, which escaped setup_tracing and killed API startup.
        Catching only ImportError is not enough.
        """
        monkeypatch.setattr(tracing, "get_config", lambda: _Cfg(True))
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "phoenix.otel":
                raise ValueError("mutable default <class 'mappingproxy'>")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert tracing.setup_tracing() is False
        assert tracing._tracer_provider is None

    def test_instrumentor_failure_does_not_raise(self, monkeypatch):
        """A broken instrumentor degrades that one path, not the whole app."""
        monkeypatch.setattr(tracing, "get_config", lambda: _Cfg(True))
        monkeypatch.setattr(tracing, "_instrument_openai", lambda tp: False)
        monkeypatch.setattr(tracing, "_instrument_langchain", lambda tp: False)

        import phoenix.otel

        monkeypatch.setattr(phoenix.otel, "register", lambda **kw: _FakeProvider())
        assert tracing.setup_tracing() is True

    def test_instrument_helpers_swallow_non_import_errors(self, monkeypatch):
        """The helpers themselves must not propagate a module-body failure."""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name.startswith("openinference.instrumentation"):
                raise RuntimeError("incompatible interpreter")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert tracing._instrument_openai(None) is False
        assert tracing._instrument_langchain(None) is False

    def test_setup_is_idempotent(self, monkeypatch):
        monkeypatch.setattr(tracing, "get_config", lambda: _Cfg(True))
        sentinel = object()
        tracing._tracer_provider = sentinel
        assert tracing.setup_tracing() is True
        assert tracing._tracer_provider is sentinel

    def test_shutdown_without_setup_does_not_raise(self):
        tracing.shutdown_tracing()

    def test_shutdown_flushes_before_shutdown(self):
        calls = []

        class Provider:
            def force_flush(self):
                calls.append("flush")

            def shutdown(self):
                calls.append("shutdown")

        tracing._tracer_provider = Provider()
        tracing.shutdown_tracing()

        assert calls == ["flush", "shutdown"]
        assert tracing._tracer_provider is None

    def test_shutdown_swallows_provider_errors(self):
        class Provider:
            def force_flush(self):
                raise RuntimeError("export failed")

            def shutdown(self):
                raise RuntimeError("never reached")

        tracing._tracer_provider = Provider()
        tracing.shutdown_tracing()
        assert tracing._tracer_provider is None


class _FakeProvider:
    """Stands in for the TracerProvider register() returns."""

    def force_flush(self):
        pass

    def shutdown(self):
        pass


class _Cfg:
    """Minimal stand-in for the Config object tracing.setup_tracing consumes."""

    def __init__(self, enabled):
        self._enabled = enabled

    def get_tracing_config(self):
        return {
            "enabled": self._enabled,
            "endpoint": "http://127.0.0.1:9/v1/traces",
            "project_name": "test-project",
        }
