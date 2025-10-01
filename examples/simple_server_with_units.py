import os
import asyncio
import asyncua
from collections import deque
from ws_brew_sim.simulation import Simulation
from ws_brew_sim.units import FermentationTankExample, BrightBeerTankExample
from ws_brew_sim.jobs import TransferJob
from asyncua import ua
import logging


async def setup(server: asyncua.Server):


    simulation = Simulation(server, units=[], jobs=[])

    units = [
        FermentationTankExample(simulation, initial_vol=1000),
        BrightBeerTankExample(simulation, initial_vol=0)
    ]

    jobs = deque([
        TransferJob.new(source=units[0], target=units[1], amount=200, rate=20)
    ])
    simulation.units = units
    simulation.jobs = jobs
    asyncio.create_task(simulation.start_loop())


def get_xmls():
    folder = "xmls/"
    xmls = [f for f in os.listdir(folder) if f.endswith(".xml")]
    xmls.sort()
    logging.info(f"Found XMLs: {xmls}")
    return xmls


async def main():
    logging.info("Starting simple server...")
    server = asyncua.Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840/wsbrew")
    server.set_server_name("WS Brew Simulation Server")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    for xml in get_xmls():
        logging.info(f"Importing {xml}...")
        await server.import_xml(f"xmls/{xml}")

    await setup(server)

    async with server:
        while True:
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
