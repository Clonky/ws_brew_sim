from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING
from uuid import uuid4
from .behaviours import NormalDistBehaviour, DurationTimer
from .events import TransferEvent, Event, UnitProcedureEvent
from .modules import Volume, Module
from asyncua import Server
from asyncua.common.node import Node
from asyncua import ua
from asyncua.server.event_generator import EventGenerator
import asyncio
import logging
from .jobs import JobState, TransferJob, FilterJob
from .statemachine import StateMachineTree

if TYPE_CHECKING:
    from .simulation import Simulation
    from .jobs import JobState, TransferJob, Job

logger = logging.getLogger(__name__)

TIME_NODE = ua.NodeId(2258, 0)


class Unit:
    def __init__(self, name: str, node_id: ua.NodeId, simulation: "Simulation", modules: list[Module] = []):
        self.asset_id = str(uuid4())[:12]
        self.serial_number = str(uuid4())[:12]
        self.name = name
        self.node_id = node_id
        self.jobs = deque()
        self.job = None
        self.node: Node | None = None
        self.modules = modules
        self.simulation = simulation
        self.evgen = dict()
        self.event: Event | None = None
        self._populate_modules()
        self.statemachine_operation_mode: None | StateMachineTree = None
        self.statemachine_machine_state: None | StateMachineTree = None

    def __repr__(self):
        return f"Unit(name={self.name}, node_id={self.node_id}"

    def add_job(self, job: Job):
        self.jobs.append(job)

    def _check_jobs(self):
        if self.jobs and self.job is None:
            self.job = self.jobs.popleft()

    async def _get_servertime(self) -> float:
        time_node = self.simulation.server.get_node(TIME_NODE)
        return await time_node.read_value()

    def _handle_job(self):
        pass

    def _populate_modules(self, modules: list[Module] = []):
        for module in modules:
            self.register_module(module)

    def register_module(self, module: Module):
        self.modules.append(module)

    def _start_job(self):
        if not self.job:
            associated_jobs = self.simulation.messages.get(self.name, [])
            if associated_jobs:
                self.job = associated_jobs

    async def _set_static_vals(self):
        asset_id_node = await self.node.get_child(["2:Identification", "2:AssetId"])
        await asset_id_node.write_value(self.asset_id)
        serial_number_node = await self.node.get_child(["2:Identification", "2:SerialNumber"])
        await serial_number_node.write_value(self.serial_number)

    async def _set_up_statemachines(self):
        self.statemachine_operation_mode = await StateMachineTree.build_tree_operation_mode(self.simulation.server, self.node_id)
        self.statemachine_machine_state = await StateMachineTree.build_tree_machine_state(self.simulation.server, self.node_id)

    async def _set_internal_static_state(self):
        if self.node:
            await self._set_static_vals()
            await self._set_up_statemachines()

    async def connect(self, server: Server):
        if not self.node:
            self.node = server.get_node(self.node_id)
            logger.info(f"Module {self.name} connected to node {self.node}")
            await self._set_internal_static_state()
            await self._setup_evgen(server)
            event = await TransferEvent.from_nodes(
                self.node, self.node, "batch_001", self.evgen["TransferEvent"], server
            )
            self.curr_event = event

        for module in self.modules:
            await module.connect(server)

    async def _setup_evgen(self, server: Server):
        pass

    async def _create_transfer_event_generator(self, server: Server):
        ws_basis_idx = await server.get_namespace_index("http://opcfoundation.org/UA/WeihenstephanStandards/WSBasis/")
        etype = await server.nodes.base_event_type.get_child(f"{ws_basis_idx}:WSTransferEventType")
        target = server.get_node(self.node_id)
        transfer_gen: EventGenerator = await server.get_event_generator(etype, target)
        return transfer_gen

    async def _create_process_event_generator(self, server: Server):
        ws_brew_idx = await server.get_namespace_index("http://opcfoundation.org/UA/WeihenstephanStandards/WSBrew/")
        etype = await server.nodes.base_event_type.get_child(f"{ws_brew_idx}:WSUnitProcedureEventType")
        target = server.get_node(self.node_id)
        process_gen: EventGenerator = await server.get_event_generator(etype, target)
        return process_gen

    async def run(self):
        for module in self.modules:
            await module.run()


