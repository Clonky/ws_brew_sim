import asyncio
import logging
from collections import deque
from .jobs import Job
from .units import Unit
from asyncua import Server

logger = logging.getLogger(__name__)


class Simulation:
    def __init__(self, server: Server, units: list[Unit] = [], jobs: deque = deque([])):
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

    async def start_loop(self):
        logging.info("Starting simulation loop...")
        while True:
            try:
                await self.run()
                await asyncio.sleep(0.5)
            except Exception as e:
                logging.error(f"Error in simulation loop: {e}")
                self.stop()
                break
