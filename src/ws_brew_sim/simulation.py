import asyncio
import logging

logger = logging.getLogger(__name__)


class Simulation:
    def __init__(self):
        self.state = "paused"
        self.units = []
        self.messages = dict()

    async def run(self):
        self.state = "running"
        for unit in self.units:
            await unit.run()

    def stop(self):
        self.state = "paused"

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
