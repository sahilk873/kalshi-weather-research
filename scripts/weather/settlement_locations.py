"""Versioned settlement-site registry supplied by the project owner.

Coordinates are retained as reconciliation evidence; source-specific displayed
coordinates can differ slightly, so the registry preserves the stated source
and does not imply licensed TWC precision beyond the supplied listing key.
"""
from __future__ import annotations

SETTLEMENT_LOCATIONS = {
    "KNYC": {"city": "NYC", "product_key": "CLINYC", "site": "Central Park, New York City", "latitude": 40.77900, "longitude": -73.96925, "coordinate_source": "IEM/NWSCLI; user-supplied listing reconciliation", "display_coordinate": "TWC/WU approximately 40.78,-73.97"},
    "KLAX": {"city": "Los Angeles", "product_key": "CLILAX", "site": "Los Angeles International Airport (LAX)", "latitude": 33.93816, "longitude": -118.38653, "coordinate_source": "IEM/NWSCLI; user-supplied listing reconciliation", "display_coordinate": "TWC/WU approximately 33.96,-118.40"},
    "KAUS": {"city": "Austin", "product_key": "CLIAUS", "site": "Austin-Bergstrom International Airport", "latitude": 30.18304, "longitude": -97.67987, "coordinate_source": "Synoptic/MesoWest; user-supplied listing reconciliation", "display_coordinate": "TWC/WU approximately 30.16,-97.69"},
}
