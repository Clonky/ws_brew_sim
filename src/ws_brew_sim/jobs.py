from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

if TYPE_CHECKING:
    from .units import Unit, SheetFilter

logger = logging.getLogger(__name__)


class JobState(Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"


@dataclass(kw_only=True)
class Job:
    name: str
    job_id: str
    state: JobState = JobState.PENDING

    def is_finished(self) -> bool:
        return self.state == JobState.COMPLETED


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

    def run(self, unit: Unit):
        transfer_amount = min(self.rate, self.source.volume.volume)
        self.source.volume -= transfer_amount
        self.moved_volume += transfer_amount
        logger.info(
            f"Transferring {transfer_amount}L from {self.name} to {self.target.name}. {self.moved_volume}/{self.amount}L moved."
        )
        self.target.volume += transfer_amount
        if self.moved_volume >= self.amount or abs(self.source.volume.volume) == 0:
            self.state = JobState.COMPLETED

    def _finish_requirement(self) -> bool:
        return self.moved_volume >= self.amount or abs(self.source.volume.volume) == 0

@dataclass(kw_only=True)
class TransferJobLongRunning(TransferJob):

    def _finish_requirement(self) -> bool:
        return self.moved_volume >= self.amount



@dataclass(kw_only=True)
class ProcessingJob(Job):
    batch_id: str


@dataclass(kw_only=True)
class FilterJob(ProcessingJob):
    filter_rate: int = 10
    amount_filtered: int = 0
    amount_to_filter: int

    def run(self, unit: SheetFilter):
        # Simulate filtering process
        if self.state == JobState.RUNNING:
            move_amount = min(self.filter_rate, unit.volume.volume)
            unit.volume_filtered += move_amount
            if self._finish_requirement(unit):
                self.state = JobState.COMPLETED
                unit.volume_filtered = 0
        
    def _finish_requirement(self, unit: SheetFilter) -> bool:
        return unit.volume_filtered >= self.amount_to_filter