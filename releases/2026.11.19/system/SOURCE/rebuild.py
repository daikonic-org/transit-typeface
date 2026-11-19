from pathlib import Path
import gzip
from fontTools.ttLib import TTFont
for path in sorted(Path(__file__).resolve().parent.glob('*.ttx.gz')):
    font = TTFont(recalcTimestamp=False)
    with gzip.open(path, 'rb') as source:
        font.importXML(source)
    font.save(path.with_name(path.name.removesuffix('.ttx.gz') + '-VF.ttf'))
