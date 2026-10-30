# Changelog

Versions follow the usual pattern: the middle number goes up with new features, the last one with fixes only. The version is shown at the bottom of the library's left column and in ComfyUI's terminal at startup.

## 0.10.1 (2026-10-30)

- Fixed: an error in the terminal when the library size was computed while copies were being renamed in the background.

## 0.10.0 (2026-10-30)

- Segments already in the library are recognized (Easy-Media by the folder they came from, others by their lengths): same **Part** / **Combined from** marks, **Hide parts**, and **Remove parts** with a confirmation listing them, once their final video is in the library.
- Library copies keep a readable name: the original name plus the start of their id, for example `mauriceruns_00001_ (5806bab7).mp4`. Existing copies are renamed once in the background.
- The **Library directory** setting shows the size of the whole library.

## 0.9.0 (2026-10-30)

- Segments of combined videos (Easy-Media projects read from their project.json; other tools by length, timing and first frame): **Combined from N parts** / **Part 2 of 4** on the Output cards, **Hide parts** (on by default), and **Delete parts** once the final video is in the library, with a confirmation listing every file and its size. Segments no longer count in the new files badge.
- **Library directory** setting: move the library to another folder (verified copy, then the old folder is deleted) or use a folder as it is, without restarting. The folder at the bottom of the left column opens the setting.
- Settings grouped in two sections, **Options** and **File Management**.
- Model families: **Krea 2** (file names and its own nodes) and **FLUX.1 Krea**. Utility nodes (empty latents, ModelSampling) no longer suggest a family, which gave a wrong "SD3". Official model files of ComfyUI's templates are recognized exactly. Existing creations are recalculated.
- The **Model** field suggests the models known to ComfyUI's Browse Templates, in addition to the library's families.

## 0.8.0 (2026-10-29)

- Version suggestions across workflows: creations made from the same source file (Load Image of image-to-image workflows) are related like those of one workflow; at the Loose level, near-identical creations (92 % or more) are suggested whatever their origin. The banner says why.
- Thumbnails centered on the face when a picture has a single subject (OpenCV), portrait pictures framed on their upper third. Existing thumbnails are processed once in the background.
- Settings in ComfyUI's Settings panel: center on faces, play videos on hover, new files badge, remove from output after adding (default), similarity.
- Clear icon in the search field (as in Templates); **Esc** clears the search.
- Opening **Detect versions** from further down the grid scrolls back to the banner.

## 0.7.4 (2026-10-29)

- **Changes since**: prompt changes are shown in the text itself, like tracked changes (added words highlighted, removed ones struck through, at their place). A prompt that is mostly new shows **Rewritten**, with **Show differences**.
- Fixed: long prompts and file names overflowed the **Changes since** box. Model and LoRA names are cut with an ellipsis; hover one for its full name.

## 0.7.3 (2026-10-29)

- The buttons that reorder versions are now labeled **Move earlier** / **Move later** (they were two bare arrows that looked like browsing).
- The version and removal buttons of the detail panel form a second, smaller row of their own.
- Thumbnails already loaded are reused when the grid is redrawn instead of being requested again (fewer "connection reset" messages in the Windows terminal).

## 0.7.2 (2026-10-29)

- Fixed: with many versions, the first ones could not be reached in the version strip.
- The version shown stays visible in the strip when browsing with **↑** / **↓**.
- The mouse wheel scrolls the version strip sideways.
- A click on the preview leaves any text field, so the arrows browse again.

## 0.7.1 (2026-10-29)

- Fixed: "null" appeared next to **New thumbnail** after **Reset thumbnail**.

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
