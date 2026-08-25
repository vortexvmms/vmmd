# Company themes and Home tasks resilience

The administrator can select one of three complete company themes in Settings:

- Vortex Executive
- Industrial Navy
- Construction Amber

Each theme controls primary, secondary, accent, page, card and text colours across the website, including Home. Safety success, warning and error colours stay semantic. Theme changes use a 220ms transition and respect the device's Reduce Motion setting.

The Home task panel now handles reminder-scan timeouts and API failures without remaining blank. Existing tasks still load when automatic DPR reminder reconciliation fails, and the panel provides Retry and Open to-do board actions when the request itself is unavailable.

Release: `20260825-ui5`  
Service-worker cache: `vcms-v44-themes-tasks`