class Tank(Unit):
    def __init__(
        self, name: str, node_id: ua.NodeId, simulation: Simulation, initial_vol=0, modules: list[Module] = []
    ):
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
                time = await self.simulation.server.get_node(TIME_NODE).read_value()
                if self.evgen.get("TransferEvent") is None:
                    self.evgen["TransferEvent"] = await self.create_transfer_event_generator(self.simulation.server)
                self.event = await TransferEvent.from_job(self.job, self.evgen["TransferEvent"], time, "batch_001")
                self.job.state = JobState.RUNNING
                self.statemachine_operation_mode.start_production()
                self.build_tree_operation_modestatemachine_operation_mode.start_production()
            elif self.job.state == JobState.RUNNING and self.statemachine_operation_mode.is_in_production():
                # Perform transfer here
                self.job.run(self)
            elif self.job.state == JobState.COMPLETED:
                logger.info(f"Job {self.job} on tank {self.name} completed")
                time = await self._get_servertime()
                self.event.add_completion_info(self.job, time)
                await self.event.trigger()
                self.statemachine_operation_mode.stop_production()
                self.build_tree_operation_modestatemachine_operation_mode.stop_production()
                self.job = None

    async def _setup_evgen(self, server: Server):
        if not self.node:
            await self.connect(server)
        else:
            transfer_gen = await self._create_transfer_event_generator(server)
            self.evgen["TransferEvent"] = transfer_gen

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
        modules = [Module("Temperature", ua.NodeId(6277, 15), NormalDistBehaviour(12, 0.5)), Volume(initial_vol)]
        super().__init__("FermentationTank", ua.NodeId(5209, 15), simulation, modules=modules)


class BrightBeerTankExample(Tank):
    def __init__(self, simulation: Simulation, initial_vol=0):
        modules = [Volume(initial_vol)]
        super().__init__("BrightBeerTank", ua.NodeId(5001, 15), simulation, modules=modules)


class SheetFilter(Unit):
    def __init__(self, simulation: Simulation, nodeid: ua.NodeId, modules: list[Module] = []):
        super().__init__("SheetFilter", nodeid, simulation, modules=modules)
        self.volume = 0
        self.volume_filtered = 0

    async def run(self):
        for module in self.modules:
            await module.run()
        if self.job:
            await self._handle_job()
        else:
            self._check_jobs()
        await asyncio.sleep(0.5)

    async def _setup_evgen(self, server: Server):
        if not self.node:
            await self.connect(server)
        else:
            transfer_gen = await self._create_transfer_event_generator(server)
            process_gen = await self._create_process_event_generator(server)
            self.evgen["TransferEvent"] = transfer_gen
            self.evgen["ProcessEvent"] = process_gen

    async def _handle_job(self):
        if self.job and self.job.state == JobState.PENDING:
            logger.info(f"Starting job {self.job} on SheetFilter {self.name}")
            self.job.state = JobState.RUNNING
            await self._setup_event()
        elif self.job and self.job.state == JobState.RUNNING:
            self.job.run(self)
        elif self.job.is_finished():
            logger.info(f"Job {self.job} on SheetFilter {self.name} completed")
            await self.event.add_completion_info(self.job, await self._get_servertime())
            await self.event.trigger()
            self.job = None
            self.event = None

    async def _setup_event(self):
        if isinstance(self.job, FilterJob):
            self.event = await UnitProcedureEvent.from_job(
                self.job, self.evgen["ProcessEvent"], self, self.job.batch_id
            )
        elif isinstance(self.job, TransferJob):
            time = await self._get_servertime()
            self.event = await TransferEvent.from_job(self.job, self.evgen["TransferEvent"], time, "batch_001")


class SheetFilterExample(SheetFilter):
    def __init__(self, simulation: Simulation):
        modules = [
            Module("Pressure", ua.NodeId(6151, 15), NormalDistBehaviour(1.5, 0.1)),
            Module("PowerOnDuration", ua.NodeId(6268, 15), DurationTimer(0.0)),
            Module("TurbidityOutlet", ua.NodeId(6153, 15), NormalDistBehaviour(0.5, 0.1)),
            Volume(0),
        ]
        super().__init__(simulation, ua.NodeId(5100, 15), modules=modules)
        self.volume = next((m for m in self.modules if m.name == "Volume"), None)
