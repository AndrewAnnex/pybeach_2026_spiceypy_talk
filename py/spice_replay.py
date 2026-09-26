"""Build a spice-replay telemetry payload from loaded SPICE kernels.

Only numpy, spiceypy and the standard library, so the same module runs locally and in pyodide:

    spiceypy.furnsh(metakernel)
    payload = spice_replay.build(scene, events)   # scene: dict (see scenes/*.toml), events: events.json dict
    window.SpiceReplay.load(target, json.dumps(payload))

Locally: `python python/spice_replay.py scenes/cassini_20091120.toml` writes telemetry/<name>.telemetry.json.

Payload (schema "spice-replay/1"). All vectors are in `frame` (J2000), km, relative to `center`.
Times `t` are TDB seconds since `time.et0`; arrays are flat (xyz or xyzw per sample).
Quaternions are spiceypy.m2q(pxform(object_frame, frame, et)) as SPICE returns them, scalar first
([w, x, y, z]); the viewer reorders to three.js's [x, y, z, w] when it loads a track.

{
  "schema": "spice-replay/1",
  "name", "frame", "center", "units": "km", "abcorr",
  "time": {"et0", "et1", "utc0", "utc1"},            # utc(t) ~ utc0 + t (no leap second inside a window)
  "meta": {"toolkit", "generated_by", "kernels"},
  "sun": {"t": [...], "dir": [...]},                  # unit vectors center->Sun
  "bodies": [{"name", "naif_id", "frame", "radii": [a, b, c],
              "t", "pos" | null (null: this body is the center), "quat"}],
  "spacecraft": [{"name", "naif_id", "frame",
                  "t", "pos", "vel",                  # Hermite-interpolate pos with vel
                  "att_t", "att_quat", "att_gaps",    # thinned so slerp stays within attitude_tol_rad
                  "instruments": [{"name", "naif_id", "fov_frame", "shape", "boresight", "bounds",
                                   "mount_quat"}]}],  # fov_frame -> spacecraft frame (fixed mount)
  "events": [{"id", "type": "image", "t", "t_start", "exposure", "spacecraft", "instrument",
              "image", "target_in_fov", "range_km"},
             {"id", "type": "note", "t", "label"}]
}

Every event time (image mid-exposure) is also a sample time in the position and attitude tracks, so
interpolated state is exact when an image is shown.
"""

from __future__ import annotations

import json
import math
import sys

import numpy as np
import spiceypy

SCHEMA = "spice-replay/2"


# --- helpers ------------------------------------------------------------------------------------------


def continuous(quats: np.ndarray) -> np.ndarray:
    """Flip signs so neighbouring quaternions sit in the same hemisphere (q and -q are the same rotation).

    The viewer's slerp takes the short way round regardless, but thin()/slerp_error measure the angle
    between neighbours directly, so a sign flip there would read as a ~180 deg step and cost knots."""
    out = quats.copy()
    for i in range(1, len(out)):
        if np.dot(out[i], out[i - 1]) < 0:
            out[i] = -out[i]
    return out


def time_grid(et0: float, et1: float, step: float, extra=()) -> np.ndarray:
    """Uniform samples plus the window end and any extra epochs (event times), sorted and de-duplicated."""
    grid = np.concatenate([np.arange(et0, et1, step), [et1], [e for e in extra if et0 <= e <= et1]])
    return np.unique(np.round(grid, 6))


def rounded(values, digits: int) -> list:
    return [round(float(v), digits) for v in np.ravel(values)]


def slerp_error(q0, q1, frac, truth) -> float:
    """Max rotation angle between truth[k] and slerp(q0, q1, frac[k])."""
    theta = math.acos(min(1.0, max(-1.0, float(np.dot(q0, q1)))))
    if theta < 1e-12:
        interp = np.broadcast_to(q0, truth.shape)
    else:
        interp = (np.sin((1 - frac) * theta)[:, None] * q0 + np.sin(frac * theta)[:, None] * q1) / math.sin(theta)
    # same-hemisphere unit quaternions: ||qa - qb|| = 2 sin(angle / 4)
    return float(np.max(4 * np.arcsin(np.clip(np.linalg.norm(interp - truth, axis=1) / 2, 0, 1))))


