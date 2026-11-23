from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupportTicket:
    id: str
    title: str
    description: str
    department: str
    notes: str
    attachment_name: str = ""
