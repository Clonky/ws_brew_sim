from __future__ import annotations
from typing import TYPE_CHECKING
from .behaviours import StaticBehaviour
from .utils import NodeId
from asyncua import Server
import logging

if TYPE_CHECKING:
    from .units import Unit

logger = logging.getLogger(__name__)

class Module:
    def __init__(self, name: str, node_id: NodeId | None, update_behaviour=None):
        self.name = name
        self.node_id = node_id
        self.node = None
        self.update_behaviour = update_behaviour

    async def connect(self, server: Server):
        if not self.node:
            if self.node_id is not None:
                self.node = server.get_node(self.node_id)
                await self.node.set_writable()
                logger.info(f"Module {self.name} connected to node {self.node}")

    async def run(self):
        if self.update_behaviour:
            self.update_behaviour.update()
            if self.node is not None:
                logger.debug("Updating node %s to state %s", self.node, self.update_behaviour.state)
                await self.node.write_value(self.update_behaviour.state)

    def register(self, unit: 'Unit'):
        unit.register_module(self)

class Volume(Module):
    def __init__(self, initial_volume: int = 0):
        super().__init__("Volume", None, StaticBehaviour(initial_volume))

    @property
    def volume(self) -> int:
        return self.behaviour.state
    
    @volume.setter
    def volume(self, value: int):
        self.behaviour.state = value