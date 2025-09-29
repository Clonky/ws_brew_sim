import os
import asyncio
import asyncua
from ws_brew_sim.simulation import Simulation
from ws_brew_sim.units import FermentationTankExample
from asyncua.common.node import Node
from asyncua import ua
import logging


async def setup(server: asyncua.Server) -> list[Node]:
    simulation = Simulation()
    units = []

    ns_idx = await server.register_namespace("http://wsbrewsim.bgt")
    ws_brew_idx = await server.get_namespace_index("http://opcfoundation.org/UA/WeihenstephanStandards/WSBrew/")
    ws_basis_idx = await server.get_namespace_index("http://opcfoundation.org/UA/WeihenstephanStandards/WSBasis/")
    machinery_idx = await server.get_namespace_index("http://opcfoundation.org/UA/Machinery/")
    machinery_node: Node = server.get_node(ua.NodeId(1001, machinery_idx))
    fermentation_tank = await machinery_node.add_object(ns_idx, "FermentationTank", ua.NodeId(10024, ws_brew_idx))
    evgen = await server.get_event_generator(ua.NodeId(10002, ws_basis_idx), fermentation_tank)
    fermentation_tank.evgen = evgen
    units.append(fermentation_tank)


    asyncio.create_task(simulation.start_loop())
    return units


def get_xmls():
    folder = "xmls/"
    xmls = [f for f in os.listdir(folder) if f.endswith(".xml")]
    xmls.sort()
    xmls = [xml for xml in xmls if not xml.startswith("113_filter")]
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

    units = await setup(server)

    async with server:
        while True:
            await units[0].evgen.trigger()
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
