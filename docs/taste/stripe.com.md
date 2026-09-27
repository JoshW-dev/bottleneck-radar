# Design Map

Source: https://stripe.com (redirects to https://stripe.com/en-ca), 1440×900 viewport, single page, captured 2026-09-26.

## Spacing Scale
- Base unit 4px with 2px half steps: 2, 4, 6, 8, 10, 12, 16px
- Layout steps: 24, 32, 64px; 160px between sections
- Counts: 8px ×149, 6px ×77, 16px ×56, 12px ×49, 4px ×46, 2px ×31, 32px ×25, 64px ×22
- Hero air: 128px from nav rule to eyebrow, 122px from CTA row to logo strip
- Card padding 24px; icon button inset 16px from the card corner; primary button padding ~12px 24px
- Spacing through `gap` (nav 28px, lists 24px, icon to label 4px); margin 0 on h1, h2, h3, p, ul

## Font Hierarchy
- Families: `sohne-var` (Söhne variable) in every role, 2,836 nodes; `SourceCodePro` for code lines inside product mockups, 57 nodes

| Role | Size / line-height | Weight | Tracking | Color |
|---|---|---|---|---|
| Hero h1, two tones in one block | 48px / 55.2px | 300 | -0.96px | #061B31 first sentence, #41607F rest |
| Stat figure | 48px | 300 | not measured | #FFFFFF active, #6980B7 idle |
| Section h2, two tones in one block | 32px / 35.2px | 300 | -0.64px | #061B31, then #64748D |
| Section and tile h3 | 26px / 29.12px | 300 | -0.26px | #061B31 |
| Lead paragraph | 18px / 25.2px | ~300 | normal | #50617A |
| Body, buttons, stat labels, h4 | 16px / 22.4px | 400 | normal | #50617A; #FFFFFF on accent |
| Footer links | 16px / 24px | ~300 | normal | #50617A; column heads #061B31 at ~400 |
| Nav triggers, eyebrow, live GDP figure | 14px | 400 | normal | #061B31; figure #64748D |
| Mockup UI text | 8-12px | mixed | normal | per mockup |

- Steps: 48/32 = 1.5, 32/26 = 1.23, 26/22 = 1.18, 22/18 = 1.22, 18/16 = 1.125, 16/14 = 1.14 (22px on 20 nodes, role not captured)
- Weights by node count: 300 ×445, 400 ×253, 500 ×35, 700 ×1
- Line length comes from column span (hero 920px, about 40 characters per line); no `ch` max-width

## Color Palette
Grounds and lines:
- #FFFFFF: main ground, 56.6% of background area
- #F8FAFD: alternate ground for the bento section and footer, 9.5%
- #E5EDF5: 1px rails, hairlines, card borders

Text:
- #061B31: headings, lead sentence of two-tone blocks, nav
- #50617A: body, lead paragraphs, footer links
- #64748D: continuation sentence of two-tone h2, live GDP figure
- #41607F (sampled): hero h1 continuation
- ~#784CE3 and ~#8642B2: h1 words where they overlap the wave

Accent:
- #533AFD: primary fill, links, icon strokes, active icon button (0.2% of background area, hue 248°)
- #F5F5FD: idle icon button fill

Dark stats band, full-bleed:
- #1B1F5E to #28227A to #4239AE, top to bottom (hue 236-245°)
- #8A84F2 to #E0E0FB radial glow at the ray origin, bottom center
- #FFFFFF active stat, #6980B7 (sampled) idle stats, ~#9494CA hairline glow over the active cell
- Rails stay visible at #342B94

Art ramp, canvas and illustration only:
- Hero wave: #C0DAFD, #C2C2FF, #FF9016, #FF5F85, #FC6EC4
- Globe: dots ~#ACA2D8 (violet) to ~#EBAFC9 (pink) to ~#EBA4B3 (coral); arc ~#E0A9E4 to ~#CEC1EE; pulse marker ~#F09DE6; second marker ~#C6DAF5 (all JPEG-softened)
- Customer logos keep their own brand colors
- Mockup-only, under 5% of area: rgba(21,190,83,0.2) status badge, #650057 sidebar, #FFFAFD panel tint

