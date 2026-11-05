# Phase 9: UI Redesign - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-05
**Phase:** 9-UI Redesign
**Areas discussed:** Brand and logo, Theme and shell, Scope deferrals, Rollout order

---

## Brand and logo

| Option | Description | Selected |
|--------|-------------|----------|
| Old VMS blue + wordmark | #0056D2 accent and text wordmark (UI-SPEC default) | |
| I'll supply logo files | Old blue now, reserve logo slots | |
| Different brand color | User gives hex | |
| Free text | "u know the app i am developing right in that there vl log right" (use the mobile app's logo) | ✓ |

**User's choice:** Use the VizenLink mobile app's branding. Claude then found `/Users/gokul/mobilecctvapp/assets/branding` (black V + red L logo) and `lib/theme/app_colors.dart` (indigo `#5B6EF5` / cyan UI palette).
**Notes:** Follow-up on accent: Mobile app indigo (selected) vs Logo red vs Indigo-to-cyan gradient. Follow-up on logo files: Yes, copy light + dark (selected) vs applogo.svg vs wordmark. Old VMS logos: No (selected).

---

## Theme and shell

| Option | Description | Selected |
|--------|-------------|----------|
| Follow system | Light/dark by OS with override | ✓ |
| Dark by default | | |
| Light by default | | |

**User's choice:** Follow system.
**Notes:** Shell: Sidebar, collapsible (selected) vs Auto-collapse on Live vs Top bar only.

---

## Scope deferrals

| Option | Description | Selected |
|--------|-------------|----------|
| Add-camera + users/profile, no Search | UI-only additions using existing APIs | ✓ |
| All four, including Search | Search needs new backend | |
| None, keep deferred | | |

**User's choice:** Add-camera wizard, user management, change-password and Profile in Phase 9; Search deferred.
**Notes:** The first scope answer selected every option including "None, keep deferred" (contradictory), so it was clarified with a follow-up question. Claude found no discovery endpoint in the API, so the wizard is manual entry unless the owner decides otherwise.

---

## Rollout order

| Option | Description | Selected |
|--------|-------------|----------|
| Page by page, one app | Tooling/shell first, then one plan per page group, app builds after each | ✓ |
| Big-bang rewrite | | |
| Shell first, old pages inside | | |

**User's choice:** Page by page, one app.

---

## Claude's Discretion

- Exact AA-compliant shades, logo lockup cropping, final plan split, Add-camera and users form layout.

## Deferred Ideas

- Global Search page, web LAN camera discovery (new backend), dedicated Alerts page, i18n, PWA, drag-to-arrange tiles, gradient styling.
