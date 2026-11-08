# models/telemetry_schema.py
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class MetricValue:
    value: Optional[float | int | str]
    unit: str
    source: str  # "Garmin Connect", "Manual Input", "Calculated"
    timestamp: Optional[datetime]
    baseline: Optional[float] = None
    data_coverage_pct: Optional[float] = None

    @property
    def is_available(self) -> bool:
        return self.value is not None