## Image Ratios
- 1.43:1: hero wave fallback image, 1392×975 (the live wave is a canvas)
- 2.74:1, 3.08:1, 2.32:1: full-width section art rendered at 1232px
- 1.21:1: feature art at 860px; 1.03:1 and 0.90:1 at 344px
- 0.59:1: bento tiles (400×678) holding the globe, card and chat art; also a 280px thumbnail
- 1:1: 92px thumbnails

## Component Tokens
Radius:
- 4px: buttons and nav CTAs (×103)
- 6px: bento tiles, cookie banner, 38px icon buttons (×79)
- 5px and 8px: mockup frames; 16px: card illustration; 100%: dots

Shadows:
- Floating product object: `0 30px 45px -30px rgba(50,50,93,0.25), 0 18px 36px -18px rgba(0,0,0,0.1)`
- Same recipe at 0.47× inside scaled mockups: `0 14.088px 21.132px -14.088px rgba(3,3,39,0.25), 0 8.453px 16.906px -8.453px rgba(0,0,0,0.1)`
- Soft: `0 16px 32px rgba(50,50,93,0.12)`, `0 15px 35px rgba(23,23,23,0.08)`
- Cookie banner: `0 4px 24px rgba(0,0,0,0.06)`
- Structural tiles: no shadow, 1px #E5EDF5 border

Grid:
- 12 columns × 88px, 16px gutter, 1232px content from x=104 to x=1336
- 1264px frame, 1px rails at x=88 and x=1352, visible for the full page height and through the dark band
- Spans: hero copy columns 2-10 (920px); SaaS paragraph from column 8; bento 3 × 4 columns (400px); footer 4 × 3 columns (312px pitch); stats 4 cells at 320px pitch
- Full-bleed: nav rule at y=76 and the dark band

Buttons and controls:
- Primary: #533AFD fill, #FFFFFF 16px/400, 4px radius, ~48px tall, trailing › chevron
- Secondary: #FFFFFF fill, 1px lavender border, #533AFD text, ~48px tall
- Nav: 14px/400 dropdown triggers with ▾; CTAs ~38px tall
- Icon button: 38px square, 6px radius, #F5F5FD fill, #533AFD icon; active state fills #533AFD
- Text link: #533AFD with trailing ›
- Band toggle: 32px outlined square with a crescent-moon icon, top right of the ray canvas (function not verified)

Dividers:
- 1px hairlines: nav rule at y=76; logo strip top and bottom at y=688 and y=760 (a 72px band, 7 logos)
- Footer: 1px dashed dividers between 4 columns and above the locale row

Motion:
- UI: color, background-color, border-color, opacity, fill at 0.24s cubic-bezier(0.45, 0.05, 0.55, 0.95); transform at 0.25s cubic-bezier(0.6, 0, 0.2, 0.5); opacity and transform on cubic-bezier(0.4, 0, 0.2, 1)
- No width or height transitions
- Canvas: hero wave; dot globe (1 arc and 2 pulse markers in the captured frame); ray burst (~300 rays tipped with dots, 4.5% bright pixels); GDP figure to 8 decimals (1.72240141%)
- Captured states: 1 of 4 stats lit, hairline glow spanning about 150px either side of it; one bento tile at 408px (+2%) with its icon button filled
- `prefers-reduced-motion` and `:focus-visible` not found in readable CSS

---

# Taste DNA

