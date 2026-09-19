"""Sentiment pipeline: FinBERT / CryptoBERT върху заглавия на news_events.

Локален inference (HuggingFace transformers), не харчи API кредити.
Резултатите се версионират по (model_name, model_version) в
`sentiment_scores`, за да могат модели да се сравняват едно към едно.
"""
