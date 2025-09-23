from .utils import NodeId
from .simulation import Simulation
from .behaviours import NormalDistBehaviour
from asyncua import Server
from asyncua.common.node import Node
import logging

logger = logging.getLogger(__name__)


class Module:
    def __init__(self, name: str, node_id: NodeId, update_behaviour=None):
        self.name = name
        self.node_id = node_id
        self.node = None
        self.update_behaviour = update_behaviour

    async def connect(self, server: Server):
        if not self.node:
            self.node = server.get_node(f"ns={self.node_id.ns};i={self.node_id.id}")
            await self.node.set_writable()
            logger.info(f"Module {self.name} connected to node {self.node}")

    async def run(self):
        if self.update_behaviour:
            self.update_behaviour.update()
            if self.node is not None:
                logger.debug("Updating node %s to state %s", self.node, self.update_behaviour.state)
                await self.node.write_value(self.update_behaviour.state)


class Unit:
    def __init__(self, name: str, node_id: NodeId, simulation: Simulation):
        self.name = name
        self.node_id = node_id
        self.job = None
        self.node: Node | None = None
        self.modules = []
        self.simulation = simulation
        self.evgen = dict()

    def register_module(self, module: Module):
        self.modules.append(module)

    def start_job(self):
        if not self.job:
            associated_jobs = self.simulation.messages.get(self.name, [])
            if associated_jobs:
                self.job = associated_jobs

    async def connect(self, server: Server):
        if not self.node:
            self.node = server.get_node(f"ns={self.node_id.ns};i={self.node_id.id}")
            logger.info(f"Module {self.name} connected to node {self.node}")

        for module in self.modules:
            await module.connect(server)

    async def setup_evgen(self, server, evnode: Node):
        if not self.node:
            await self.connect(server)
        else:
            transfer_gen = await server.get_event_generator(evnode, self.node.nodeid)
            self.evgen["TransferEvent"] = transfer_gen

    async def run(self):
        for module in self.modules:
            await module.run()


class FermentationTankExample(Unit):
    def __init__(self, simulation: Simulation):
        self.name = "Fermentation Tank"
        self.node_id = NodeId(16, "5209")
        self.job = None
        self.node = None
        self.modules = []
        self.simulation = simulation
        self._populate_modules()

    def _populate_modules(self):
        temp = Module("Temperature", NodeId(16, "6277"), NormalDistBehaviour(12, 0.5))
        self.modules.append(temp)
