"""Entity linking: news_events -> assets, чрез asset_aliases.

Alias matching (exact / cashtag / regex) с confidence тежест от
`asset_aliases.confidence`, за да не се броят двусмислени псевдоними
("Link", "Apple") с пълна тежест. Резултат: `news_asset_link`.
"""
