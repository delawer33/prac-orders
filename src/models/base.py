from typing import Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeMeta, declarative_base

metadata = sa.MetaData()


class BaseServiceModel:
    @classmethod
    def on_conflict_constraint(cls) -> Optional[Tuple]:
        return None


Base: DeclarativeMeta = declarative_base(metadata=metadata, cls=BaseServiceModel)
