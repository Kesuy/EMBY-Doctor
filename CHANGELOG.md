# Changelog

## Unreleased

- Renamed the project and application from **Emby Media Library Batch Processor** to **EMBY Doctor**.
- Renamed Windows EXE / CI artifacts to `EMBY-Doctor` / `EMBY-Doctor-Windows`.
- Updated GUI, CLI, package metadata, User-Agent, README, CI and Release branding.

## v1.3.0

- Added click-to-sort support to all result-list columns, with ascending/descending indicators.
- Added double-click opening for the **movie directory** column across result lists.
- Reused the configured directory-path prefix when opening Emby server paths from Windows.
- Limited actor-list double-click opening to the first associated directory to avoid opening multiple Explorer windows.

## v1.2.0

- Added right-click actions to missing-actor scan results for copying movie names, refreshing metadata, and opening the containing directory.
- Added multi-select batch metadata refresh using Emby FullRefresh while preserving existing images.
- Added a configurable directory path prefix for opening Emby server paths through Windows UNC network shares.
- Updated the path-prefix UI example to use `\\192.168.1.10`.

## v1.1.0

- Added independent **all libraries / selected libraries** scope controls for all three tools.
- Added a separate **movie directory** column while keeping the full media file path.
- Added CSV export for actor-image and director results; missing-actor CSV now includes the movie directory.
- Added actor result mapping to associated movie directories in the selected scan scope.
- Replaced the application icon source with the provided Emby SVG.
- Windows CI now generates a standard multi-size ICO directly from the SVG before PyInstaller packaging.
- Removed the redundant large branding header from inside the application window.
- Clarified the optional generic Video scan label.

## v1.0.0

- Added Windows desktop UI based on Tkinter.
- Added shared Emby URL/API Key/SSL/timeout settings.
- Added independent library ID configuration for each of the three tools.
- Added output tables for actor images, missing-actor movies, and director metadata.
- Added connection test and persistent `settings.json` beside the EXE.
- Added local `reports/` CSV exports and `backups/` director metadata backups beside the EXE.
- Added actor Primary-image deletion with preview and confirmation.
- Added missing Actor metadata scanner for Movie/Video items.
- Added Director metadata deletion while preserving other People entries.
- Added CLI compatibility, unit tests, Windows EXE CI artifacts, and tag-based GitHub Release publishing.
