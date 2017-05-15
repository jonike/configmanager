from .lightweight import LwConfig as LwConfig
from .lightweight import LwItem as LwItem
from .exceptions import _ConfigValueMissing
from .base import ItemAttribute

#
# Only the names assigned below and the public attributes of respective classes are part of the v1.0 public interface.
# Names like Lw* and _* are NOT part of the interface and may change at any time in future.
#

Item = LwItem
Item.__name__ = 'Item'
Item.__module__ = 'configmanager.v1'

Config = LwConfig
Config.__name__ = 'Config'
Config.__module__ = 'configmanager.v1'

ConfigValueMissing = _ConfigValueMissing
ConfigValueMissing.__name__ = 'ConfigValueMissing'
ConfigValueMissing.__module__ = 'configmanager.v1'
