from __future__ import annotations
from ws_brew_sim.behaviours import ConditionalDurationTimer, DurationTimer
from ws_brew_sim.behaviours import NormalDistBehaviour
from typing import TYPE_CHECKING
from .behaviours import StaticBehaviour
from .utils import NodeId
from asyncua import Server, ua
import logging

if TYPE_CHECKING:
    from .units import Unit

logger = logging.getLogger(__name__)

_UNECE_NS = "http://www.opcfoundation.org/UA/units/un/cefact"


def _eu(unit_id: int, display: str, description: str) -> ua.EUInformation:
    info = ua.EUInformation()
    info.NamespaceUri = _UNECE_NS
    info.UnitId = unit_id
    info.DisplayName = ua.LocalizedText(Text=display)
    info.Description = ua.LocalizedText(Text=description)
    return info


def _range(low: float, high: float) -> ua.Range:
    r = ua.Range()
    r.Low = low
    r.High = high
    return r


class Module:
    def __init__(self, name: str, node_id: NodeId | None, update_behaviour=None, unit: str | None = None, variant_type=None):
        self.name = name
        self.node_id = node_id
        self.node = None
        self.update_behaviour = update_behaviour
        self.unit = unit
        self.variant_type = variant_type
        self.eu_info: ua.EUInformation | None = None
        self.eu_range: ua.Range | None = None

    async def connect(self, server: Server):
        if not self.node:
            if self.node_id is not None:
                self.node = server.get_node(self.node_id)
                await self.node.set_writable()
                logger.info(f"Module {self.name} connected to node {self.node}")
                await self._write_metadata()

    async def _write_metadata(self):
        if self.eu_info is not None:
            try:
                eu_node = await self.node.get_child("0:EngineeringUnits")
                await eu_node.set_writable()
                await eu_node.write_value(self.eu_info)
                logger.debug("Wrote EngineeringUnits on %s", self.node)
            except Exception:
                pass
        if self.eu_range is not None:
            try:
                eu_range_node = await self.node.get_child("0:EURange")
                await eu_range_node.set_writable()
                await eu_range_node.write_value(self.eu_range)
                logger.debug("Wrote EURange on %s", self.node)
            except Exception:
                pass

    async def run(self):
        if self.update_behaviour:
            self.update_behaviour.update()
            if self.node is not None:
                logger.debug("Updating node %s to state %s", self.node, self.update_behaviour.state)
                if self.variant_type is not None:
                    await self.node.write_value(ua.DataValue(ua.Variant(self.update_behaviour.state, self.variant_type)))
                else:
                    await self.node.write_value(self.update_behaviour.state)

    def register(self, unit: "Unit"):
        unit.register_module(self)


class Volume(Module):
    def __init__(self, initial_volume: int = 0):
        super().__init__("Volume", None, StaticBehaviour(initial_volume), unit="l")

    @property
    def volume(self) -> int:
        return self.update_behaviour.state

    @volume.setter
    def volume(self, value: int):
        self.update_behaviour.state = value

    def __sub__(self, other):
        if isinstance(other, (int)):
            new_vol = self.volume - other
            return new_vol
        raise NotImplementedError("Subtraction only supported with int or float types.")

    def __isub__(self, other):
        if isinstance(other, (int)):
            self.volume = self.volume - other
            return self
        raise NotImplementedError("In-place subtraction only supported with int or float types.")

    def __add__(self, other):
        if isinstance(other, (int)):
            new_vol = self.volume + other
            return new_vol
        raise NotImplementedError("Addition only supported with int or float types.")

    def __iadd__(self, other):
        if isinstance(other, (int)):
            self.volume = self.volume + other
            return self
        raise NotImplementedError("In-place addition only supported with int or float types.")

    def __gt__(self, other):
        if isinstance(other, (int)):
            return self.volume > other
        raise NotImplementedError("Greater than comparison only supported with int or float types.")

    def __lt__(self, other):
        if isinstance(other, (int)):
            return self.volume < other
        raise NotImplementedError("Less than comparison only supported with int or float types.")


class Temperature(Module):
    # UN/CEFACT "CEL" — degree Celsius
    _EU_INFO = _eu(4408652, "°C", "degree Celsius")

    def __init__(self, nodeid, mean, std, low: float = -50.0, high: float = 300.0):
        super().__init__("Temperature", nodeid, NormalDistBehaviour(mean, std), "°C")
        self.eu_info = self._EU_INFO
        self.eu_range = _range(low, high)


class Turbidity(Module):

    def __init__(self, nodeid, mean, std):
        super().__init__("Turbidity", nodeid, NormalDistBehaviour(mean, std), "EBC")


class Pressure(Module):
    # UN/CEFACT "BAR" — bar
    _EU_INFO = _eu(4342098, "bar", "bar")

    def __init__(self, nodeid, mean, std, low: float = 0.0, high: float = 10.0):
        super().__init__("Pressure", nodeid, NormalDistBehaviour(mean, std), "bar")
        self.eu_info = self._EU_INFO
        self.eu_range = _range(low, high)


class Timer(Module):

    def __init__(self, nodeid, name):
        super().__init__(name, nodeid, DurationTimer(0.0), "s")


class PowerOnDuration(Module):
    """Increments unconditionally while the server is running (OPC UA Duration, ms)."""

    def __init__(self, nodeid):
        super().__init__("PowerOnDuration", nodeid, ConditionalDurationTimer(0.0, condition=lambda: True), "ms")
        self.variant_type = ua.VariantType.Double


class OperationDuration(Module):
    """Increments only while the unit is in executing/production state (OPC UA Duration, ms)."""

    def __init__(self, nodeid):
        super().__init__("OperationDuration", nodeid, ConditionalDurationTimer(0.0), "ms")
        self.variant_type = ua.VariantType.Double

    def set_condition(self, fn):
        self.update_behaviour.condition = fn
