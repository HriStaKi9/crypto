"""APScheduler orchestrator за непрекъснатия ingestion поток (Етап 1).

Пуска се като дълготраен процес: `python -m ingestion.scheduler`.
Интервалите отразяват реалната честота на обновяване на всеки
източник — GDELT ~15 мин, RSS/CryptoPanic по-често текстово, крипто
цени на всеки час, дневни бар-ове за акции веднъж на ден. Целта по
CLAUDE.md е 2 седмици непрекъснат поток, без модел и без сигнали.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from ingestion import binance, cryptopanic, equities, gdelt

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

    scheduler.add_job(lambda: _job("gdelt", gdelt.run_once), "interval", minutes=15, id="gdelt", misfire_grace_time=300)
    scheduler.add_job(lambda: _job("cryptopanic_rss", cryptopanic.run_once), "interval", minutes=10, id="cryptopanic_rss", misfire_grace_time=300)
    scheduler.add_job(lambda: _job("binance", binance.run_once), "interval", hours=1, id="binance", misfire_grace_time=600)
    scheduler.add_job(lambda: _job("equities", equities.run_once), "interval", hours=24, id="equities", misfire_grace_time=3600)

    logger.info("Ingestion scheduler стартиран (UTC). Ctrl+C за спиране.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Спиране на scheduler-а.")


if __name__ == "__main__":
    main()
