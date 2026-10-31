# Dashboard artwork: provenance and behavior

## Geographic hero artwork

- File: `src/atima_fl/ui/static/federated-world.svg`
- Source of land contours: **Natural Earth**, `ne_110m_land.geojson`, from
  [natural-earth-vector](https://github.com/nvkelso/natural-earth-vector/tree/master/geojson).
- License of source map data: **public domain** (free to reproduce, modify, and
  redistribute, including commercially). Source:
  https://www.naturalearthdata.com/about/terms-of-use/
- Artwork: ATIMA-specific local SVG rendering of these contours, dots, geographic
  landmarks, illustrative links, and soft glows. **The links are illustrative,
  not actual participating client positions or actual network traffic.**
- Native viewport: **960 × 540 (16:9)**, matched to the Studio hero panel.
  Rendered by CSS with `background-size:cover` so it fills the panel
  without letterboxing on varying display widths.
- A slow dash animation on the *illustrative* network links automatically
  disables under `prefers-reduced-motion:reduce`. No external network
  dependencies, timers or video assets.

## Icons

- File: `src/atima_fl/ui/static/dashboard-icons.svg`
- 18 original SVG symbols, created specifically for this ATIMA Studio.
  They replace approximate font glyphs in sidebar, stat cards,
  hero features, recent experiments and quick actions.
- The symbols contain no externally imported icon pack or licensed third-party
  logo. No dependence on remotely loaded fonts or CDN icon fonts.
- The user-selected shield brand mark is retained as a separate PNG.
- All controls remain native HTML buttons with accessible names and keyboard
  support, and icons are marked `aria-hidden` when decorative.

## Scientific accuracy

The dashboard counts registered **dataset plugin types**, executable attack
plugins (excluding `none`), and registered aggregation methods, and displays
the current default experiment client count. These are **not** run counts or
proof of dataset availability. The experiment table uses local verified
workspace result metadata and does **not** fabricate rows from the reference
image. Studio health indicates catalog access, **not** cluster/GPU readiness.

## Testing

`tests/test_ui.py` verifies that both SVG assets are served through the explicit
loopback static-file allowlist; that icons are referenced consistently; and that
the map geometry, dimensions and reduced-motion support are valid.
`tests/js/dashboard.test.cjs` checks that real APIs populate the metrics and
recent runs correctly, including the empty-workspace state.

A final *pixel-comparison screenshot* is separate from these functional tests
and must be assessed from the locally running Studio browser UI before merge.


## October 2026 refresh

The vector sprite now uses corrected cog/gear geometry for **Settings** and a
history-clock arrow for **Recent Experiments**, avoiding platform-dependent
Unicode glyphs. The original shapes in `dashboard-icons.svg` are supplied
for ATIMA use under the Creative Commons Zero 1.0 Universal dedication
(https://creativecommons.org/publicdomain/zero/1.0/) to the extent that
copyright subsists in them; no commercial icon-library artwork was copied.

The new `atima-shield-transparent.png` is a generated, text-free ATIMA
symbol supplied with an indexed PNG transparency channel and referenced
as the sidebar emblem and favicon. The previous mark is retained for
provenance but not used as active brand art. The new image should not be
represented as a registered or exclusively owned trademark without a
separate clearance.

The implementation draws on the **design principles** of the
[shadcn/ui dashboard and sidebar blocks](https://ui.shadcn.com/blocks):
sharper elevation hierarchy, consistent panels, subtle dividers and
coherent interactions. The frontend remains the existing no-React
HTML/CSS/JavaScript Studio architecture.

The chosen technical display font is the GGBotNet **Alpha Prota** face
(CC0 1.0, https://github.com/ggbotnet/fonts-cc0). For offline/privacy
reasons it is used via `local()` when installed on the workstation;
without that local font, the same system fallback is used in light and
dark mode. The binary font is **not included** with ATIMA.
