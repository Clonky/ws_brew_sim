import asyncio
import logging
from collections import deque
from .jobs import Job
from .units import Unit
from asyncua import Server

logger = logging.getLogger(__name__)


class Simulation:
    def __init__(self, server: Server, units: list[Unit] = [], jobs: deque | None = deque([])):
        self.server = server
        self.state = "paused"
        self.units = units
        self.jobs = jobs

    async def run(self):
        self.state = "running"
        for unit in self.units:
            await unit.run()

    def stop(self):
        self.state = "paused"

    def add_job(self, job: Job):
        self.jobs.append(job)

    async def add_unit(self, unit: Unit):
        self.units.append(unit)
        await unit.connect(self.server)


    async def start_loop(self):
        logging.info("Starting simulation loop...")
        while True:
            await self.run()
            await asyncio.sleep(0.5)
