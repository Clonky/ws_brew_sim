from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING
from uuid import uuid4

from asyncua import Server, ua
from asyncua.common.node import Node
from asyncua.server.event_generator import EventGenerator

from .events import Event, TransferEvent, UnitProcedureEvent
from .jobs import FilterJob, JobState, TransferJob
from .modules import Module, Pressure, Temperature, Timer, Turbidity, Volume
from .statemachine import MachineState, StateMachineTree

if TYPE_CHECKING:
    from .jobs import Job, JobState, TransferJob
    from .simulation import Simulation

logger = logging.getLogger(__name__)

TIME_NODE = ua.NodeId(2258, 0)


class Unit:
    def __init__(
        self,
        name: str,
        node_id: ua.NodeId,
        simulation: "Simulation",
        modules: list[Module] = [],
        initial_operation_mode="",
    ):
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
        self.initial_operation_mode = initial_operation_mode

    def __repr__(self):
        return f"Unit(name={self.name}, node_id={self.node_id}"

    def add_job(self, job: Job):
        self.jobs.append(job)

    def _check_jobs(self):
        if self.jobs and self.job is None:
            self.job = self.jobs.popleft()

    async def _get_servertime(self) -> float:
        time_node = self.simulation.server.get_node(TIME_NODE)
        val = await time_node.read_value()
        return val

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
        try:
            asset_id_node = await self.node.get_child(
                [("8:Monitoring", "8:Status", "7:Identification", "7:AssetId")]
            )
            await asset_id_node.write_value(self.asset_id)
            serial_number_node = await self.node.get_child(
                [("8:Monitoring", "8:Status", "7:Identification", "7:SerialNumber")]
            )
            await serial_number_node.write_value(self.serial_number)
        except:
            return

    async def _set_up_statemachines(self):
        self.statemachine_operation_mode = (
            await StateMachineTree.build_tree_operation_mode(
                self.simulation.server, self.node_id
            )
        )
        if self.initial_operation_mode and self.statemachine_operation_mode:
            self.statemachine_operation_mode.activate_state(self.initial_operation_mode)
        self.statemachine_machine_state = await MachineState.build_tree_machine_state(
            self.simulation.server, self.node_id
        )

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
            if "TransferEvent" in self.evgen:
                event = await TransferEvent.from_nodes(
                    self.node,
                    self.node,
                    "batch_001",
                    self.evgen["TransferEvent"],
                    server,
                )
                self.curr_event = event

        for module in self.modules:
            await module.connect(server)

    async def _setup_evgen(self, server: Server):
        pass

    async def _create_transfer_event_generator(self, server: Server):
        ws_basis_idx = await server.get_namespace_index(
            "http://opcfoundation.org/UA/WeihenstephanStandards/WSBasis/"
        )
        etype = await server.nodes.base_event_type.get_child(
            f"{ws_basis_idx}:WSTransferEventType"
        )
        target = server.get_node(self.node_id)
        transfer_gen: EventGenerator = await server.get_event_generator(etype, target)
        return transfer_gen

    async def _create_process_event_generator(self, server: Server):
        ws_brew_idx = await server.get_namespace_index(
            "http://opcfoundation.org/UA/WeihenstephanStandards/WSBrew/"
        )
        etype = await server.nodes.base_event_type.get_child(
            f"{ws_brew_idx}:WSUnitProcedureEventType"
        )
        target = server.get_node(self.node_id)
        process_gen: EventGenerator = await server.get_event_generator(etype, target)
        return process_gen

    async def run(self):
        for module in self.modules:
            await module.run()


class Tank(Unit):
    def __init__(
        self,
        name: str,
        node_id: ua.NodeId,
        simulation: Simulation,
        initial_vol=0,
        modules: list[Module] = [],
        **kwargs,
    ):
        super().__init__(name, node_id, simulation, **kwargs)
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
                    self.evgen[
                        "TransferEvent"
                    ] = await self.create_transfer_event_generator(
                        self.simulation.server
                    )
                self.event = await TransferEvent.from_job(
                    self.job, self.evgen["TransferEvent"], time, "batch_001"
                )
                self.job.state = JobState.RUNNING
                self.statemachine_operation_mode.start_production()
                self.statemachine_operation_mode.default_mode = "Used"
                self.statemachine_machine_state.start_production()
            elif (
                self.job.state == JobState.RUNNING
                and self.statemachine_operation_mode.is_in_production()
            ):
                # Perform transfer here
                self.job.run(self)
            elif self.job.state == JobState.COMPLETED:
                logger.info(f"Job {self.job} on tank {self.name} completed")
                time = await self._get_servertime()
                self.event.add_completion_info(self.job, time)
                await self.event.trigger()
                self.statemachine_operation_mode.stop_production()
                self.statemachine_operation_mode.goto_default()
                self.statemachine_machine_state.stop_production()
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
        modules = [Temperature(ua.NodeId(6277, 15), 12, 0.5), Volume(initial_vol)]
        super().__init__(
            "FermentationTank",
            ua.NodeId(5209, 15),
            simulation,
            modules=modules,
            initial_operation_mode="Used",
        )


