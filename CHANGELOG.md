# Changelog

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
