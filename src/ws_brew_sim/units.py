from __future__ import annotations
from typing import TYPE_CHECKING
from uuid import uuid4
from .utils import NodeId
from .behaviours import NormalDistBehaviour, StaticBehaviour
from .events import TransferEvent, Event
from .jobs import JobState, TransferJob
from .modules import Volume, Module
from asyncua import Server
from asyncua.common.node import Node
from asyncua import ua
from asyncua.server.event_generator import EventGenerator
import asyncio
import logging

if TYPE_CHECKING:
    from .simulation import Simulation

logger = logging.getLogger(__name__)

TIME_NODE = ua.NodeId(2258, 0)




class Unit:
    def __init__(self, name: str, node_id: ua.NodeId, simulation: 'Simulation', modules: list[Module] = []):
        self.asset_id = str(uuid4())[:12]
        self.serial_number = str(uuid4())[:12]
        self.name = name
        self.node_id = node_id
        self.job = None
        self.node: Node | None = None
        self.modules = modules
        self.simulation = simulation
        self.evgen = dict()
        self.event: Event | None = None
        self._populate_modules()

    def __repr__(self):
        return f"Unit(name={self.name}, node_id={self.node_id}"

    def _check_jobs(self):
        if self.simulation.jobs:
            first_job = self.simulation.jobs[0]
            if first_job.name == self.name:
                self.job = self.simulation.jobs.popleft()

    def _handle_job(self):
        pass

    def _populate_modules(self, modules: list[Module] = []):
        for module in modules:
            self.register_module(module)

    def register_module(self, module: Module):
        self.modules.append(module)

    def start_job(self):
        if not self.job:
            associated_jobs = self.simulation.messages.get(self.name, [])
            if associated_jobs:
                self.job = associated_jobs

    async def _set_internal_static_state(self):
        if self.node:
            asset_id_node = await self.node.get_child(["2:Identification", "2:AssetId"])
            await asset_id_node.write_value(self.asset_id)
            serial_number_node = await self.node.get_child(["2:Identification", "2:SerialNumber"])
            await serial_number_node.write_value(self.serial_number)

    async def connect(self, server: Server):
        if not self.node:
            self.node = server.get_node(self.node_id)
            logger.info(f"Module {self.name} connected to node {self.node}")
            await self._set_internal_static_state()
            await self.setup_evgen(server)
            event = await TransferEvent.from_nodes(self.node, self.node, "batch_001", self.evgen["TransferEvent"], server)
            self.curr_event = event

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
        target = server.get_node(self.node_id)
        transfer_gen: EventGenerator = await server.get_event_generator(etype, target)
        return transfer_gen


    async def run(self):
        for module in self.modules:
            await module.run()


class Tank(Unit):
    def __init__(self, name: str, node_id: ua.NodeId, simulation: Simulation, initial_vol = 0, modules: list[Module] = []):
        super().__init__(name, node_id, simulation)
        if not any(m.name == "Volume" for m in modules):
            modules.append(Volume(initial_vol))
        self.modules = modules
        self.job: TransferJob | None = None
        self.event: TransferEvent | None = None
        self.volume = next((m for m in self.modules if m.name == "Volume"), None)

    async def _handle_job(self):
        if self.job:
            if self.job.state == JobState.PENDING:
                logger.info(f"Starting job {self.job} on tank {self.name}")
                # Initialize events over here
                target = self.job.target
                time = await self.simulation.server.get_node(TIME_NODE).read_value()
                if self.evgen.get("TransferEvent") is None:
                    self.evgen["TransferEvent"] = await self.create_transfer_event_generator(self.simulation.server)
                self.event = TransferEvent(
                    source_asset_id=self.job.source.asset_id,
                    target_asset_id=self.job.target.asset_id,
                    source_batch_id="batch_001",
                    target_batch_id="batch_001",
                    source_set_amount=self.volume - self.job.amount,
                    target_set_amount=self.job.target.volume + self.job.amount,
                    start_time=time,
                    evgen=self.evgen["TransferEvent"],
                    source_material_id=None,
                    target_material_id=None
                )
                set_source_quantity = max(0, self.volume - self.job.amount)
                set_target_quantity = self.job.target.volume + self.job.amount
                self.event.evgen.event.SetSourceQuantity = ua.Variant(int(set_source_quantity), ua.VariantType.UInt32) 
                self.event.evgen.event.SetTargetQuantity = ua.Variant(int(set_target_quantity), ua.VariantType.UInt32)
                self.job.state = JobState.RUNNING
            elif self.job.state == JobState.RUNNING:
                # Perform transfer here
                transfer_amount = min(self.job.rate, self.volume)
                self.volume -= transfer_amount
                self.job.moved_volume += transfer_amount
                logger.info(f"Transferring {transfer_amount}L from {self.name} to {self.job.target.name}. {self.job.moved_volume}/{self.job.amount}L moved.")
                self.job.target.volume += transfer_amount
                if self.job.moved_volume >= self.job.amount or abs(self.volume) == 0:
                    # Handle job completion
                    time = await self.simulation.server.get_node(TIME_NODE).read_value()
                    self.job.state = JobState.COMPLETED
                    self.event.evgen.event.EndTime = time
                    self.event.evgen.event.SourceQuantity = ua.Variant(self.volume, ua.VariantType.UInt32)
                    self.event.evgen.event.TargetQuantity = ua.Variant(int(self.job.target.volume), ua.VariantType.UInt32)
                    await self.event.trigger()
                    self.event = None
                    self.job = None

    async def run(self):
        for module in self.modules:
            await module.run()
        if self.job:
            await self._handle_job()
        else:
            self._check_jobs()
        await asyncio.sleep(0.5)


class FermentationTankExample(Tank):
    def __init__(self, simulation: Simulation, initial_vol=1000):
        modules = [
            Module("Temperature", ua.NodeId(6277, 15), NormalDistBehaviour(12, 0.5)),
            Volume(initial_vol)
        ]
        super().__init__("FermentationTank", ua.NodeId(5209, 15), simulation, modules=modules)

class BrightBeerTankExample(Tank):
    def __init__(self, simulation: Simulation, initial_vol=0):
        modules = [
            Volume(initial_vol)
        ]
        super().__init__("BrightBeerTank", ua.NodeId(5001, 15), simulation, modules=modules)
