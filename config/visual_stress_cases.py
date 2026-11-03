"""Visual-only stress orders for the GUI.

Intentionally separate from VALIDATION_ORDERS so the existing
130-case automated planner validation stays unchanged.
These inputs are not guaranteed to fit every pallet configuration.
"""

VISUAL_STRESS_CASES = [
    {"name": "Stress 01", "20L": 2, "10L": 3, "1L": 2, "4L": 4},
    {"name": "Stress 02", "20L": 5, "10L": 4, "1L": 3, "4L": 6},
    {"name": "Stress 03", "20L": 3, "10L": 5, "1L": 0, "4L": 9},
    {"name": "Stress 04", "20L": 7, "10L": 2, "1L": 4, "4L": 3},
    {"name": "Stress 05", "20L": 1, "10L": 8, "1L": 5, "4L": 8},
    {"name": "Stress 06", "20L": 4, "10L": 6, "1L": 2, "4L": 10},
    {"name": "Stress 07", "20L": 6, "10L": 0, "1L": 7, "4L": 4},
    {"name": "Stress 08", "20L": 2, "10L": 10, "1L": 4, "4L": 6},
    {"name": "Stress 09", "20L": 8, "10L": 5, "1L": 3, "4L": 5},
    {"name": "Stress 10", "20L": 3, "10L": 4, "1L": 0, "4L": 14},
    {"name": "Stress 11", "20L": 5, "10L": 7, "1L": 6, "4L": 2},
    {"name": "Stress 12", "20L": 0, "10L": 11, "1L": 4, "4L": 10},
    {"name": "Stress 13", "20L": 4, "10L": 3, "1L": 8, "4L": 7},
    {"name": "Stress 14", "20L": 7, "10L": 8, "1L": 2, "4L": 4},
    {"name": "Stress 15", "20L": 2, "10L": 6, "1L": 9, "4L": 12},
    {"name": "Boundary 01", "20L": 9, "10L": 0, "1L": 0, "4L": 0},
    {"name": "Boundary 02", "20L": 10, "10L": 0, "1L": 0, "4L": 0},
    {"name": "Boundary 03", "20L": 18, "10L": 0, "1L": 0, "4L": 0},
    {"name": "Boundary 04", "20L": 3, "10L": 4, "1L": 0, "4L": 15},
    {"name": "Boundary 05", "20L": 3, "10L": 4, "1L": 0, "4L": 16},
    {"name": "Boundary 06", "20L": 3, "10L": 4, "1L": 0, "4L": 17},
]
