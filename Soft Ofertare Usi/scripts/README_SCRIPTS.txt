Release automation (project root, not inside "v1.0.0 stabila"):

1) build_release.bat  — Cleans dist/build, runs PyInstaller (ofertare.exe, admin.exe), copies outputs into "v1.0.0 stabila".

2) After a successful build, compile Windows installers from folder "v1.0.0 stabila\installers" using compile_installers.bat (requires Inno Setup 6).

See docs\RELEASE_README.md and RELEASE_REBUILD_REPORT.md in the release folder (or project root) for full steps.
