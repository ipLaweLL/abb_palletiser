# GPU pallet viewer prototype

This experimental branch keeps the same planner, simulator, and ABB integration.
Only the 3D rendering component changes when using the dedicated launcher.

## Run
From your activated Python virtual environment:

```powershell
pip install -r requirements-gpu.txt
python .\gpu_main.py
```

The original Matplotlib engineering GUI still runs with `python .\main.py`.
The end-user GUI still runs with `python .\user_main.py`.

The OpenGL viewer supports interactive orbit and zoom. Simulate All and Auto Rotate
operate through the same `set_data` and `rotate_camera` API as the Matplotlib
viewer. Do not use the experimental launcher for robot acceptance testing until
you've checked that all product geometry, placement statuses, camera interaction,
and computer OpenGL drivers behave as expected.

Notes:
- PyQtGraph uses your computer's OpenGL stack; GPU acceleration depends on drivers.
- Rendering fidelity is experimental (simple meshes rather than CAD models).
- Existing validation and floor-first algorithms are unchanged.
