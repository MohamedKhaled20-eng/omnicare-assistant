"""FastAPI application factory. Startup ingests the policy and wires the agent."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from app.agent.graph import CustomerAssistant
from app.agent.llm import LLMConfigurationError, build_llm
from app.agent.tools import build_tools
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.rag.embeddings import Embedder, FastEmbedEmbedder
from app.rag.ingest import get_collection, ingest_policy
from app.rag.retriever import PolicyRetriever
from app.tools.claims import ClaimsRepository

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    llm: BaseChatModel | None = None,
    embedder: Embedder | None = None,
) -> FastAPI:
    """Build the app. `llm` / `embedder` can be injected (tests use offline fakes)."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)

        claims_repository = ClaimsRepository(settings.claims_file_path, settings.claims_seed_path)
        claims_repository.initialize()

        policy_embedder = embedder or FastEmbedEmbedder(settings.embedding_model)
        collection = get_collection(settings.chroma_path, settings.chroma_collection)
        ingest_policy(settings.policy_file_path, collection, policy_embedder)
        retriever = PolicyRetriever(collection, policy_embedder, top_k=settings.rag_top_k)

        app.state.assistant = None
        try:
            model = llm or build_llm(settings)
            tools = build_tools(claims_repository, retriever, max_distance=settings.rag_max_distance)
            app.state.assistant = CustomerAssistant(model, tools, settings.agent_recursion_limit)
            logger.info(
                "assistant ready",
                extra={"provider": settings.llm_provider, "model": settings.resolved_llm_model},
            )
        except LLMConfigurationError as exc:
            logger.warning("assistant disabled: %s", exc)
        yield

    app = FastAPI(
        title="OmniCare Financial Customer Assistant",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.assistant = None
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
        finally:
            request_id_ctx.reset(token)
        return response

    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
