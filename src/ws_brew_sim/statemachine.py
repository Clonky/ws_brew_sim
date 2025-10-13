from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass
from asyncua import Server
from asyncua.ua import NodeId
from asyncua.common import Node
import logging

logger = logging.getLogger(__name__)


TRANSITION_ID = 2310
STATE_ID = 2307
CURRENT_STATE_ID = 2760

@dataclass
class State:
    name: str
    node: Node
    state_number: int

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
    substates: list[StateMachineLevel] = None

    async def write_state(self, state_name: str) -> None:
        state = next((state for state in self.possible_states if state.name == state_name), None)
        if state:
            logger.info("Writing state %s to node %s", state, self.curr_state)
            await self.curr_state.write_value(state.state_number)
        else:
            raise ValueError(f"State {state_name} not found in possible states.")

@dataclass
class StateMachineTree:
    root: StateMachineLevel

    @classmethod
    async def build_tree(cls, server: Server, parent_node_id: NodeId):
        parent_node = server.get_node(parent_node_id)
        operation_mode_node = await parent_node.get_child(["4:Monitoring", "4:Status", "4:OperationMode"])
        root = await cls.get_states_and_transitions(server, operation_mode_node.nodeid)
        return cls(root)

    @staticmethod
    async def get_states_and_transitions(server: Server, parent_node_id: NodeId):
        states_and_transitions = await server.get_node(parent_node_id).get_children()
        states = [istate for istate in states_and_transitions if await istate.read_type_definition() ==  NodeId(STATE_ID)]
        states = [State(
            name = (await istate.read_display_name()).Text,
            node=istate,
            state_number= await (await istate.get_child("0:StateNumber")).read_value()
            ) for istate in states
        ]
        for state in states:
            logger.info("Adding state: %s", state)
        transitions = [itransition for itransition in states_and_transitions if await itransition.read_type_definition() ==  NodeId(TRANSITION_ID)]
        transitions = [Transition(
            name = (await itransition.read_display_name()).Text,
            node=itransition,
            transition_number= await (await itransition.get_child("0:TransitionNumber")).read_value()
            ) for itransition in transitions
        ]
        current_state_node = await server.get_node(parent_node_id).get_child("0:CurrentState")
        # If its neither State, nor Transition, nor CurrentState, it must be a substate (not necessarily always true)
        substates = [istate for istate in states_and_transitions if
                      await istate.read_type_definition() !=  NodeId(STATE_ID) and
                      await istate.read_type_definition() !=  NodeId(TRANSITION_ID) and
                      await istate.read_type_definition() !=  NodeId(CURRENT_STATE_ID)]
        # Go into recursive mode here
        substates = [await StateMachineTree.get_states_and_transitions(server, istate.nodeid) for istate in substates]
        return StateMachineLevel(current_state_node, states, transitions, substates)