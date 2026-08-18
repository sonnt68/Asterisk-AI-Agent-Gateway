"""Transport-neutral lifecycle model for one Asterisk call."""

from dataclasses import dataclass
from enum import StrEnum


class CallState(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    ENDED = "ended"


@dataclass(slots=True)
class CallSession:
    call_id: str
    state: CallState = CallState.CREATED

    def activate(self) -> None:
        if self.state is not CallState.CREATED:
            raise ValueError(f"Call {self.call_id} cannot activate from {self.state}")
        self.state = CallState.ACTIVE

    def end(self) -> None:
        if self.state is CallState.ENDED:
            return
        self.state = CallState.ENDED
