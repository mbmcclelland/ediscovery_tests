"""
dr-load-recorder — persistent monitoring daemon for long-running load tests.

A daemon ticks every 10s, samples system + Digital Reef API + log streams,
and writes everything to a SQLite TSDB. The `dr-load record/campaign/report`
CLI verbs read and write this store; a future Textual TUI is a third reader.

Design contract: see memory/dr_load_monitor_vision.md.
"""

from recorder.store import Store, default_db_path

__all__ = ["Store", "default_db_path"]