def thin(t: np.ndarray, q: np.ndarray, tol: float, keep: set[int]) -> list[int]:
    """Indices of the fewest samples whose slerp stays within tol of every sample; `keep` indices are forced."""

    def ok(i: int, j: int) -> bool:
        if j == i + 1:
            return True
        if np.dot(q[i], q[j]) < math.cos(math.radians(45) / 2):  # keep spans well under 180 deg
            return False
        k = slice(i + 1, j)
        return slerp_error(q[i], q[j], (t[k] - t[i]) / (t[j] - t[i]), q[k]) <= tol

    knots, i, n = [0], 0, len(t)
    forced = sorted(k for k in keep if 0 < k < n)
    while i < n - 1:
        limit = next((k for k in forced if k > i), n - 1)  # never jump past a forced sample
        lo, hi, span = i + 1, None, 1
        while (cand := min(i + 2 * span, limit)) > lo:
            if ok(i, cand):
                lo, span = cand, span * 2
            else:
                hi = cand
                break
        while hi is not None and hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if ok(i, mid) else (lo, mid)
        knots.append(lo)
        i = lo
    return knots


# --- tracks -------------------------------------------------------------------------------------------


def body_track(body: dict, scene: dict, et0: float, et1: float, event_ets) -> dict:
    name, frame, center = body["name"], scene.get("frame", "J2000"), scene["center"]
    ets = time_grid(et0, et1, body.get("step_seconds", scene["step_seconds"]))
    quats = continuous(np.array([spiceypy.m2q(spiceypy.pxform(body["frame"], frame, et)) for et in ets]))
    is_center = spiceypy.bods2c(name) == spiceypy.bods2c(center)
    pos = None
    if not is_center:
        pos = rounded([spiceypy.spkpos(name, et, frame, scene.get("abcorr", "NONE"), center)[0] for et in ets], 3)
    return {
        "name": name,
        "naif_id": spiceypy.bods2c(name),
        "frame": body["frame"],
        "radii": rounded(spiceypy.bodvrd(name, "RADII", 3)[1], 4),
        "t": rounded(ets - et0, 6),
        "pos": pos,
        "quat": rounded(quats, 9),
    }


def spacecraft_track(sc: dict, scene: dict, et0: float, et1: float, event_ets) -> dict:
    name, frame, center = sc["name"], scene.get("frame", "J2000"), scene["center"]
    abcorr = scene.get("abcorr", "NONE")

    ets = time_grid(et0, et1, scene["step_seconds"], event_ets)
    states = np.array([spiceypy.spkezr(name, et, frame, abcorr, center)[0] for et in ets])

    # attitude: dense samples (plus event epochs), CK gaps skipped, then thinned to attitude_tol_rad
    dense = time_grid(et0, et1, scene.get("attitude_step_seconds", 2.0), event_ets)
    att_t, att_q = [], []
    for et in dense:
        try:
            att_q.append(spiceypy.m2q(spiceypy.pxform(sc["frame"], frame, et)))
            att_t.append(et)
        except spiceypy.utils.exceptions.SpiceyError:
            continue  # no pointing (CK gap)
    att_t, att_q = np.array(att_t), continuous(np.array(att_q))
    step = scene.get("attitude_step_seconds", 2.0)
    gaps = [[round(a - et0, 6), round(b - et0, 6)] for a, b in zip(att_t[:-1], att_t[1:]) if b - a > 2.5 * step]
    keep = {int(i) for i in np.searchsorted(att_t, [e for e in event_ets if et0 <= e <= et1]) if i < len(att_t)}
    # a gap edge is a forced knot too, so slerp never bridges missing pointing silently
    for a, b in gaps:
        keep |= {int(np.searchsorted(att_t, a + et0)), int(np.searchsorted(att_t, b + et0))}
    knots = thin(att_t, att_q, scene.get("attitude_tol_rad", 1e-4), keep)

    instruments = []
    for inst in sc.get("instruments", []):
        naif_id = spiceypy.bods2c(inst)
        shape, fov_frame, boresight, _, bounds = spiceypy.getfov(naif_id, 16)
        mount0 = spiceypy.pxform(fov_frame, sc["frame"], et0)
        mount1 = spiceypy.pxform(fov_frame, sc["frame"], et1)
        if not np.allclose(mount0, mount1, atol=1e-9):
            print(f"warning: {inst} mount changes over the window; using the start value", file=sys.stderr)
        instruments.append({
            "name": inst, "naif_id": naif_id, "fov_frame": fov_frame, "shape": shape,
            "boresight": rounded(boresight, 9), "bounds": [rounded(b, 9) for b in bounds],
            "mount_quat": rounded(spiceypy.m2q(mount0), 9),
        })

    print(f"  {name}: {len(ets)} state samples, attitude {len(att_t)} samples -> {len(knots)} "
          f"(tol {scene.get('attitude_tol_rad', 1e-4):g} rad), {len(gaps)} gaps", file=sys.stderr)
    return {
        "name": name, "naif_id": spiceypy.bods2c(name), "frame": sc["frame"],
        "t": rounded(ets - et0, 6),
        "pos": rounded(states[:, :3], 3),
        "vel": rounded(states[:, 3:], 6),
        "att_t": rounded(att_t[knots] - et0, 6),
        "att_quat": rounded(att_q[knots], 9),
        "att_gaps": gaps,
        "instruments": instruments,
    }


