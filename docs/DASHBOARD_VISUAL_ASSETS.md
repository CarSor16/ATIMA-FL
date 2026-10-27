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
