# Brand images

Home Assistant 2026.3+ serves brand images for custom integrations from this
folder, and local images take priority over the brands CDN — so no submission
to home-assistant/brands is needed (that repository no longer accepts PRs for
custom integrations).

| File | Size |
|---|---|
| `icon.png` | 256×256 |
| `icon@2x.png` | 512×512 |

Regenerate after editing `logo.svg` in the repository root:

```bash
rsvg-convert -w 256 -h 256 logo.svg -o custom_components/vnish/brand/icon.png
rsvg-convert -w 512 -h 512 logo.svg -o "custom_components/vnish/brand/icon@2x.png"
optipng -o5 custom_components/vnish/brand/*.png
```

Optional extras HA also understands: `logo.png`, `dark_icon.png`,
`dark_logo.png` (plus their `@2x` variants). When no logo is supplied the icon
is used in its place.
