"""Композитен signal engine: -2..+2 (strong sell .. strong buy).

Чете точково-времеви sentiment features САМО през `v_signal_features`
(използва `available_at`), комбинирано с технически индикатори от
`technical.py`. Никога не чете `published_at` — виж CLAUDE.md, правило 1.
"""
