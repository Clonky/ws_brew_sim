from asyncua.server.event_generator import EventGenerator
from asyncua.server import Server
from asyncua.common import Node
from asyncua import ua

class Event:
    def __init__(self):
        pass

    @classmethod
    async def from_nodes(cls):
        pass

    async def trigger(self):
        pass

class TransferEvent(Event):
    def __init__(self, source_asset_id, target_asset_id, source_batch_id, target_batch_id, source_set_amount, target_set_amount, start_time, evgen: EventGenerator, source_material_id=None, target_material_id=None):
        self.source_asset_id = source_asset_id
        self.target_asset_id = target_asset_id
        self.source_batch_id = source_batch_id
        self.target_batch_id = target_batch_id
        self.source_set_amount = source_set_amount
        self.target_set_amount = target_set_amount
        self.start_time = start_time
        self.end_time = None,
        self.source_material_id = source_material_id
        self.target_material_id = target_material_id
        self.evgen = evgen
        evgen.event.SourceAssetId = source_asset_id
        evgen.event.TargetAssetId = target_asset_id
        evgen.event.SourceBatchId = source_batch_id
        evgen.event.TargetBatchId = target_batch_id
        evgen.event.SourceSetAmount = source_set_amount
        evgen.event.TargetSetAmount = target_set_amount
        evgen.event.StartTime = start_time
        if source_material_id:
            evgen.event.SourceMaterialId = source_material_id
        if target_material_id:
            evgen.event.TargetMaterialId = target_material_id


    @classmethod
    async def from_nodes(cls, source_node: Node, target_node: Node, batch_id: str, evgen: EventGenerator, server: Server):
        source_info = await cls._get_info_from_node(source_node)
        target_info = await cls._get_info_from_node(target_node)
        local_time = await server.get_node(ua.NodeId(17634, 0)).read_value()
        return cls(
            source_asset_id=source_info.get("AssetId"),
            target_asset_id=target_info.get("AssetId"),
            source_batch_id=batch_id,
            target_batch_id=batch_id,
            source_set_amount=0.0,
            target_set_amount=0.0,
            start_time=local_time,
            evgen=evgen,
            source_material_id=None,
            target_material_id=None
        )


    @staticmethod
    async def _get_info_from_node(node: Node):
        info = dict()
        asset_id = await (await node.get_child(["2:Identification", "2:AssetId"])).read_value()
        info["AssetId"] = asset_id
        return info

    async def trigger(self):
        await self.evgen.trigger()


