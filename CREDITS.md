# Credits

Third-party data and assets redistributed in this repository, and the sources the demos read from.

## SPICE kernels

All kernels under `kernels/` come from NAIF's PDS archives and are in the public domain. They are
**subsets**: each was sliced to its demo's time window (with `spkmerge` and `ckslicer`) so the browser
downloads megabytes rather than gigabytes. The geometry they reproduce is unchanged within the
tolerances recorded in each demo, but they are not substitutes for the archived originals.

- **Cassini** — `co-s_j_e_v-spice-6-v1.0/cosp_1000`, NAIF/JPL.
  `kernels/cassini_flyby/` covers 2009-11-21 01:00–03:00 UTC (the E8 Enceladus flyby), 1.8 MB sliced
  from 505 MB.
- **Eclipse demo** — `naif0012.tls`, `pck00010.tpc` and a subset of `de438s.bsp`, NAIF/JPL.
- Kernels fetched at runtime from
  [AndrewAnnex/spiceypylessonkernels](https://github.com/AndrewAnnex/spiceypylessonkernels) are
  likewise NAIF PDS archive products.

## Imagery

- **Cassini ISS NAC frames** in the 3D replay are loaded at runtime from
  [OPUS](https://opus.pds-rings.seti.org/) (PDS Ring-Moon Systems Node). They are not redistributed
  here; the payload carries their URLs. Credit: NASA / JPL-Caltech / Space Science Institute.
- **Enceladus global mosaic** (`assets/textures/enceladus_cassini_mosaic_global_100m_schenk2024_600m.jpg`)
  — USGS Astrogeology, from Cassini ISS data, Schenk (2024). Credit: NASA / JPL-Caltech / SSI / USGS.
- **Mars basemap** on the M20 slide is served by
  [MMGIS](https://trek.nasa.gov/) (HiRISE/CTX mosaic). Credit: NASA / JPL-Caltech / UArizona / USGS.

## 3D models

- **Cassini-Huygens** (`assets/models/cassini-huygens-b.nodraco.glb`) — NASA 3D Resources,
  "Cassini-Huygens (B)". Draco decompressed for use without a runtime decoder; geometry unchanged.
  Credit: NASA.
- **Saturn** (`assets/models/saturn_1_120536.usdz`) — NASA Science Solar System resources.
  Credit: NASA.

## Software

- [SpiceyPy](https://github.com/AndrewAnnex/SpiceyPy) (MIT) wrapping NAIF's
  [CSPICE](https://naif.jpl.nasa.gov/naif/toolkit.html) toolkit.
- [PyScript](https://pyscript.net/) and [Pyodide](https://pyodide.org/) (Apache-2.0 / MPL-2.0).
- [reveal.js](https://revealjs.com/) (MIT).
- [three.js](https://threejs.org/) (MIT), bundled into `js/spice-replay.min.js`.
- `js/spice-replay.min.js` and `py/spice_replay.py` are the talk's own replay viewer and telemetry
  builder, vendored here so the deck is self-contained.

SPICE is produced by NASA's Navigation and Ancillary Information Facility (NAIF) at JPL. Neither
NAIF, NASA, ESA nor the USGS endorse this talk.
