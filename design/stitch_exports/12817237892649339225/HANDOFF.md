# Stitch Handoff

## Active Source Screens

### `weekday_commute_now`
- Refined screen ID: `584d7fbfd57545489f2288ad975f09cc`
- Screenshot: [screenshot.png](584d7fbfd57545489f2288ad975f09cc/screenshot.png)
- HTML: [screen.html](584d7fbfd57545489f2288ad975f09cc/screen.html)
- Notes:
  - Keep the `250 / 760 / 350` structure.
  - Keep the hero route/destination/due hierarchy.
  - Remove leftover Stitch placeholder header chrome and keep the right rail as headlines only.

### `weekend_multi_stop`
- Refined screen ID: `0e06961ebc3b4c499e66340a8df937f5`
- Screenshot: [screenshot.png](0e06961ebc3b4c499e66340a8df937f5/screenshot.png)
- HTML: [screen.html](0e06961ebc3b4c499e66340a8df937f5/screen.html)
- Notes:
  - Keep the `4 x 340px` strip.
  - Keep four departures per stop above a full-width footer.
  - Increase route, due, destination, and time legibility.

### `ambient_info`
- Refined screen ID: `22afa13267874815a0d5ee96d37e0701`
- Screenshot: [screenshot.png](22afa13267874815a0d5ee96d37e0701/screenshot.png)
- HTML: [screen.html](22afa13267874815a0d5ee96d37e0701/screen.html)
- Notes:
  - Keep the `340 / 1020` split.
  - Remove the leave-by block from this mode.
  - Use one stacked headline column across the full main plane.

## Live Stitch MCP Reference
- Exact live model enum used in this environment: `GEMINI_3_1_PRO`
- Refinement method used: `edit_screens`
- Exported artifacts were downloaded from the returned hosted file handles and stored in this folder tree.

## Implemented Geometry

### `weekday_commute_now`
- Columns: `250 / 760 / 350`
- Left rail:
  - time
  - date/day
  - weather icon + temperature
  - humidity
  - AQI
  - sunrise / sunset
  - leave-by block
- Center:
  - stop title
  - hero next-bus block
  - 3 departures below
- Right rail:
  - 6 stacked real headlines
  - no ledger labels, version tags, or QR chrome

### `weekend_multi_stop`
- Main strip: `4 x 340px`
- Column header height: `72px`
- Departure row height: `92px`
- Footer height: `40px`
- Footer content:
  - current time
  - day/date
  - weather icon + temperature

### `ambient_info`
- Left rail width: `340px`
- Main plane width: `1020px`
- Left rail:
  - time
  - date/day
  - weather icon + temperature
  - humidity
  - AQI
  - sunrise / sunset
- Main plane:
  - compact summary block
  - 6 vertically stacked headlines with source label + headline title

## Type Scale
- `weekday_commute_now`
  - clock: `70px`
  - date: `18px`
  - temperature: `30px`
  - stop title: `34px`
  - hero route: `74px`
  - hero destination: `32px`
  - hero due: `76px`
  - departure rows: `20-28px`
  - right-rail headlines: `14px`
- `weekend_multi_stop`
  - stop title: `20px`
  - route: `52px`
  - due: `30px`
  - destination: `17px`
  - scheduled time: `12px`
  - footer time/temp: `18px`
- `ambient_info`
  - clock: `88px`
  - date: `18px`
  - temperature: `44px`
  - metric values: `20px`
  - summary copy: `16px`
  - headline source: `9px`
  - headline title: `18px`

## Contrast Rules
- White text appears only on solid black fills.
- Light surfaces use black or dark gray text only.
- Divider lines use darker gray or black only.
- There are no gray-on-gray or white-on-light-gray combinations.

## Truncation Rules
- Weekday right-rail headlines clamp deterministically.
- Weekday center destinations clamp to one line.
- Weekend destinations clamp to one line.
- Ambient headlines clamp deterministically in a single vertical stack.
- Times and due values never wrap.

## Local Asset Rules
- Text fonts are vendored locally in [fonts](../../../src/ribbon/render/fonts).
- Weather and utility icons now use the vendored Material Symbols variable font, not browser-hosted CSS fonts.

## Removed Or Edited During Renderer Adaptation
- `Mobility Ledger`, `System Ledger`, version tags, and QR/footer ornaments
- stray Stitch placeholder identifiers in the weekday header
- ambient leave-by / commute alert block
- ambient headline grid
- filler chrome that was not part of the required product information
