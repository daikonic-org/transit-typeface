# Editor setup

Install the Code VF or TTC from the coordinated release. The installed family name is **Daikonic Transit Code**. Book is weight 350.

## WezTerm

```lua
config.font = wezterm.font('Daikonic Transit Code', { weight = 'DemiLight' })
config.harfbuzz_features = { 'calt=1', 'clig=1', 'liga=1' }
```

WezTerm calls the350 weight DemiLight; the font’s named instance is Book.

## VS Code

```json
{
  "editor.fontFamily": "'Daikonic Transit Code', monospace",
  "editor.fontWeight": "350",
  "editor.fontVariations": true,
  "editor.fontLigatures": true,
  "terminal.integrated.fontFamily": "'Daikonic Transit Code', monospace",
  "terminal.integrated.fontWeight": 350,
  "terminal.integrated.fontLigatures.enabled": true
}
```

## Zed

```json
{
  "buffer_font_family": "Daikonic Transit Code",
  "buffer_font_weight": 350,
  "buffer_font_features": { "calt": true, "clig": true, "liga": true },
  "terminal": {
    "font_family": "Daikonic Transit Code",
    "font_weight": 350,
    "font_features": { "calt": true, "clig": true, "liga": true }
  }
}
```

Merge these font settings into existing configuration, rather than replacing other preferences. Font size is intentionally left to the application/user. Common Unicode arrows are actual Code glyphs; other symbols may still require system fallback fonts.

## Optional Code features

The current Code release provides **Extended Rust lifetime hooks (`ss01`)** and **Logic (`ss02`)** independently; both are off by default. Enable the desired tag alongside `calt`, `clig` and `liga`: WezTerm accepts `ss01=1` / `ss02=1`; VS Code accepts an explicit font-feature string; Zed accepts `"ss01": true` / `"ss02": true` in its font-feature settings. Logic joins `<>`, `[]`, `<[` / `]>` and `[<` / `>]`.
