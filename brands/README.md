# Brand assets

Home Assistant does not read icons from a custom integration's own repository —
it loads them from `brands.home-assistant.io`, which is served from
[home-assistant/brands](https://github.com/home-assistant/brands). Until the
domain exists there, the integration shows the "icon not available" placeholder.

`custom_integrations/vnish/` below mirrors the layout that repository expects,
so submitting it is a matter of copying the folder into a fork and opening a PR:

| File | Size | Source |
|---|---|---|
| `icon.png` | 256×256 | `logo.svg`, rendered with `rsvg-convert`, optimised with `optipng` |
| `icon@2x.png` | 512×512 | same |

Regenerate after editing `logo.svg`:

```bash
rsvg-convert -w 256 -h 256 logo.svg -o brands/custom_integrations/vnish/icon.png
rsvg-convert -w 512 -h 512 logo.svg -o brands/custom_integrations/vnish/icon@2x.png
optipng -o5 brands/custom_integrations/vnish/*.png
```

`logo.png` is optional: brands falls back to the icon when no logo is supplied.
