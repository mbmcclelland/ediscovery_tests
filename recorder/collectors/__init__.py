"""
Per-tick samplers. Each module exposes a `sample()` function that returns
a flat dict {signal_name: numeric_value}. Collector failures should never
crash the daemon — return an empty dict and log.
"""

from recorder.collectors import dr_api, logs, system

__all__ = ["system", "dr_api", "logs"]
