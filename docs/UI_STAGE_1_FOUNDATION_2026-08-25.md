# VCMS UI Stage 1 — Shared Foundation

## Appearance controls

### Every user
- Light mode
- High-contrast mode for outdoor use
- Dark mode
- The personal mode is stored on the current device.

### Administrator
- Vortex Red
- Construction Blue
- Safety Orange
- Professional Navy
- Emerald Green
- Custom six-digit brand colour

The company colour is stored in the existing `settings` table under `ui_company_theme`. No database migration is required. All signed-in users receive the company colour; the browser keeps it for six hours to avoid slowing normal navigation.

## Semantic colours

These colours never follow the company theme:
- Green: confirmed/success
- Amber: pending/warning
- Red: error/destructive
- Grey: neutral/disabled

## Shared components

- Mobile/desktop page header and toolbar
- Primary, secondary, tertiary, success and destructive buttons
- 46px form controls
- Status pills
- Loading, empty and error states
- Accessible toast messages

## Print protection

Theme rules are screen-only. Print and PDF reset to the approved Vortex report palette so changing the interface colour does not alter official reports.

## Next stage

Stage 2 applies these shared components to the five supervisor pages: Home, Request Manpower, Attendance, Allocation and WhatsApp.