def closest_approach(name: str, scene: dict, et0: float, et1: float) -> tuple[float, float]:
    """Coarse grid minimum of the range to center, refined by golden-section search."""
    frame, abcorr, center = scene.get("frame", "J2000"), scene.get("abcorr", "NONE"), scene["center"]
    rng = lambda et: float(np.linalg.norm(spiceypy.spkpos(name, et, frame, abcorr, center)[0]))  # noqa: E731
    ets = time_grid(et0, et1, scene["step_seconds"])
    i = int(np.argmin([rng(et) for et in ets]))
    a, b = ets[max(i - 1, 0)], ets[min(i + 1, len(ets) - 1)]
    g = (math.sqrt(5) - 1) / 2
    while b - a > 1e-3:
        c, d = b - g * (b - a), a + g * (b - a)
        a, b = (a, d) if rng(c) < rng(d) else (c, b)
    et = (a + b) / 2
    return et, rng(et)


# --- payload ------------------------------------------------------------------------------------------


def scene_from(
    start: str,
    stop: str,
    center: str,
    spacecraft: str,
    spacecraft_frame: str,
    instruments=(),
    bodies=(),
    name: str | None = None,
    frame: str = "J2000",
    abcorr: str = "NONE",
    step_seconds: float = 60.0,
    attitude_step_seconds: float = 2.0,
    attitude_tol_rad: float = 1e-4,
) -> dict:
    """Assemble a scene dict from plain arguments, so a caller need not spell the whole structure out.

    `bodies` entries are either a name, whose body-fixed frame is taken to be IAU_<NAME> (true for
    planets and satellites, not for a comet with a CK-based frame), or a dict as scenes/*.toml writes
    it: {"name": ..., "frame": ..., "step_seconds": ...}.
    """
    return {
        "name": name or f"{spacecraft.lower()}_at_{center.lower()}",
        "start": start, "stop": stop, "center": center, "frame": frame, "abcorr": abcorr,
        "step_seconds": step_seconds,
        "attitude_step_seconds": attitude_step_seconds,
        "attitude_tol_rad": attitude_tol_rad,
        "bodies": [b if isinstance(b, dict) else {"name": b, "frame": f"IAU_{b.upper()}"} for b in bodies],
        "spacecraft": [{"name": spacecraft, "frame": spacecraft_frame, "instruments": list(instruments)}],
    }


