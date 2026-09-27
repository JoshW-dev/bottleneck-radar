# Design Map

## Spacing Scale
- Base unit 4px; 8px is the most used value (137 uses), then 16px (33) and 24px (29)
- Scale: 4, 8, 12, 16, 24, 32, 64, 128px
- Page gutters: 16px under 768px, 32px from 768px, 48px from 992px, 64px from 1280px
- Header: 32px top and bottom padding; eyebrow to H1 16px; H1 to dek 20px
- Indicator layout: 32px between sidebar and chart column, 24px vertical padding; chart card inset 32px
- Indicator tabs: 12px × 10px padding, 4px apart; subtabs 12px × 8px, 2px apart
- Chart: plot margins 24px top, 40px bottom, 8px left; 52px y-tick column with labels 12px from the plot; x-ticks 28px below the plot; end labels 10px past the last point
- Chart footer: 8px 32px 12px padding, 16px gap
- Page sections: 64px above methodology; 128px spacer before related articles; related grid gaps 24px column, 48px row

## Font Hierarchy
- Lausanne: display, body and UI; faces loaded at 300, 350, 400, 700 (a 600 request renders with the 700 face, 500 with the 400 face)
- IBM Plex Mono: UI labels, y-ticks, toggle, tooltips; faces 400 and 500
- DM Mono: SVG chart text via `--d-mono`; the page ships no @font-face for it, so it falls back to the system monospace
- 48px / 50px, 300, -0.01px tracking: page title (H1)
- 31.68px / 39.6px, 600, -0.025em: chart title, fluid `clamp(1.45rem, 2.2vw, 2rem)`
- 28px / 32px, 300: section heading ("You might also like")
- 24px / 28px, 300: methodology heading
- 18px / 30px: methodology body; 18px / 24px: related-card titles
- 16px / 22px, 300: header dek (max 720px) and chart subtitle (max 760px)
- 14px / 20px, 400: nav, indicator tabs, buttons
- 13px / 1.65: chart source line
- 12.48px: indicator subtabs
- 11.52px IBM Plex Mono: eyebrow (uppercase, 0.1em, #4F72E8), group labels (uppercase, 0.08em, 500, #666), y-ticks (#666), toggle, tooltip text
- 11px DM Mono: series end labels (600, series color), x-ticks (#999)
- Headings and body use a leading-trim utility that removes half-leading from Lausanne's metrics (ascent 1866, descent -410, 2048 units per em)

## Color Palette
- #FFFFFF: page ground, 86.1% of area
- #1A1919: footer band (11.7% of area), "Get started" button, active toggle pill
- #0C0A08: primary ink (H1, active tab text, Ramp wordmark)
- #1A1A1A: chart titles and chart text
- #444444: chart source line
- #666666: subtitles, inactive tabs, group labels, y-ticks
- #999999: x-ticks, empty-state text
- #0C0A0899 (ink at 60%, about #6D6C6B on white): header dek, methodology body
- #4F72E8: AI accent; the primary series at 0.9 opacity, its end label, the eyebrow
- #8B8479: Census benchmark line (dashed) and its end label
- #E4F222: "solar" demo button and text selection highlight, 0.2% of area
- #E0E0E0: rules, tab and toggle borders, subtab rail
- #EEEEEE: gridlines
- #F5F5F5: active tab fill
- #FFFFFFE0: tooltip and toggle surface, with backdrop blur
- #168A4D / #D23B3B: positive and negative change
- Sepia "Serious" theme: #F5F0E8 ground, #7A756D muted text, #B0A99E faint text, #E0DBD3 border, #7693D2 accent
- Other chart views: business size #2B2B2B / #4EA1B7 / #E8893D; sectors #4A6FA5, #6B8F71, #8B7355, #7693D2, #5A9E8F, #A67C6D, #7A8B6F

## Image Ratios
- Related-article media: 2:1, 421px wide, 12px radius (sources 1.90:1 to 2.00:1)
- Author avatar: 1:1, 40px, circular
- Footer badge: 1:1, 32px
- No hero image; the 420px-tall chart is the first visual under the header

## Component Tokens
- Radius: 0px chart card; 4px toggle pills; 6px buttons, tabs, subtabs, toggle shell, tooltip; 12px related media; 9999px avatar
- Shadow: `0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px -1px rgba(0,0,0,0.1)` on the toggle and tooltip only; copy toast `0 1px 3px #00000022`; tabs, chart cards and related cards have none
- Grid: container max 1536px; 240px sidebar + 32px gap + fluid chart column (about 1040px at 1440); sidebar sticky 86px from the top; methodology column 644px centered; related cards 3 × 421px
- Header: closed by a 1px #E0E0E0 full-bleed rule
- Indicator tab: 240 × 44px minimum, 1px border (#E0E0E0 when active, transparent otherwise), #F5F5F5 active fill, 14px text; subtab rail 1px #E0E0E0 with 16px indent and 12px padding, 36px rows at 12.48px
- Chart: 420px tall; 1px #EEEEEE horizontal gridlines only; no axis lines; straight segments between monthly points
- Chart lines: primary 2.5px at 0.9 opacity with round caps; other series 2px at 0.9; benchmark 1.75px dashed 6 4 at 0.72; muted aggregate 1.5px dashed 6 4 #B0A99E at 0.6
- Chart focus: hovering a series fades the others to 0.24; hover dot r=4 with a 2px ring in the ground color
- End label: series name plus latest value ("Ramp Overall 56.1%"), 11px DM Mono 600 in the series color, 10px past the last point; colliding labels get a 1px dashed (2 2) leader at 0.5 opacity
- Tooltip: 6px radius, 1px #E0E0E0 border, #FFFFFFE0 with backdrop blur, 14px × 10px padding, 11.52px IBM Plex Mono at 1.625 line height, 8px color dot per row, "label: value" rows, 14px from the point, flips left past 60% of the plot width
- Chart footer: "Source: ..." sentence at 13px #444, underlined "Get the data." (3px offset) that copies the rows, Ramp wordmark at the right, hairline below
- Number format: rates to 1 decimal ("56.1%"); spend per employee in USD with up to 2 decimals; spend shares 2 decimals at 1% and above, 3 decimals below, floored at "<0.001%"
- Theme toggle: "Casual" (white) and "Serious" (sepia) segmented control, 11.52px IBM Plex Mono, 6px shell with 4px padding, active pill #1A1A1A with white text, choice saved in localStorage
- Motion: color, background and border transitions at 150ms cubic-bezier(0.4, 0, 0.2, 1); copy toast 150ms ease-out with a 4px rise; related media scales to 1.02 over 300ms; prefers-reduced-motion respected
- State: indicator selection lives in the URL hash (`#adoption#overall`); `:focus-visible` styles present

---

# Taste DNA

### Name the line where it ends
- **Trigger**: When a monthly index chart has to say which line is which and what the latest reading is.
- **Decision**: Chose to print each series' name and latest value at its last data point, in the series color and 11px DM Mono at 600, over a legend box with values revealed on hover.
- **Reason**: People open a monthly index to get the current number, and their eye already stops at the right end of the line. Monospaced digits make "56.1%" read as a measurement, and the label survives in a static screenshot where hover doesn't exist.
- **Evidence**: "Ramp Overall 56.1%" in #4F72E8 and "Census Estimate 22.1%" in #8B8479, each 10px past the line's last point; no legend box; colliding labels get a 1px dashed (2 2) leader at 0.5 opacity; y-ticks 11.52px IBM Plex Mono #666, right-aligned in a 52px column; x-ticks 11px #999; straight segments between monthly points.

### Spend color only on the headline series
- **Trigger**: When one chart pairs Ramp's own series with a public benchmark, inside a brand whose signature color is chartreuse.
- **Decision**: Chose one blue for Ramp's line and a thinner warm-gray dashed line for the Census benchmark, with all chart structure in gray, over a categorical palette or the brand chartreuse on the data.
- **Reason**: Readers should know which line is the headline before they read a label, and a heavy solid blue line against a thin dashed gray one settles that at a glance. Chartreuse #E4F222 measures about 1.2:1 against white, so a 2.5px line in it would disappear; Ramp keeps it on one sales button.
- **Evidence**: #4F72E8 (4.3:1 on white) at 2.5px and 0.9 opacity against #8B8479 at 1.75px, dashed 6 4, 0.72 opacity; #E4F222 covers 0.2% of the page; gridlines #EEEEEE, horizontal only, no axis lines; the chart card has no border, fill, radius or shadow; hovering one series fades the rest to 0.24.

### The whole index in one list
- **Trigger**: When 6 indicators in two families, plus 5 breakdowns under Adoption, have to share one page.
- **Decision**: Chose a sticky 240px sidebar that lists every indicator under 11.52px mono group labels and unfolds subtabs only under the active tab, over top tabs or a long scroll of stacked charts.
- **Reason**: People return to a recurring index for one series and want to see what else it covers before they pick. One list answers "what does this track?" without a click, and the URL hash lets them send a colleague the exact view.
- **Evidence**: tabs 240 × 44px, 6px radius, 12px × 10px padding, 4px apart; active tab #F5F5F5 fill, 1px #E0E0E0 border, ink text; inactive tabs #666 with a transparent border; subtabs at 12.48px on a 1px #E0E0E0 rail, the active one in ink against #666; sticky at 86px (62px nav plus 24px); `#adoption#overall` in the URL; under 992px the list turns into two selects.

### Provenance rides inside the crop
- **Trigger**: When deciding where sources and methodology go for charts that readers will crop and share.
- **Decision**: Chose to end every chart with a source sentence, a "Get the data." button that copies the rows, and the Ramp logo, with methodology published as signed long-form prose, over one footnote linking to a separate methodology page.
- **Reason**: A shared chart travels as a crop, and anything outside the crop is lost. With the source line and logo inside the chart, attribution stays attached, and a named economist gives readers a person who answers for the numbers.
- **Evidence**: chart footer 13px/1.65 in #444, 8px 32px 12px padding, 3px underline offset; Ramp wordmark at the footer's right edge (x 1268 to 1343); a hairline closes each chart; "Get the data." confirms with a "Copied data to clipboard." status; methodology in a 644px column at 18px/30px in #0C0A0899, 64px below the charts, under a 40px avatar byline for Ramp's lead economist.

# Capture notes
- The Ethyca consent banner covered y 640 to 851 in every capture, hiding the x-axis and part of the sidebar. Chart values below that line come from the page's CSS and chart code.
- The nav logo and links rendered white on the white page at scrollY 0, with no visible pixels. This analysis treats that as a capture defect.
- Methodology, byline, tooltip, number formats, the sepia theme and the non-overall palettes come from ramp.com's served HTML, CSS and JS on 2026-09-26, since the screenshots don't show them.
