"""APScheduler orchestrator за непрекъснатия ingestion поток (Етап 1).

Пуска се като дълготраен процес: `python -m ingestion.scheduler`.
Интервалите отразяват реалната честота на обновяване на всеки
източник — GDELT ~15 мин, RSS/CryptoPanic по-често текстово, крипто
цени на всеки час, дневни бар-ове за акции веднъж на ден. Целта по
CLAUDE.md е 2 седмици непрекъснат поток, без модел и без сигнали.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from ingestion import binance, cryptopanic, equities, gdelt, rss_feeds

logger = logging.getLogger(__name__)


def _job(name: str, fn) -> None:
    """Обвивка, за да не убие изключение в един job целия scheduler process."""
    try:
        fn()
    except Exception:
        logger.exception("Job '%s' гръмна — scheduler-ът продължава напред", name)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scheduler = BlockingScheduler(timezone="UTC")
    now = datetime.now(timezone.utc)

    # next_run_time=now: първи fire веднага при старт (не след цял
    # interval) — за да не гледаш празен dashboard 15-24ч след `docker
    # compose up`. Малко разминати start offset-и, за да не тръгнат
    # всичките 5 job-а в една и съща секунда.
    scheduler.add_job(lambda: _job("gdelt", gdelt.run_once), "interval", minutes=15, id="gdelt", misfire_grace_time=300, next_run_time=now)
    scheduler.add_job(lambda: _job("cryptopanic", cryptopanic.run_once), "interval", minutes=10, id="cryptopanic", misfire_grace_time=300, next_run_time=now + timedelta(seconds=5))
    scheduler.add_job(lambda: _job("rss_feeds", rss_feeds.run_once), "interval", minutes=15, id="rss_feeds", misfire_grace_time=300, next_run_time=now + timedelta(seconds=10))
    scheduler.add_job(lambda: _job("binance", binance.run_once), "interval", hours=1, id="binance", misfire_grace_time=600, next_run_time=now + timedelta(seconds=15))
    scheduler.add_job(lambda: _job("equities", equities.run_once), "interval", hours=24, id="equities", misfire_grace_time=3600, next_run_time=now + timedelta(seconds=20))

    logger.info("Ingestion scheduler стартиран (UTC). Ctrl+C за спиране.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Спиране на scheduler-а.")


if __name__ == "__main__":
    main()
