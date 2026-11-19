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

Upright Code includes **Hairlining (`ss05`)**, which is off by default. Enable `ss05=1` in WezTerm, `'ss05' on` in VS Code, or `"ss05": true` in Zed. The hairline set includes the diamond Rust lifetime form.

**Logic (`ss02`)** is optional in upright and italic. It joins `<>` and `[]`. Mixed `<[` / `]>` and `[<` / `>]` use separate, tightly fitted glyphs and forced tall angles.

Upright Code applies texture healing with `calt`. To turn healing off while keeping the other contextual features active, enable `ss04=1` in WezTerm, `'ss04' on` in VS Code, or `"ss04": true` in Zed. Paired `ff`, `tt` and `ll` use `liga` in both upright and italic.
