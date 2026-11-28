from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from .config import Settings
from .models import SupportTicket

PARTITION_KEY = "helpdesk"


class TicketStore(Protocol):
    def list_tickets(self) -> Iterable[SupportTicket]: ...

    def save_ticket(
        self,
        *,
        title: str,
        description: str,
        notes: str,
        attachment_name: str,
    ) -> SupportTicket: ...

    def upload_attachment(self, *, filename: str, content: bytes) -> str: ...

    def delete_attachment(self, blob_name: str) -> None: ...

    def check_health(self) -> None: ...

    def close(self) -> None: ...


class AzureTicketStore:
    def __init__(self, settings: Settings) -> None:
        self._credential = DefaultAzureCredential(
            managed_identity_client_id=settings.managed_identity_client_id,
            exclude_managed_identity_credential=settings.managed_identity_client_id is None,
        )
        self._blob_service = BlobServiceClient(
            account_url=settings.storage_url,
            credential=self._credential,
        )
        table_service = TableServiceClient(
            endpoint=settings.tables_url,
            credential=self._credential,
        )
        self._table_client = table_service.get_table_client("tickets")

    def check_health(self) -> None:
        self._blob_service.get_container_client("attachments").get_container_properties()
        next(self._table_client.query_entities("PartitionKey eq 'healthcheck'", select=["RowKey"]), None)


    def list_tickets(self) -> Iterable[SupportTicket]:
        entities = self._table_client.query_entities("PartitionKey eq 'helpdesk'")
        return [
            SupportTicket(
                id=entity["RowKey"],
                title=entity.get("title", ""),
                description=entity.get("description", ""),
                department=entity["PartitionKey"],
                notes=entity.get("notes", ""),
                attachment_name=entity.get("attachmentName", ""),
            )
            for entity in entities
        ]

    def save_ticket(
        self,
        *,
        title: str,
        description: str,
        notes: str,
        attachment_name: str,
    ) -> SupportTicket:
        ticket = SupportTicket(
            id=uuid4().hex[:8],
            title=title,
            description=description,
            department=PARTITION_KEY,
            notes=notes,
            attachment_name=attachment_name,
        )
        self._table_client.upsert_entity(
            {
                "PartitionKey": ticket.department,
                "RowKey": ticket.id,
                "title": ticket.title,
                "description": ticket.description,
                "notes": ticket.notes,
                "attachmentName": ticket.attachment_name,
            }
        )
        return ticket

    def upload_attachment(self, *, filename: str, content: bytes) -> str:
        safe_filename = Path(filename).name
        if not safe_filename or safe_filename in {".", ".."}:
            raise ValueError("The attachment filename is invalid.")
        blob_name = f"{uuid4().hex}-{safe_filename}"
        blob_client = self._blob_service.get_blob_client(
            container="attachments",
            blob=blob_name,
        )
        blob_client.upload_blob(BytesIO(content), overwrite=False)
        return blob_name

    def delete_attachment(self, blob_name: str) -> None:
        blob_client = self._blob_service.get_blob_client(
            container="attachments",
            blob=blob_name,
        )
        blob_client.delete_blob()

    def close(self) -> None:
        self._blob_service.close()
        self._table_client.close()
        self._credential.close()
