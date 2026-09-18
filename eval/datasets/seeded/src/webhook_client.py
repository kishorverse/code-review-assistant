"""Deliver audit events and fetch profile images."""

import json

import requests

AUDIT_ENDPOINT = "https://audit.internal.example/events"


def deliver(event: dict[str, object]) -> bool:
    """POST ``event`` to the audit service; True if it was accepted."""
    response = requests.post(
        AUDIT_ENDPOINT,
        data=json.dumps(event),
        headers={"Content-Type": "application/json"},
        verify=False,
    )
    return response.status_code == 200


def fetch_avatar(url: str) -> bytes:
    """Download the avatar image that a user linked in their profile."""
    return requests.get(url, timeout=10).content
