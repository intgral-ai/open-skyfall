# Dependency notices

OpenSkyfall project-authored code is MIT. The original Open Assembly CAD copyright notice is retained. Dependencies retain their own licenses.

The installed package metadata reports Apache-2.0 for build123d 0.13.0, cadquery-ocp-novtk 8.0.1.1.0, and Specify 0.1.7. The OpenCascade native libraries retain their upstream LGPL terms and exception. Do not treat the binding package's license as a replacement for the native library terms.

Trimesh, FastAPI, MCP, Three.js, and the MCP Apps SDK carry MIT licenses. NumPy and SciPy include BSD-family and bundled-library notices. Uvicorn is BSD-3-Clause. The Python wheels install their own license files. Preserve those files when redistributing dependencies.

The Vite bundle includes third-party JavaScript. Relevant npm license files are retained under `web/public/licenses/` and included in the built viewer. This notice does not claim that project code licenses third-party libraries.

The viewer embeds Geist and Geist Mono variable WOFF2 files, Copyright 2024 The Geist Project Authors, under the SIL Open Font License 1.1. The files in `web/src/fonts/` are unmodified Geist font files, with byte counts and SHA256 recorded in `web/src/fonts/sources.json`. The build inlines them as data URLs in the viewer CSS. The license ships as `web/public/licenses/Geist-OFL.txt` in the built viewer. Noto Sans SC is named as a fallback family only and is not bundled.

The saved text-to-cad files under `references/upstream/` are unmodified MIT reference snapshots with their original licenses. smlibpy 0.3.4 declares MIT AND Apache-2.0 AND OFL-1.1. Its wrapper is MIT; its bundled usd-brep kernel uses Apache-2.0 and its font component uses OFL-1.1. Native wheels and dependency binaries are not bundled here. Retain the installed upstream LICENSE and NOTICE files when redistributing that dependency. See https://github.com/awv-informatik/smlibpy and https://github.com/NVIDIA-Omniverse/usd-brep.

No SKY-001 code or weights, CAD-Recode weights or research-only CAD dataset is bundled. All generated mechanical fixtures are project-authored and may be reused under CC0-1.0.

The relay/socket screenshots show project-authored illustrative geometry. The OMRON datasheet and original user CAD inputs are not distributed. OMRON and Skyfall names identify the referenced products and workflow; their owners have not endorsed this project. The source-fidelity audit remains part of the example.
