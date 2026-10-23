from pydantic import AwareDatetime, BaseModel, Field, ConfigDict
from typing import Literal

class TelemetryMessage(BaseModel):

    model_config = ConfigDict(extra="forbid")   
    asset_id: str = Field(min_length=1)
    asset_type: Literal["haul_truck"]
    timestamp: AwareDatetime
    seq: int = Field(strict=True, gt=0, description="Reading sequence number, +1 per reading")
    engine_temp_c: float = Field(strict=True, gt=-40, lt=200, description="Engine coolant temperature, °C")
    hyd_pressure_bar: float = Field(strict=True, ge=0, description="Hydraulic system pressure, bar")
    vibration_mm_s: float = Field(strict=True, ge=0, description="Vibration velocity, mm/s")
    fuel_pct: float = Field(strict=True, ge=0, le=100, description="Fuel tank level, % of capacity")
    