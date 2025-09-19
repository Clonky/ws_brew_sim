from dataclasses import dataclass


@dataclass
class NodeId:
    ns: int
    id: str
