# Learning Path: Udemy & Coursera

A suggested order for learning every technology used in this project, so you can read, change and extend the code with confidence. Each step ends with a concrete exercise **in this repo**.

> **Please verify before enrolling.** I could not open Udemy or Coursera from my build environment, so I have **not** confirmed that any individual course below is still available, current, or priced as you expect. Course titles are ones I know of by reputation; the **search links** are the reliable entry point (they always resolve), and the free official docs are listed as a no-cost fallback. Check ratings, "last updated" dates (prefer 2024+ for LangChain/LangGraph, which change fast) and look for Coursera "audit" / Udemy sales.

Estimated total: **8–10 weeks** at ~5 h/week. Skip stages you already know.

## Stage 1 — Python foundations (≈1–2 weeks)
Python 3.11+, type hints, `pathlib`, `dataclasses`, virtual envs, JSON, threading basics.

| Platform | Suggestion |
|---|---|
| Coursera | *Python for Everybody* (University of Michigan) — [search](https://www.coursera.org/search?query=python%20for%20everybody) |
| Udemy | *100 Days of Code: The Complete Python Pro Bootcamp* (Dr. Angela Yu) or *Complete Python Bootcamp* (Jose Portilla) — [search](https://www.udemy.com/courses/search/?q=python%20bootcamp) |
| Free | [docs.python.org tutorial](https://docs.python.org/3/tutorial/) |

**Exercise:** read `backend/app/tools/claims.py` and explain how the atomic write (`tempfile` + `os.replace`) protects the JSON file.

## Stage 2 — REST APIs with FastAPI and Pydantic v2 (≈1–2 weeks)
Routing, dependency injection, lifespan events, middleware/CORS, request/response models, validation errors, `pydantic-settings`.

| Platform | Suggestion |
|---|---|
| Udemy | *FastAPI – The Complete Course* (Eric Roby) — [search](https://www.udemy.com/courses/search/?q=fastapi) |
| Udemy | search "Pydantic V2" for focused short courses — [search](https://www.udemy.com/courses/search/?q=pydantic) |
| Coursera | search "FastAPI" / "REST API Python" (project-based courses) — [search](https://www.coursera.org/search?query=fastapi) |
| Free | [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/) · [Pydantic docs](https://docs.pydantic.dev/latest/) |

**Exercise:** add a `GET /api/v1/claims/{claim_id}` endpoint with a Pydantic response model (`app/api/routes.py`) and a test in `tests/test_api.py`.

## Stage 3 — Testing with pytest (≈1 week)
Fixtures, `parametrize`, `monkeypatch`, `tmp_path`, markers, test doubles, FastAPI `TestClient`.

| Platform | Suggestion |
|---|---|
| Udemy | search "pytest" — [search](https://www.udemy.com/courses/search/?q=pytest) |
| Coursera | search "Python testing" — [search](https://www.coursera.org/search?query=python%20testing%20pytest) |
| Free | [pytest docs](https://docs.pytest.org/) |

**Exercise:** read `backend/tests/conftest.py` and `tests/fakes.py`; add a scripted scenario to `FakeChatModel` for a new tool.

## Stage 4 — LLM & GenAI fundamentals (≈1–2 weeks)
Transformers at a high level, prompting, tool/function calling, hallucination, evaluation, prompt injection.

| Platform | Suggestion |
|---|---|
| Coursera | *Generative AI with Large Language Models* (DeepLearning.AI & AWS) — [search](https://www.coursera.org/search?query=generative%20ai%20with%20large%20language%20models) |
| Coursera | *Generative AI for Everyone* (DeepLearning.AI) — [search](https://www.coursera.org/search?query=generative%20ai%20for%20everyone) |
| Udemy | search "LLM engineering" / "prompt engineering" — [search](https://www.udemy.com/courses/search/?q=llm%20engineering) |
| Free | [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/) |

**Exercise:** read `backend/app/agent/prompts.py` and `safety/guardrails.py`; write three new injection phrases the regexes miss, then extend `tests/test_guardrails.py`.

## Stage 5 — Embeddings, vector stores and RAG (Chroma, fastembed) (≈1–2 weeks)
Embeddings, cosine similarity, chunking strategies, top-k retrieval, metadata, citations, RAG evaluation.

| Platform | Suggestion |
|---|---|
| Coursera | search "Retrieval Augmented Generation" — [search](https://www.coursera.org/search?query=retrieval%20augmented%20generation) |
| Udemy | search "RAG" and "vector database" / "ChromaDB" — [RAG](https://www.udemy.com/courses/search/?q=rag%20llm) · [ChromaDB](https://www.udemy.com/courses/search/?q=chromadb) |
| Free | [Chroma docs](https://docs.trychroma.com/) · [fastembed](https://qdrant.github.io/fastembed/) |

**Exercise:** add a second policy file, ingest both (loop in `main.py` lifespan), and add a test asserting citations name the right file.

## Stage 6 — Agents with LangChain & LangGraph (≈2 weeks)
Chat models, tool binding, state graphs, conditional edges, tool loops, checkpointers/memory, provider switching (Groq/OpenAI/Anthropic/Ollama).

| Platform | Suggestion |
|---|---|
| Udemy | *LangChain – Develop LLM powered applications* and *LangGraph – Develop LLM powered AI agents* (Eden Marco) — [LangChain](https://www.udemy.com/courses/search/?q=langchain) · [LangGraph](https://www.udemy.com/courses/search/?q=langgraph) |
| Coursera | search "LangChain" / "AI agents" — [LangChain](https://www.coursera.org/search?query=langchain) · [agents](https://www.coursera.org/search?query=ai%20agents) |
| Free | [LangGraph docs](https://langchain-ai.github.io/langgraph/) · [LangChain docs](https://python.langchain.com/) · [DeepLearning.AI short courses](https://www.deeplearning.ai/short-courses/) |
| Local models | [Ollama](https://ollama.com) · [Groq free tier](https://console.groq.com) |

**Exercise:** study `backend/app/agent/graph.py`; swap `MemorySaver` for a SQLite checkpointer so memory survives restarts.

## Stage 7 — Streamlit chat UI (≈2–3 days)
Session state, chat elements, expanders, spinners, `AppTest`.

| Platform | Suggestion |
|---|---|
| Udemy | search "Streamlit" — [search](https://www.udemy.com/courses/search/?q=streamlit) |
| Coursera | search "Streamlit" — [search](https://www.coursera.org/search?query=streamlit) |
| Free | [Streamlit docs: build a chatbot](https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps) |

**Exercise:** add a "Download transcript" button to `frontend/app.py`.

## Stage 8 — Docker & Compose (≈1 week)
Images, multi-stage/caching, build-time downloads, volumes, healthchecks, networking, env files, non-root users.

| Platform | Suggestion |
|---|---|
| Udemy | *Docker & Kubernetes: The Practical Guide* (Maximilian Schwarzmüller) or *Docker Mastery* (Bret Fisher) — [search](https://www.udemy.com/courses/search/?q=docker%20compose) |
| Coursera | search "Docker" / "containers" (e.g. IBM, Google Cloud offerings) — [search](https://www.coursera.org/search?query=docker%20containers) |
| Free | [Docker get-started](https://docs.docker.com/get-started/) · [Compose docs](https://docs.docker.com/compose/) |

**Exercise:** read both Dockerfiles and `docker-compose.yml`; add a `read_only: true` root filesystem to the backend and fix what breaks.

## Stage 9 — Putting it together: production concerns (ongoing)
Authentication, observability, rate limiting, persistent checkpointers, LLM evaluation. Search "FastAPI authentication OAuth2 JWT" and "LLM evaluation / observability" on both platforms, and see *Assumptions & limitations* in the README for the concrete gaps in this prototype.

## Suggested weekly plan

| Week | Focus |
|---|---|
| 1 | Stage 1 + start Stage 2 |
| 2 | Stage 2 + Stage 3 |
| 3 | Stage 4 |
| 4–5 | Stage 5 (RAG) |
| 6–7 | Stage 6 (LangChain/LangGraph) |
| 8 | Stages 7 + 8 |
| 9+ | Stage 9 and the exercises above |
