"""Align the foot of lowercase i with Code's flat-bottomed lowercase."""

import unicodedata

from italic_companions import apply_shape, contours, shaped_copy


def align_i_baseline(font):
    assert font["post"].isFixedPitch
    table = font["glyf"]
    foot = table["i"].yMin
    lift = table["n"].yMin - foot
    if not lift:
        return []
    names = {
        name
        for cp, name in font.getBestCmap().items()
        if unicodedata.normalize("NFD", chr(cp)).startswith("i")
    }
    names.update(name for name in font.getGlyphOrder() if name.startswith("i."))
    names.add("dotlessi")
    for name in sorted(names):
        source = table[name]
        bodies = [
            section
            for section in contours(source)
            if min(source.coordinates[i][1] for i in section) == foot
            and max(source.coordinates[i][1] for i in section) > 300
        ]
        assert len(bodies) == 1, name
        body = bodies[0]

        def transform(i, x, y):
            if i not in body or y >= 190:
                return x, y
            # Translate the complete foot, easing into the lower shaft.
            t = min(1, (190 - y) / 70)
            return x, y + lift * t**2 * (3 - 2 * t)

        glyph, variations = shaped_copy(
            font, name, name, range(len(source.coordinates)), transform
        )
        apply_shape(font, name, glyph, variations)
    return sorted(names)
