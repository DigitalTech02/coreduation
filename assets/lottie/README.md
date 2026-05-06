# Lottie animations

Drop ``.json`` files (downloaded from <https://lottiefiles.com> or exported
from After Effects via Bodymovin) into this folder to use them in shorts.

## Built-in icon ids (resolved by `rendering_engine/lottie_renderer.py`)

The following ids are auto-injected by the shorts pipeline:

| Icon id | Auto-injected on | Fallback SVG (when no JSON present) |
|---|---|---|
| `success_check` | Payoff scene | `assets/svg_icons/success_check.svg` |
| `warning_alert` | Tension scene | `assets/svg_icons/warning_alert.svg` |
| `swipe_arrow` | CTA scene | `assets/svg_icons/swipe_arrow.svg` |
| `sparkle` | (manual via `show_lottie` action) | `assets/svg_icons/sparkle.svg` |
| `loading_dots` | (manual via `show_lottie` action) | `assets/svg_icons/loading_dots.svg` |

## How resolution works

Per icon id, the loader checks **in order**:

1. `assets/lottie/<id>.json` → if present AND `lottie` package is installed,
   converts to SVG via Cairo backend, caches the result in
   `assets/lottie/.svg_cache/<id>.svg`, returns the cached path.
2. `assets/lottie/<id>.svg` → if present, returns directly.
3. `assets/svg_icons/<id>.svg` → the bundled fallback.

## Replacing a fallback with a designer Lottie

1. Find a Lottie animation at <https://lottiefiles.com> (filter for free / CC0 / MIT).
2. Click "Lottie JSON" → save as e.g. `success_check.json` in this folder.
3. Re-run any shorts render — the new animation is converted to SVG and
   used in place of the bundled fallback.

## Optional install

```bash
pip install lottie
```

Without `lottie` installed, the pipeline gracefully falls back to the
bundled SVG icons.  Install it only if you want to use real `.json` files.
