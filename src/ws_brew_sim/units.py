from uuid import uuid4
from .utils import NodeId
from .simulation import Simulation
from .behaviours import NormalDistBehaviour
from asyncua import Server
from asyncua.common.node import Node
from asyncua import ua
from asyncua.server.event_generator import EventGenerator
import asyncio
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
            self.node = server.get_node(self.node_id)
            await self.node.set_writable()
            logger.info(f"Module {self.name} connected to node {self.node}")

    async def run(self):
        if self.update_behaviour:
            self.update_behaviour.update()
            if self.node is not None:
                logger.debug("Updating node %s to state %s", self.node, self.update_behaviour.state)
                await self.node.write_value(self.update_behaviour.state)


class Unit:
    def __init__(self, name: str, node_id: ua.NodeId, simulation: Simulation):
        self.asset_id = str(uuid4())
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
            self.node = server.get_node(self.node_id)
            logger.info(f"Module {self.name} connected to node {self.node}")
            await self.setup_evgen(server)

        for module in self.modules:
            await module.connect(server)

    async def setup_evgen(self, server: Server):
        if not self.node:
            await self.connect(server)
        else:
            transfer_gen = await self.create_transfer_event_generator(server)
            self.evgen["TransferEvent"] = transfer_gen

    async def create_transfer_event_generator(self, server: Server):
        ws_basis_idx = await server.get_namespace_index("http://opcfoundation.org/UA/WeihenstephanStandards/WSBasis/")
        etype = await server.nodes.base_event_type.get_child(f"{ws_basis_idx}:WSTransferEventType")
        filter_idx = await server.get_namespace_index("http://Implementation_Filter")
        logging.warning(filter_idx)
        target = server.get_node(ua.NodeId(5209, filter_idx))
        transfer_gen: EventGenerator = await server.get_event_generator(etype, target)
        return transfer_gen


    async def run(self):
        for module in self.modules:
            await module.run()


class FermentationTankExample(Unit):
    def __init__(self, simulation: Simulation):
        super().__init__("15:FermentationTank", ua.NodeId(5209, 15), simulation)
        self._populate_modules()

    async def run(self):
        for module in self.modules:
            await module.run()
        self.evgen["TransferEvent"].event.SourceAssetId = self.asset_id
        self.evgen["TransferEvent"].event.SourceName = "FermentationTank"
        self.evgen["TransferEvent"].event.Severity = ua.Variant(100)
        await self.evgen["TransferEvent"].trigger()
        await asyncio.sleep(0.5)

    def _populate_modules(self):
        temp = Module("Temperature", ua.NodeId(6277, 15), NormalDistBehaviour(12, 0.5))
        self.modules.append(temp)
