"""
Plugins that contains non-core functionalities for lihil,
mostly simple wrappers to third-party dependencies.
if not, likely to be a standalone lib
"""

from .registry import PLUGIN_REGISTRY as PLUGIN_REGISTRY
from .registry import PluginBase as PluginBase
from .registry import register_plugin_provider as register_plugin_provider
from .registry import remove_plugin_provider as remove_plugin_provider