class BrightBeerTankExample(Tank):
    def __init__(self, simulation: Simulation, initial_vol=0):
        modules = [Volume(initial_vol)]
        super().__init__(
            "BrightBeerTank",
            ua.NodeId(5001, 15),
            simulation,
            modules=modules,
            initial_operation_mode="Sterile",
        )


class SheetFilter(Unit):
    def __init__(
        self,
        simulation: Simulation,
        nodeid: ua.NodeId,
        modules: list[Module] = [],
        **kwargs,
    ):
        super().__init__("SheetFilter", nodeid, simulation, modules=modules, **kwargs)
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
            self.statemachine_machine_state.start_production()
            self.statemachine_operation_mode.start_production()
            self.statemachine_operation_mode.default_mode = "Used"
            await self._setup_event()
        elif self.job and self.job.state == JobState.RUNNING:
            self.job.run(self)
        elif self.job.is_finished():
            self.statemachine_machine_state.stop_production()
            self.statemachine_operation_mode.goto_default()
            logger.info(f"Job {self.job} on SheetFilter {self.name} completed")
            self.event.add_completion_info(self.job, await self._get_servertime())
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
            self.event = await TransferEvent.from_job(
                self.job, self.evgen["TransferEvent"], time, "batch_001"
            )


class SheetFilterExample(SheetFilter):
    def __init__(self, simulation: Simulation):
        modules = [
            Pressure(ua.NodeId(6151, 15), 1.5, 0.1),
            Timer(ua.NodeId(6268, 15), "PowerOnDuration"),
            Turbidity(ua.NodeId(6153, 15), 0.5, 0.1),
            Volume(0),
        ]
        super().__init__(
            simulation,
            ua.NodeId(5100, 15),
            modules=modules,
            initial_operation_mode="Sterile",
        )
        self.volume = next((m for m in self.modules if m.name == "Volume"), None)


class TunnelOvenExample(Unit):
    """Tunnel oven unit wired to ns=15 (http://bake.example.com) at runtime.

    Runtime namespace indices (server loads xmls/ alphabetically):
      ns=15 → http://bake.example.com  (114_tunnel_oven.NodeSet2.xml instances)

    Sensors:
      - TemperatureProductCore   ns=15;i=6431
      - PressureChimneyFlueGas   ns=15;i=6423
      - PressureChimneyFlueSteam ns=15;i=6427
      - EccentricSetpoint        ns=15;i=6058  (stable setpoint ~25 Hz)
      - PressureSetpoint         ns=15;i=6059  (stable setpoint ~1.0 bar)
    """

    def __init__(self, simulation: Simulation):
        # Placeholder node IDs (ns=15) are replaced with correct indices in connect().
        modules = [
            Temperature(ua.NodeId(6431, 15), 200.0, 2.0, low=0.0, high=300.0),  # TemperatureProductCore
            Pressure(ua.NodeId(6423, 15), 0.02, 0.005, low=-0.5, high=0.5),     # PressureChimneyFlueGas
            Pressure(ua.NodeId(6427, 15), 0.015, 0.005, low=-0.5, high=0.5),    # PressureChimneyFlueSteam
        ]
        super().__init__(
            "TunnelOven",
            ua.NodeId(5001, 15),
            simulation,
            modules=modules,
            initial_operation_mode="None",
        )

    async def connect(self, server: Server):
        nsidx = await server.get_namespace_index("http://bake.example.com")
        self.node_id = ua.NodeId(5001, nsidx)
        self.modules = [
            Temperature(ua.NodeId(6431, nsidx), 200.0, 2.0, low=0.0, high=300.0),  # TemperatureProductCore
            Pressure(ua.NodeId(6423, nsidx), 0.02, 0.005, low=-0.5, high=0.5),     # PressureChimneyFlueGas
            Pressure(ua.NodeId(6427, nsidx), 0.015, 0.005, low=-0.5, high=0.5),    # PressureChimneyFlueSteam
        ]
        for m in self.modules:
            m.variant_type = ua.VariantType.Double
        await super().connect(server)

    async def run(self):
        for module in self.modules:
            await module.run()
        if self.job:
            await self._handle_job()
        else:
            self._check_jobs()
        await asyncio.sleep(0.5)

    async def _setup_evgen(self, server: Server):
        pass
