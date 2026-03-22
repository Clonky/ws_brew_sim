from __future__ import annotations

import logging
from dataclasses import dataclass, field

from asyncua import Server
from asyncua.common import Node
from asyncua.ua import NodeId

logger = logging.getLogger(__name__)


TRANSITION_ID = 2310
STATE_ID = 2307
CURRENT_STATE_ID = 2760


@dataclass
class State:
    name: str
    node: Node
    state_number: int
    curr_state_node: Node
    active: bool = False
    substates: StateMachineLevel = field(default_factory=list)

    def __repr__(self):
        return f"State(name={self.name}, node_id={self.node.nodeid}, state_number={self.state_number})"


@dataclass
class Transition:
    name: str
    node: Node
    transition_number: int


@dataclass
class StateMachineLevel:
    curr_state: Node
    possible_states: list[State]
    possible_transitions: list[Transition]

    async def write_state(self, state_name: str) -> None:
        state = next(
            (state for state in self.possible_states if state.name == state_name), None
        )
        if state:
            logger.info("Writing state %s to node %s", state, self.curr_state)
            await self.curr_state.write_value(state.state_number)
        else:
            raise ValueError(f"State {state_name} not found in possible states.")


@dataclass
class StateMachineTree:
    root: StateMachineLevel
    default_mode: None | str = None

    @classmethod
    async def build_tree_operation_mode(cls, server: Server, parent_node_id: NodeId):
        try:
            parent_node = server.get_node(parent_node_id)
            operation_mode_node = await parent_node.get_child(
                ["8:Monitoring", "8:Status", "12:OperatingMode"]
            )
            root = await cls.get_states_and_transitions(
                server, operation_mode_node.nodeid
            )
        except Exception:
            logger.warning("OperatingMode state machine not found under node %s", parent_node_id)
            return None
        return cls(root)

    @classmethod
    async def build_tree_machine_state(cls, server: Server, parent_node_id: NodeId):
        try:
            machinery_idx = await server.get_namespace_index(
                "http://opcfoundation.org/UA/Machinery/"
            )
            machine_state_node = server.get_node(NodeId(1002, machinery_idx))
            parent_node = server.get_node(parent_node_id)
            machine_state_local = await parent_node.get_child(
                [
                    f"{machinery_idx}:Monitoring",
                    f"{machinery_idx}:Status",
                    f"{machinery_idx}:MachineryItemState",
                ]
            )
            root = await cls.get_states_and_transitions(
                server, machine_state_local.nodeid, src_override=machine_state_node.nodeid
            )
        except Exception:
            logger.warning("MachineryItemState not found under node %s", parent_node_id)
            return None
        return cls(root)

    @staticmethod
    async def get_states_and_transitions(
        server: Server, parent_node_id: NodeId, src_override: NodeId | None = None
    ):
        states_and_transitions = await server.get_node(parent_node_id).get_children()
        if src_override:
            states_and_transitions = await server.get_node(src_override).get_children()
        current_state_node = await server.get_node(parent_node_id).get_child(
            "0:CurrentState"
        )
        logger.warn(current_state_node)
        states = [
            istate
            for istate in states_and_transitions
            if await istate.read_type_definition() == NodeId(STATE_ID)
        ]
        states = [
            State(
                name=(await istate.read_display_name()).Text,
                node=istate,
                state_number=await (
                    await istate.get_child("0:StateNumber")
                ).read_value(),
                curr_state_node=current_state_node,
            )
            for istate in states
        ]
        substates = [
            istate
            for istate in states_and_transitions
            if await istate.read_type_definition() != NodeId(STATE_ID)
            and await istate.read_type_definition() != NodeId(TRANSITION_ID)
            and await istate.read_type_definition() != NodeId(CURRENT_STATE_ID)
            and (await istate.read_display_name()).Text != "DefaultInstanceBrowseName"
        ]
        if substates:
            for istate, isubstate in zip(states, substates):
                logger.info("Adding state: %s", istate)
                istate.substates = await StateMachineTree.get_states_and_transitions(
                    server, isubstate.nodeid
                )
        transitions = [
            itransition
            for itransition in states_and_transitions
            if await itransition.read_type_definition() == NodeId(TRANSITION_ID)
        ]
        transitions = [
            Transition(
                name=(await itransition.read_display_name()).Text,
                node=itransition,
                transition_number=await (
                    await itransition.get_child("0:TransitionNumber")
                ).read_value(),
            )
            for itransition in transitions
        ]
        return StateMachineLevel(current_state_node, states, transitions)

    def __getitem__(self, name: str) -> State | None:
        states = self.get_all_states()
        return next((istate for istate in states if istate.name == name), None)

    def disable_all_states(self):
        states = self.get_all_states()
        for state in states:
            state.active = False

    def get_all_states(self) -> list[State]:
        def collect_states(level: StateMachineLevel) -> list[State]:
            states = level.possible_states.copy()
            for state in level.possible_states:
                if state.substates:
                    states.extend(collect_states(state.substates))
            return states

        return collect_states(self.root)

    def get_path_to_state(self, target_state_name: str) -> list[State] | None:
        def find_path(
            level: StateMachineLevel, path: list[State]
        ) -> list[State] | None:
            for state in level.possible_states:
                new_path = path + [state]
                if state.name == target_state_name:
                    return new_path
                if state.substates:
                    result = find_path(state.substates, new_path)
                    if result:
                        return result
            return None

        return find_path(self.root, [])

    def activate_state(self, statename: str):
        states = self.get_path_to_state(statename)
        for state in states:
            state.active = True

    def goto_default(self):
        if self.default_mode:
            self.disable_all_states()
            self.activate_state(self.default_mode)

    def is_in_production(self):
        states = self.get_path_to_state("Production")
        production = states[-1]
        return production.active

    def start_production(self):
        self.disable_all_states()
        states = self.get_path_to_state("Production")
        for state in states:
            state.active = True

    def stop_production(self):
        self.disable_all_states()
        states = self.get_path_to_state("Production")
        for state in states:
            state.active = False

    def recursively_get_states(self, state: State, collection: list[State]):
        if state.substates == []:
            collection.append(state)
            return collection
        else:
            collection.append(state)
            for istate in state.substates.possible_states:
                return collection + self.recursively_get_states(istate, collection)


@dataclass
class MachineState(StateMachineTree):
    def __post_init__(self):
        self.set_default()

    def start_production(self):
        self.disable_all_states()
        states = self.get_path_to_state("Executing")
        for state in states:
            state.active = True

    def stop_production(self):
        self.disable_all_states()
        states = self.get_path_to_state("NotExecuting")
        for state in states:
            state.active = True

    def set_default(self):
        self.stop_production()
