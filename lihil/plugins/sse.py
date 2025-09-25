from typing import Any, Callable

from msgspec.json import encode as json_encode

from lihil.interface import UNSET, Record, Unset, is_set

class SSE(Record, kw_only=True):
    """
    Server-Sent Events (SSE) record type.
    """

    event: Unset[str] = UNSET
    data: Any
    id: Unset[str] = UNSET
    retry: Unset[int] = UNSET

    def encode_str(self, enc_hook: Callable[[Any], Any] | None = None) -> str:
        """
        Encode the SSE record to a string format.
        """

        lines: list[str] = []
        if is_set(self.event):
            lines.append(f"event: {self.event}")
        if is_set(self.id):
            lines.append(f"id: {self.id}")
        if is_set(self.retry):
            lines.append(f"retry: {self.retry}")

        # Ensure data is a string (JSON encode if not already a string)
        payload = (
            self.data
            if isinstance(self.data, str)
            else json_encode(self.data, enc_hook=enc_hook).decode()
        )

        payload_lines = payload.splitlines()
        for line in payload_lines:
            lines.append(f"data: {line}")
        return "\n".join(lines) + "\n\n"
