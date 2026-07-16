from dataclasses import dataclass
from enum import Enum

from pdi.models import Asset, AssetSource, Blob


class ActionType(str, Enum):
    CREATE_ASSET = "create_asset"
    CREATE_BLOB = "create_blob"
    CREATE_SOURCE = "create_source"
    UPDATE_SOURCE = "update_source"


@dataclass
class Action:
    type: ActionType
    asset: Asset | None = None
    blob: Blob | None = None
    source: AssetSource | None = None