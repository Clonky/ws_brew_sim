from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

if TYPE_CHECKING:
    from .units import Unit


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