# Plan 09-15 Summary: Gallery Page Overhaul

## What Was Built
- **`src/vizenlink_nvr/web/src/features/gallery/api.ts`**:
  - `useGallery`: Infinite query for `GET /api/v1/gallery` with camera, date bounds, and item type params, with "Load more" pagination.
  - `useDeleteGalleryItem`: Mutation sending `DELETE /api/v1/gallery/{id}` and invalidating gallery queries.
  - `useUsersList`: Fetches `/api/v1/users` for owner role to populate user filter dropdown.
- **`src/vizenlink_nvr/web/src/features/gallery/copy.ts`**:
  - User-facing strings matching UI-SPEC: tab labels, filter labels, empty state, load errors, preview close button label, and confirmation dialog copy.
- **`src/vizenlink_nvr/web/src/features/gallery/GalleryCard.tsx`**:
  - 16:9 thumbnail preview (`aspect-video`), body strong truncated title, camera + time in site zone.
  - Video clips display duration badge chip (e.g. `45s`, `01:23`) and play icon overlay.
- **`src/vizenlink_nvr/web/src/features/gallery/PreviewDialog.tsx`**:
  - 960 px dialog (`max-w-[960px] sm:max-w-4xl`) with icon-only close button (`aria-label="Close preview"`).
  - Displays full `<img>` or `<video controls autoPlay>` media preview.
  - Shows metadata: Camera name, capture time in site zone, file size, and duration for clips.
  - Action buttons: "Download snapshot" / "Download clip" (`<a download>`), "Open in Playback" (navigating to `/playback?camera=...&t=...`).
  - Role-gated deletion:
    - Viewers see no delete control.
    - Operators and owners see "Delete snapshot" / "Delete clip" (destructive outline).
    - Deletion triggers an `AlertDialog` confirmation with UI-SPEC copy ("Delete this {snapshot or clip}?", "This permanently removes the file from the NVR and can't be undone.") and actions ("Delete {type}" / "Keep {type}").
    - On delete failure, the preview remains open with an `InlineError` and "Retry delete {type}" action.
- **`src/vizenlink_nvr/web/src/features/gallery/GalleryFilters.tsx`**:
  - Wrapping filter bar with camera selector, date range popover + calendar, "Clear filters" button, and an Advanced view user filter dropdown ("Anyone", "Me", and usernames for owners).
- **`src/vizenlink_nvr/web/src/features/gallery/GalleryPage.tsx`**:
  - Snapshots and Clips tabs synced with `?tab=clips` search param.
  - Responsive 1/2/3/4 column grid (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4`).
  - Empty state with `Images` icon: "Nothing saved yet. Save a snapshot from Live or Playback, or export a clip, and it will appear here."
  - Load error state with `InlineError` and "Reload gallery".
  - Skeletons on loading.
- **`src/vizenlink_nvr/web/src/features/gallery/routes.tsx`**:
  - Updated to render `GalleryPage` directly on `/gallery`.
- **`src/vizenlink_nvr/web/src/legacy/GalleryView.tsx`**:
  - Completely deleted via `git rm`.

## Planner Decision (Recorded for Owner Review)
The `/api/v1/gallery` endpoint does not support a `user_id` query filter. Per Plan 09-15 context, the Advanced view user filter operates client-side on loaded gallery items by comparing `item.user_id` against the current user (for "Me") or selected user ID (for owners). "Load more" fetches further pages from the server.

## Verification
- `npm --prefix src/vizenlink_nvr/web test -- src/features/gallery`: PASS (8/8 tests)
- `npm --prefix src/vizenlink_nvr/web run gates`: PASS (122 non-legacy files scanned, 0 violations)
- `npm --prefix src/vizenlink_nvr/web run build`: PASS (TypeScript tsc & Vite production bundle green)
- `npm --prefix src/vizenlink_nvr/web test`: PASS (236/236 tests across 22 test suites)
- `test ! -e src/vizenlink_nvr/web/src/legacy/GalleryView.tsx`: PASS (file deleted)

