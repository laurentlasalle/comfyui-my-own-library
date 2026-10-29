# Changelog

Versions follow the usual pattern: the middle number goes up with new features, the last one with fixes only. The version is shown at the bottom of the library's left column and in ComfyUI's terminal at startup.

## 0.7.0 (2026-10-29)

- Model Filter, sort and Similarity menus styled like ComfyUI's own (Templates).
- Model Filter accepts several models at once, with **Clear all**.
- Sort by size: **Largest first** and **Smallest first**. A work counts the size of all its versions; hovering a card shows it.
- **Reset thumbnail** sits next to **New thumbnail** on the video player. Neither restarts the video: it keeps playing or stays paused.
- The **+** of Categories is smaller and aligned with the counts.
- Version number shown in the window and in the terminal, and this changelog.

## 0.6.0 (2026-10-29)

- **Detect versions** button to show or hide the suggestion banner, with the number of suggestions. The **Similarity** menu stays reachable when nothing is found.
- **Review** goes on to the next suggestion after grouping or **Not the same work**, with **Skip**.
- **New thumbnail** / **Reset thumbnail** for videos: use the frame shown in the player.
- Video thumbnails skip nearly black first frames; existing ones are checked once in the background.
- Background work is reported in the terminal.
- Window design matched to Templates: left column, header, search, close button, filter buttons, four cards per row.

## 0.5.2 (2026-10-29)

- Progress bar of fixed width; long file names are cut in the middle.

## 0.5.1 (2026-10-29)

- Progress advances one file at a time.

## 0.5.0 (2026-10-29)

- Progress bar with **Cancel** for adding, moving, deleting from output and removing from the library; other actions wait.
- Each file and a summary are printed in the terminal.
- The Output view refreshes afterwards, keeping its filters.

## 0.4.0 (2026-10-28)

- Window size matched to Templates, **Maximize** button, click outside to close.
- Screenshot in the README.

## 0.3.0 (2026-10-28)

- Duplicates: identical files are linked to the creation already in the library instead of copied again; **Duplicates** view to merge identical creations.

## 0.2.0 (2026-10-28)

- Reorder the versions of a work by hand (drag in the strip, **Alt+↑** / **Alt+↓**), **Sort by date**.

## 0.1.0 (2026-10-28)

- First release: output view, library copies, categories, tags, notes, favorites, model families, versions with similarity-based suggestions, video and audio support.
