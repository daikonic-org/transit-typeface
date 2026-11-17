# c/a weight balance study

Book comparison: previous c/a; lighter c with smoother join; heavier a with smoother join. Outer size, positioning, advance and a proportions remain constant. The lighter-c trial is built as a separate variable font plus Light/Book/Regular snapshots. No installed or released fonts change.

The lighter-c version moves the inner left curve from x115 to103 and lowers its bottom from45 to35, leaving the outer silhouette fixed. Nominal left stroke changes95 to83; bottom95 to85, matching the85-unit a stem more closely. The first cubic control changes from155,399 to186,398 to better follow the a terminal direction. The original a bowl/counter/stem are unchanged.

The heavier-a option narrows the counter, lowers the inner arch12 source units, and thickens the stem inward; it is included as a Book comparison, not as a separately built family.

Rebuild: .venv/bin/python tools/code_at_c_balance_study.py
Editable outline specimens: Book.svg and NamedWeights.svg. PNG and PDF exports match.
