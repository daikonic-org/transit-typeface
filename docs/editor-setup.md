# Editor setup

Install `fonts/code/VF/DaikonicTransitCode600-VF.ttf`. The installed family name is **Daikonic Transit Code 600**; the final number is the cell width, not a font weight. Book is weight 350.

## WezTerm

```lua
config.font = wezterm.font('Daikonic Transit Code 600', { weight = 'DemiLight' })
config.harfbuzz_features = { 'calt=1', 'clig=1', 'liga=1' }
```

WezTerm calls the350 weight DemiLight; the font’s named instance is Book.

## VS Code

```json
{
  "editor.fontFamily": "'Daikonic Transit Code 600', monospace",
  "editor.fontWeight": "350",
  "editor.fontVariations": true,
  "editor.fontLigatures": true,
  "terminal.integrated.fontFamily": "'Daikonic Transit Code 600', monospace",
  "terminal.integrated.fontWeight": 350,
  "terminal.integrated.fontLigatures.enabled": true
}
```

## Zed

```json
{
  "buffer_font_family": "Daikonic Transit Code 600",
  "buffer_font_weight": 350,
  "buffer_font_features": { "calt": true, "clig": true, "liga": true },
  "terminal": {
    "font_family": "Daikonic Transit Code 600",
    "font_weight": 350,
    "font_features": { "calt": true, "clig": true, "liga": true }
  }
}
```

Merge these font settings into existing configuration, rather than replacing other preferences. Font size is intentionally left to the application/user. Common Unicode arrows are actual Code glyphs; other symbols may still require system fallback fonts.
