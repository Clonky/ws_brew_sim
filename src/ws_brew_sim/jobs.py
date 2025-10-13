from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

if TYPE_CHECKING:
    from .units import Unit

logger = logging.getLogger(__name__)


class JobState(Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"


@dataclass(kw_only=True)
class Job:
    name: str
    job_id: str
    state: JobState = JobState.PENDING


@dataclass(kw_only=True)
class TransferJob(Job):
    source: Unit
    target: Unit
    amount: int
    rate: int
    moved_volume: int = 0

    @classmethod
    def new(cls, source: Unit, target: Unit, amount: int, rate: int):
        return cls(
            state=JobState.PENDING,
            job_id=str(uuid4()),
            name=f"{source.name}",
            source=source,
            target=target,
            amount=amount,
            rate=rate,
        )

    def run(self):
        transfer_amount = min(self.rate, self.source.volume.volume)
        self.source.volume -= transfer_amount
        self.moved_volume += transfer_amount
        logger.info(
            f"Transferring {transfer_amount}L from {self.name} to {self.target.name}. {self.moved_volume}/{self.amount}L moved."
        )
        self.target.volume += transfer_amount
        if self.moved_volume >= self.amount or abs(self.source.volume.volume) == 0:
            self.state = JobState.COMPLETED
