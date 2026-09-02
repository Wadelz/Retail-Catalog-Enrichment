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

"""Arize Phoenix (OpenTelemetry) tracing for the catalog-enrichment backend.

Tracing is additive and strictly optional: every failure path here degrades to
"no traces" rather than raising, because an observability backend being down
must never stop the API from serving. Call `setup_tracing()` once at startup,
before any LLM client is constructed, and `shutdown_tracing()` on the way out
so buffered spans are flushed instead of dropped.

Two instrumentors cover the two ways this backend reaches a model:
  * OpenAI    - the raw `openai` SDK calls in vlm/image/policy/product_manual/
                reflection, all pointed at NVIDIA NIM endpoints.
  * LangChain - the deepagents/LangGraph agent in web_insights, including its
                tool and chain spans. deepagents is built on LangGraph, which
                the LangChain instrumentor already covers.
"""

import logging
from typing import Any, Optional

from backend.config import get_config

logger = logging.getLogger("catalog_enrichment.tracing")

_tracer_provider: Optional[Any] = None


class _NoOpTracer:
    """Stand-in tracer whose decorators pass functions through untouched.

    Modules decorate their orchestrators at import time, long before
    `setup_tracing()` runs, so importing this module must never fail. If
    openinference is missing or unimportable, decorated functions still need
    to be plain functions rather than an AttributeError at import.
    """

    def __getattr__(self, _name: str) -> Any:
        def passthrough(*args: Any, **kwargs: Any) -> Any:
            # Supports both bare `@tracer.chain` and called `@tracer.chain(...)`.
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return lambda func: func

        return passthrough


def _build_tracer() -> Any:
    try:
        from opentelemetry import trace as otel_trace
        from openinference.instrumentation import OITracer, TraceConfig

        # get_tracer() returns a proxy while no provider is registered, and it
        # resolves to whichever provider setup_tracing() installs later. That
        # is what lets these decorators be applied at import time and still
        # emit spans -- and produce nothing at all when tracing stays off.
        return OITracer(otel_trace.get_tracer(__name__), config=TraceConfig())
    except Exception as exc:  # pragma: no cover - depends on the install
        logger.warning(f"openinference tracer unavailable ({exc}); chain spans disabled")
        return _NoOpTracer()


#: Decorate an orchestrating function with ``@tracer.chain`` to group the LLM
#: calls it makes under one span. Safe to apply whether or not tracing is on.
tracer = _build_tracer()


def _instrument_openai(tracer_provider: Any) -> bool:
    try:
        from openinference.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        return True
    except ImportError:
        logger.warning("openinference-instrumentation-openai not installed; raw OpenAI SDK calls will not be traced")
        return False
    except Exception as exc:
        # Importing a third-party package runs its module body, which can fail
        # for reasons that are not ImportError (an incompatible interpreter, a
        # bad transitive dependency). None of that may reach startup.
        logger.warning(f"OpenAI instrumentation unavailable ({exc}); those calls will not be traced")
        return False


def _instrument_langchain(tracer_provider: Any) -> bool:
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        return True
    except ImportError:
        logger.warning("openinference-instrumentation-langchain not installed; the web-insights agent will not be traced")
        return False
    except Exception as exc:
        logger.warning(f"LangChain instrumentation unavailable ({exc}); the web-insights agent will not be traced")
        return False


def setup_tracing() -> bool:
    """Wire up Phoenix tracing. Returns True if spans will be exported.

    Safe to call more than once; subsequent calls are no-ops.
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return True

    config = get_config().get_tracing_config()
    if not config["enabled"]:
        logger.info("Tracing disabled; set TRACING_ENABLED=true to export spans to Phoenix")
        return False

    try:
        from phoenix.otel import register
    except ImportError:
        logger.warning("arize-phoenix-otel not installed; tracing is disabled. Install it with: uv sync")
        return False
    except Exception as exc:
        # Importing `phoenix.otel` executes the phoenix package body. If the
        # full `arize-phoenix` server package is also installed, that pulls in
        # modules which can raise on an unsupported interpreter -- observed as
        # `ValueError: mutable default <class 'mappingproxy'>` on Python 3.11
        # with arize-phoenix 20.5.0. A broken observability install must not
        # take the API down with it.
        logger.warning(f"Phoenix tracing unavailable ({exc}); continuing without tracing")
        return False

    try:
        # `register` builds the TracerProvider, exporter and resource in one
        # step. Hand-rolling those is the documented way to end up with spans
        # that never export, so let the SDK own it.
        tracer_provider = register(
            project_name=config["project_name"],
            endpoint=config["endpoint"],
            batch=True,
            auto_instrument=False,
            set_global_tracer_provider=True,
        )
    except Exception as exc:
        # A bad endpoint or an unreachable collector must not stop startup.
        logger.warning(f"Phoenix tracing setup failed ({exc}); continuing without tracing")
        return False

    traced = []
    if _instrument_openai(tracer_provider):
        traced.append("openai")
    if _instrument_langchain(tracer_provider):
        traced.append("langchain")

    if not traced:
        logger.warning("Phoenix registered but no instrumentors loaded; no LLM spans will be produced")

    _tracer_provider = tracer_provider
    logger.info(
        f"Phoenix tracing enabled: project={config['project_name']} "
        f"endpoint={config['endpoint']} instrumented={','.join(traced) or 'none'}"
    )
    return True


def shutdown_tracing() -> None:
    """Flush buffered spans and tear the exporter down.

    The batch span processor exports on a timer, so without an explicit flush
    the spans from the final requests before shutdown are simply lost.
    """
    global _tracer_provider
    if _tracer_provider is None:
        return
    try:
        _tracer_provider.force_flush()
        _tracer_provider.shutdown()
        logger.info("Phoenix tracing flushed and shut down")
    except Exception as exc:
        logger.warning(f"Phoenix tracing shutdown failed: {exc}")
    finally:
        _tracer_provider = None
