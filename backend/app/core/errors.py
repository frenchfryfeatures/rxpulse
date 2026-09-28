from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.security import AuthError


class AppError(Exception):
    """Domain error rendered as {"code", "message", ...extra} with an HTTP status."""

    def __init__(self, status: int, code: str, message: str, **extra: Any):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def not_found(entity: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{entity} not found")


def forbidden(message: str = "You do not have permission to perform this action", **extra: Any) -> AppError:
    return AppError(403, "FORBIDDEN", message, **extra)


def conflict(code: str, message: str, **extra: Any) -> AppError:
    return AppError(409, code, message, **extra)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "message": exc.message, **exc.extra}, status_code=exc.status)

    @app.exception_handler(AuthError)
    async def _auth_error(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            {"code": exc.code, "message": exc.message},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()
        ]
        msg = errors[0]["message"] if errors else "Invalid request"
        if errors and errors[0]["field"]:
            msg = f"{errors[0]['field']}: {msg}"
        return JSONResponse({"code": "VALIDATION_ERROR", "message": msg, "errors": errors}, status_code=422)
