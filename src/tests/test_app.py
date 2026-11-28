from collections.abc import Iterable

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import SupportTicket


class FakeTicketStore:
    def __init__(self, *, healthy: bool = True) -> None:
        self.tickets: list[SupportTicket] = []
        self.attachments: dict[str, bytes] = {}
        self.healthy = healthy

    def check_health(self) -> None:
        if not self.healthy:
            raise RuntimeError("Simulated storage outage")

    def list_tickets(self) -> Iterable[SupportTicket]:
        return list(self.tickets)

    def save_ticket(
        self,
        *,
        title: str,
        description: str,
        notes: str,
        attachment_name: str,
    ) -> SupportTicket:
        ticket = SupportTicket(
            id=f"ticket-{len(self.tickets) + 1}",
            title=title,
            description=description,
            department="IT Support",
            notes=notes,
            attachment_name=attachment_name,
        )
        self.tickets.append(ticket)
        return ticket

    def upload_attachment(self, *, filename: str, content: bytes) -> str:
        self.attachments[filename] = content
        return filename

    def delete_attachment(self, blob_name: str) -> None:
        self.attachments.pop(blob_name, None)

    def close(self) -> None:
        pass


def test_healthz_endpoint() -> None:
    client = TestClient(create_app(ticket_store=FakeTicketStore()))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_home_page_loads() -> None:
    client = TestClient(create_app(ticket_store=FakeTicketStore()))
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_demo_page_loads_with_csrf_cookie() -> None:
    client = TestClient(create_app(ticket_store=FakeTicketStore()))
    response = client.get("/demo")
    assert response.status_code == 200
    assert "hello_azd_csrf" in response.cookies


def test_submit_ticket_rejects_missing_csrf() -> None:
    client = TestClient(create_app(ticket_store=FakeTicketStore()))
    response = client.post(
        "/demo",
        data={
            "title": "Printer offline",
            "description": "3rd floor printer not responding",
            "notes": "Restarted power",
            "csrf_token": "invalid-token",
        },
    )
    assert response.status_code == 403


def test_healthz_returns_503_when_storage_unhealthy() -> None:
    client = TestClient(create_app(ticket_store=FakeTicketStore(healthy=False)))
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}