def build(scene: dict | None = None, events: dict | None = None, **kwargs) -> dict:
    """Telemetry payload from the kernels already loaded into the pool.

    Either `build(scene, events)` with a scene dict (what scenes/*.toml parse to), or
    `build(events=..., start=..., stop=..., center=..., spacecraft=..., ...)` to have `scene_from`
    build it from arguments.
    """
    if scene is None:
        scene = scene_from(**kwargs)
    elif kwargs:
        raise TypeError(f"build() got both a scene and {sorted(kwargs)}")
    et0, et1 = spiceypy.str2et(scene["start"]), spiceypy.str2et(scene["stop"])
    frames = (events or {}).get("frames", [])
    # rounded like time_grid's samples, so each event epoch finds its own sample (and forced attitude knot)
    event_ets = sorted({round(f["mid_et"], 6) for f in frames if et0 <= f["mid_et"] <= et1})

    payload = {
        "schema": SCHEMA,
        "name": scene["name"],
        "frame": scene.get("frame", "J2000"),
        "center": scene["center"],
        "units": "km",
        "abcorr": scene.get("abcorr", "NONE"),
        "time": {"et0": et0, "et1": et1, "utc0": spiceypy.et2utc(et0, "ISOC", 3), "utc1": spiceypy.et2utc(et1, "ISOC", 3)},
        "meta": {"toolkit": spiceypy.tkvrsn("TOOLKIT"), "generated_by": "spice_replay.py",
                 "kernels": scene.get("metakernel")},
    }

    sun_ets = time_grid(et0, et1, max(scene["step_seconds"], 600.0))
    sun = np.array([spiceypy.spkpos("SUN", et, payload["frame"], payload["abcorr"], scene["center"])[0] for et in sun_ets])
    payload["sun"] = {"t": rounded(sun_ets - et0, 6), "dir": rounded(sun / np.linalg.norm(sun, axis=1)[:, None], 7)}

    payload["bodies"] = [body_track(b, scene, et0, et1, event_ets) for b in scene.get("bodies", [])]
    payload["spacecraft"] = [spacecraft_track(sc, scene, et0, et1, event_ets) for sc in scene["spacecraft"]]

    out_events = []
    for f in frames:
        if not et0 <= f["mid_et"] <= et1:
            continue
        out_events.append({
            "id": f["product_id"], "type": "image",
            "t": round(f["mid_et"] - et0, 6), "t_start": round(f["start_et"] - et0, 6), "exposure": f["exposure_s"],
            "spacecraft": (events or {}).get("observer", scene["spacecraft"][0]["name"]),
            "instrument": (events or {}).get("instrument"),
            "image": f["image"], "target_in_fov": f.get("target_in_fov"), "range_km": f.get("target_range_km"),
        })
    for sc in scene["spacecraft"]:
        et, dist = closest_approach(sc["name"], scene, et0, et1)
        if et0 < et < et1:
            out_events.append({"id": f"{sc['name']}_CA", "type": "note", "t": round(et - et0, 6),
                               "label": f"{sc['name']} closest approach to {scene['center']}: {dist:,.0f} km "
                                        f"({spiceypy.et2utc(et, 'ISOC', 0)} UTC)"})
    payload["events"] = sorted(out_events, key=lambda e: e["t"])
    return payload


# --- local CLI --------------------------------------------------------------------------------------------


def main(argv: list[str]) -> None:
    import tomllib
    from contextlib import chdir
    from pathlib import Path

    scene_path = Path(argv[0]).resolve()
    scene = tomllib.loads(scene_path.read_text())
    bundle = (scene_path.parent / scene["bundle"]).resolve()
    mk = next(p for p in bundle.iterdir() if p.suffix.lower() == ".tm")
    scene["metakernel"] = mk.name
    events_path = bundle / scene.get("events", "events.json")
    events = json.loads(events_path.read_text()) if events_path.exists() else None

    spiceypy.kclear()
    with chdir(bundle):  # PATH_VALUES in the minified metakernels are relative to the working directory
        spiceypy.furnsh(mk.name)
    print(f"building {scene['name']} from {bundle}", file=sys.stderr)
    payload = build(scene, events)

    out = Path(argv[1]) if len(argv) > 1 else scene_path.parents[1] / "telemetry" / f"{scene['name']}.telemetry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, separators=(",", ":"))
    out.write_text(text)
    n_img = sum(e["type"] == "image" for e in payload["events"])
    print(f"wrote {out} ({len(text) / 1e6:.2f} MB, {n_img} image events)", file=sys.stderr)
    for e in payload["events"]:
        if e["type"] == "note":
            print(f"  note: {e['label']}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