### Color lives in the art layer (restraint)
- **Trigger**: When the designers had a saturated brand ramp (sky blue, lavender, orange, coral, magenta) and a 14,617px page to carry it
- **Decision**: They chose to keep that ramp inside canvas art (hero wave, globe dots, tile illustrations) and run all chrome in blue-tinted neutrals with one accent, #533AFD, over tinting section grounds, icons, headings and figures in brand colors
- **Reason**: Because readers find the next action by its color. With #533AFD reserved for buttons and links, a reader spots the action at once, and the wave can run at full saturation without pulling focus from the controls
- **Evidence**: saturated pixels cover 28.9% of the first screen (nearly all of it the wave) and 0.1% of the footer; #533AFD appears as 12 fills (0.2% of background area) and 43 text nodes, on buttons, links and icon controls in the captures; neutrals #061B31, #50617A, #64748D, #E5EDF5, #F8FAFD sit at hue 210-217°; the one full-bleed color band is a darkened accent (hue 236-245° against 248°); type picks up the ramp only where it overlaps the wave (h1 words ~#784CE3, nav "Sign in" ~#BB7D69)

### Stat figures at headline size, weight 300, lit one at a time
- **Trigger**: When the designers had four proof numbers (135+, US$1.9tn, 99.999%, 200m+) to fit in one row
- **Decision**: They chose to set the figures at the h1's 48px in weight 300 and light one at a time (active #FFFFFF, the other three #6980B7, a glow on the hairlines above and below the active cell) over four bold, equally bright KPI tiles
- **Reason**: Because four equally bright numbers read as one block that readers skim past. Lighting one figure gives the eye an order to read them in, and at weight 300 a figure can match the h1's size without looking heavier than it
- **Evidence**: "135+" cap height 35px equals the hero "F" at 35px (48px type); weight 300 on 445 nodes, 700 on 1; stat 1 #FFFFFF against stats 2-4 at #6980B7; hairline luminance 150 at x=250 against 51 elsewhere; 16px centered two-line labels at 22px pitch, cells at 320px pitch; the live figure (Global GDP running on Stripe: 1.72240141%) sits at 14px above the h1 with 8 decimals; the one-at-a-time sequence is inferred from a single frame

### Globe as sparse dots, cropped, with one arc (restraint)
- **Trigger**: When the designers needed a globe to stand for cross-border money movement in the stablecoin tile
- **Decision**: They chose a sparse particle sphere in the page's violet, pink and coral, running off the edge of its 400×678px tile and carrying one thin arc with two pulse markers, over a textured or outlined earth shown whole and centered with many arcs and city labels
- **Reason**: Because the globe only has to tell a reader "this works across borders", and a dotted sphere says that without asking anyone to read a map. One arc gives the eye a single path to follow, and a sphere cut off by the tile edge reads as larger than the frame
- **Evidence**: dots cover 1.8% of the globe region, and land shows only as dot density, with no borders, graticule or labels; dot hue runs violet ~#ACA2D8 (lower left) through pink ~#EBAFC9 to coral ~#EBA4B3 (top right); one ~1.5px arc from magenta ~#E0A9E4 to lavender ~#CEC1EE in the captured frame; pulse marker ~#F09DE6 with a halo, second marker ~#C6DAF5; the sphere runs off the tile's right edge; the globe is one of three equal 4-column tiles under a 26px/300 title

### Drafted frame, shadows only for product
- **Trigger**: When the designers had to hold a long page of mixed bands together: hero, logo strip, bento tiles, dark stats band, footer
- **Decision**: They chose to draw the layout itself (1px rails at x=88 and x=1352 down the whole page, hairlines between bands, dashed footer dividers) and give structural cards only a 1px border, saving two-layer navy-tinted shadows for floating product objects, over shadow-lifted cards in an invisible container
- **Reason**: Because on a 14,617px scroll the lines tell readers which band they're in and where it ends. When only product UI casts a shadow, readers can pick the product out from the page around it
- **Evidence**: rails at x=88 and x=1352 bound a 1264px frame (1232px content plus 2 × 16px) and stay visible through the dark band (#342B94 on #28227A); hero copy starts one column in and spans columns 2-10 (x=208 to 1128); bento tiles have a 1px border, 6px radius and no visible shadow; the float shadow and its 0.47× copy appear on 9 elements, and the visible ones are floating mockup panels and the card illustration; footer columns split by 1px dashed dividers
