"""LodgeLedger API: FastAPI over Supabase PostgreSQL.

Run:  uvicorn main:app --port 8080 --env-file .env
Docs: http://localhost:8080/docs
"""

import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from config import get_config
from database import Conflict, InvalidReference, NotFound, PostgresRepository, Unavailable, get_repo
from routes import auth, budgets, categories, dashboard, savings, transactions

log = logging.getLogger("lodgeledger")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    # Tests set app.state.repo themselves; only build a real pool when none is set.
    if getattr(app.state, "repo", None) is None:
        app.state.repo = None
        if config.database_url:
            app.state.repo = PostgresRepository(config.database_url)
            app.state.repo.open()
            log.info("database: configured")  # never the URL: it holds the password
        else:
            log.warning("database: DATABASE_URL not set; data endpoints will return 503")
    yield
    if isinstance(app.state.repo, PostgresRepository):
        app.state.repo.close()


app = FastAPI(
    title="LodgeLedger API",
    description="Financial risk and budget monitoring for the LodgeLedger dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.repo = None

@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    # ALLOW_WRITES=false freezes a deployment: every write, sign-ups included, is refused.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not get_config().allow_writes:
        return JSONResponse({"error": "This deployment is read-only"}, status_code=403)
    return await call_next(request)


# Added after the guard so CORS is the outer layer and even a 403 carries CORS headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_config().cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


# --- one error shape everywhere: {"error": "..."} -----------------------------

def _error(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


def _field(loc) -> str:
    # ("body", "amount") -> "amount"; ("query", "month") -> "month"
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "request"


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    details = []
    for e in exc.errors():
        if e["type"] == "json_invalid":
            return _error(422, "Request body is not valid JSON")
        message = e["msg"].removeprefix("Value error, ")
        details.append({"field": _field(e["loc"]), "message": message})
    first = details[0]
    return _error(422, f"{first['field']}: {first['message']}", details=details)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return _error(exc.status_code, str(exc.detail))


@app.exception_handler(NotFound)
async def not_found(request: Request, exc: NotFound):
    return _error(404, str(exc))


@app.exception_handler(Conflict)
async def conflict(request: Request, exc: Conflict):
    return _error(409, str(exc))


@app.exception_handler(InvalidReference)
async def invalid_reference(request: Request, exc: InvalidReference):
    return _error(422, str(exc))


@app.exception_handler(Unavailable)
async def unavailable(request: Request, exc: Unavailable):
    return _error(503, str(exc))


@app.exception_handler(psycopg.IntegrityError)
async def constraint_error(request: Request, exc: psycopg.IntegrityError):
    # A database constraint the API validation did not anticipate. Log the
    # constraint name for us; tell the client only that the value was refused.
    log.warning("constraint violation: %s", type(exc).__name__)
    return _error(422, "The value was rejected by a database constraint")


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return _error(500, "Internal server error")


# --- routes ------------------------------------------------------------------

@app.get("/api/health", tags=["health"])
def health(request: Request):
    """200 when the API and database are reachable, 503 otherwise."""
    try:
        get_repo(request).ping()
        return {"status": "ok", "database": "ok"}
    except Unavailable:
        return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)


for module in (auth, categories, transactions, budgets, dashboard, savings):
    app.include_router(module.router)
