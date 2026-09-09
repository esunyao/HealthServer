from .base import BaseRepository
from .overview import OverviewMixin
from .recovery import RecoveryMixin
from .releases import ReleasesMixin
from .rows import RowsMixin
from .tasks import TasksMixin
from .trace import TraceMixin


class Repository(
    BaseRepository,
    OverviewMixin,
    TasksMixin,
    TraceMixin,
    RowsMixin,
    ReleasesMixin,
    RecoveryMixin,
):
    """领域仓库门面：按领域分文件实现，单实例注入 app.state。"""
