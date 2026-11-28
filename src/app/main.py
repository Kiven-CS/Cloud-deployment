import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .storage import AzureTicketStore, TicketStore

APP_DIR = Path(__file__).parent
MAX_ATTACHMENT_SIZE = 512_000
MAX_REQUEST_SIZE = MAX_ATTACHMENT_SIZE + 64_000
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 1_000
MAX_NOTES_LENGTH = 1_000
CSRF_COOKIE_NAME = "hello_azd_csrf"
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=APP_DIR / "templates")


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_size:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                response = PlainTextResponse("Content-Length must be an integer.", status_code=400)
                await response(scope, receive, send)
                return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_body_size:
                await self._reject(scope, receive, send)
                return
            more_body = message.get("more_body", False)

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("Request body is too large.", status_code=413)
        await response(scope, receive, send)


def create_app(ticket_store: TicketStore | None = None) -> FastAPI:
    store = ticket_store or AzureTicketStore(Settings.from_environment())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        store.close()

    application = FastAPI(
        title="Hello AZD",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_SIZE)

    @application.middleware("http")
    async def secure_responses(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'; object-src 'none'"
        )
        response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    application.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    @application.get("/healthz", include_in_schema=False)
    def health() -> Response:
        try:
            store.check_health()
        except Exception:
            logger.exception("Health check failed")
            return PlainTextResponse(
                '{"status": "unhealthy"}',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                media_type="application/json",
            )
        return PlainTextResponse(
            '{"status": "healthy"}',
            status_code=status.HTTP_200_OK,
            media_type="application/json",
        )

    @application.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="home.html")

    @application.get("/demo", response_class=HTMLResponse)
    def demo(request: Request, success: bool = False) -> HTMLResponse:
        try:
            tickets = list(store.list_tickets())
            error = None
        except Exception:
            logger.exception("Failed to load support tickets")
            tickets = []
            error = "Unable to load tickets. Please try again later."
        return _render_demo(
            request,
            tickets=tickets,
            success=success,
            error=error,
        )

    @application.post("/demo", response_class=HTMLResponse)
    def submit_ticket(
        request: Request,
        title: Annotated[str, Form(min_length=1, max_length=MAX_TITLE_LENGTH)],
        description: Annotated[str, Form(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)],
        notes: Annotated[str, Form(min_length=1, max_length=MAX_NOTES_LENGTH)],
        csrf_token: Annotated[str, Form(min_length=1)],
        attachment: Annotated[UploadFile | None, File()] = None,
    ) -> Response:
        expected_token = request.cookies.get(CSRF_COOKIE_NAME)
        if not expected_token or not compare_digest(expected_token, csrf_token):
            return _render_form_error(
                request,
                store,
                "The form expired. Refresh the page and try again.",
                status.HTTP_403_FORBIDDEN,
            )

        title = title.strip()
        description = description.strip()
        notes = notes.strip()
        if not title or not description or not notes:
            return _render_form_error(
                request,
                store,
                "Title, description, and notes are required.",
                status.HTTP_400_BAD_REQUEST,
            )

        attachment_name = ""
        try:
            if attachment and attachment.filename:
                filename = Path(attachment.filename).name
                if not filename or filename in {".", ".."}:
                    return _render_form_error(
                        request,
                        store,
                        "The attachment filename is invalid.",
                        status.HTTP_400_BAD_REQUEST,
                    )
                content = attachment.file.read(MAX_ATTACHMENT_SIZE + 1)
                if len(content) > MAX_ATTACHMENT_SIZE:
                    return _render_form_error(
                        request,
                        store,
                        "Attachments must be smaller than 0.5 MB.",
                        status.HTTP_400_BAD_REQUEST,
                    )
                attachment_name = store.upload_attachment(
                    filename=filename,
                    content=content,
                )

            store.save_ticket(
                title=title,
                description=description,
                notes=notes,
                attachment_name=attachment_name,
            )
        except Exception:
            logger.exception("Failed to submit a support ticket")
            if attachment_name:
                try:
                    store.delete_attachment(attachment_name)
                except Exception:
                    logger.exception("Failed to delete an orphaned attachment")
            return _render_form_error(
                request,
                store,
                "Unable to submit the ticket. Please try again later.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        finally:
            if attachment:
                attachment.file.close()

        return RedirectResponse(url="/demo?success=true", status_code=status.HTTP_303_SEE_OTHER)

    return application


def _render_form_error(
    request: Request,
    store: TicketStore,
    message: str,
    status_code: int,
) -> HTMLResponse:
    try:
        tickets = list(store.list_tickets())
    except Exception:
        logger.exception("Failed to reload support tickets")
        tickets = []
    return _render_demo(
        request,
        tickets=tickets,
        success=False,
        error=message,
        status_code=status_code,
    )


def _render_demo(
    request: Request,
    *,
    tickets: list,
    success: bool,
    error: str | None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    csrf_token = token_urlsafe(32)
    response = templates.TemplateResponse(
        request=request,
        name="demo.html",
        context={
            "tickets": tickets,
            "success": success,
            "error": error,
            "csrf_token": csrf_token,
        },
        status_code=status_code,
    )
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=True,
        max_age=3_600,
        samesite="strict",
        secure=request.url.scheme == "https" or forwarded_proto == "https",
    )
    return response


app = create_app()
