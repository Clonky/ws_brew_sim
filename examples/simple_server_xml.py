import os
import asyncio
import asyncua
from asyncua import ua
import logging


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

    uri = "http://wsbrewsim.bgt/"

    await server.register_namespace(uri)

    for xml in get_xmls():
        logging.info(f"Importing {xml}...")
        await server.import_xml(f"xmls/{xml}")

    async with server:
        while True:
            await asyncio.sleep(0.1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
