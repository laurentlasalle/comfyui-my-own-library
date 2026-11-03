# Changelog

Versions follow the usual pattern: the middle number goes up with new features, the last one with fixes only. The version is shown at the bottom of the library's left column and in ComfyUI's terminal at startup.

## 0.15.0 (2026-11-03)

- **Selection bar** (several creations ticked): a new **Characters to add** field next to **Tags to add**, and an **Apply changes** button in place of **Add tags**. Nothing changes until you click it: the category chosen in **Move to category** (no longer applied as soon as it is picked) replaces the current one, and the characters and tags are added. Choices are cleared when the selection is.
- **Characters** in the detail panel suggest your characters as you type (they suggested tags by mistake).
- The detail panel shows the size in megapixels next to the dimensions, for example `1600 × 896 (1.4 MP)`, with 1 MP = 1024 × 1024 pixels as in ComfyUI.
- The track of the progress bar is visible again across its whole width (it had the same colour as the bar around it).

## 0.14.1 (2026-11-02)

- The badge of combined videos is shorter: **Combo of 3** instead of **Combined from 3 parts** (the tooltip still explains it).

## 0.14.0 (2026-11-02)

- **Adding to the library** leaves out files that may still be written: a video or sound modified in the last few seconds, or a video never closed by its writer (no `moov` index, as left by a batch job that is still running or was cancelled). A **Not added** message says why. With **Remove from output after adding** ticked and **Also remove files without a workflow** off, a file without a workflow is not added either, instead of being added and kept in `output`.
- **Duplicates**: the copies that will leave the library are no longer dimmed; they show **Will be removed** where the kept one shows **Kept**. Hover a copy and click **Keep this one** to choose the copy kept (a warning appears if it takes a version out of its work). **Keep one** and **Keep one of each** follow these choices.
- Fixed: merging duplicates now also merges their characters, like their tags.
- **Combined from N parts** (Import view, Easy-Media projects) is shown only when it can be confirmed from the files in `output`: every segment of the project has a take made before the final video, and the most recent of those takes add up to its length.
- Thumbnail badges all use 12 px text, like Browse Templates; **Part 2 of 4** and **Combined from N parts** are no longer bold and sit in the bottom-right corner, above **In library** or **New** in the Import view.
- **Load workflow** uses ComfyUI's own workflow icon.
- The `output/` folder name in the Import banner is shown as code, like in ComfyUI's documentation.

## 0.13.0 (2026-11-02)

- **Remove from output after adding** is more careful. A file stays in `output`, with a message saying why, when it was modified in the last few seconds, when it is a video that was never closed by its writer (no `moov` index: a batch job that is still running or was cancelled leaves one), or when the library copy is incomplete. The file is still added to the library.
- **Also remove files without a workflow** (File Management, off by default): a file whose workflow could not be read (segments, images saved without it) stays in `output` after being added, unless you turn this on.
- **Save workflow** button next to **Load workflow** in the detail panel: saves the creation's workflow as a `.json` file (`.prompt.json` when only the API-format prompt exists).
- The download button no longer makes ComfyUI warn that the page is about to close.
- **Library directory** setting: wider field, and a folder icon before it that opens a folder picker (drives, subfolders, **Up**, **New folder**, **Select this folder**), available only from the computer running ComfyUI.
- The folder at the bottom of the left column shows the size of the library in brackets, and a click on it opens the folder picker (it used to open ComfyUI's Settings, hidden behind the library window).
- The left column follows the spacing of ComfyUI's Browse Templates (same units, in rem): taller items, 0.25 rem between them, 0.5 rem inside CHARACTERS and CATEGORIES.

## 0.12.1 (2026-11-02)

- Fixed: the CHARACTERS and CATEGORIES titles in the left column touched the first item below them; they now have a little space underneath.
- The items of the left column are spaced apart, like in ComfyUI's Browse Templates.

## 0.12.0 (2026-11-02)

- **Characters**: a new classification parallel to categories. Each item can have zero or more characters (edited in the detail panel, same tag-input as categories). Characters appear in their own **CHARACTERS** section in the left column, each with a navigation entry that filters the grid. Character names are shown on card thumbnails before the category chip.
- **CHARACTERS / CATEGORIES section order**: collapsible sections in the left column; collapse state is persisted. A new setting **Sidebar section order** controls which section comes first (Characters first by default).
- The left column's scrollbar is hidden; scrolling via mouse wheel still works. The version/library-dir footer stays fixed at the bottom with a gradient fade above it.
- **Import** (was "Output"): the nav item and view title are renamed. A permanent banner at the top of the Import view explains what the view is for.
- Player volume and mute state persist across media items within the session: opening a new file picks up where the previous one left off.
- Sidebar nav items use rounded styling (`border-radius: 8px`, `margin: 0 8px`) matching ComfyUI's Browse Templates panel.

## 0.11.0 (2026-10-30)

- **Remove parts** and **Delete parts**: click a listed file to preview it over the confirmation (**←** / **→** to go through the list, **Esc** to come back).
- Segments have their own color (teal): "P2" on their thumbnail in the version strip, "Part 2 of 4 · segment of …" in the detail header, and on the cards.
- The detail panel shows the name of the copy in the library folder under the title.

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
