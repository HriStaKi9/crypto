# Лек алтернативен вариант на timescale/timescaledb-ha:pg16 — същите
# extensions (timescaledb + pgvector), но върху обикновен postgres:16
# вместо многогигабайтовия HA image. Полезен, ако pull-ването на
# timescaledb-ha е бавно/блокирано на твоята мрежа: смени docker-compose.yml
# db услугата от `image: timescale/timescaledb-ha:pg16` на `build: db/`.
#
# "-ha" вариантът е замислен за production clustering (Patroni, repmgr
# и т.н.) — overkill за локална разработка с една инстанция; този image
# има точно нужните extensions и нищо повече.
FROM postgres:16

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends -qq curl gnupg ca-certificates \
    && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /usr/share/keyrings/timescaledb-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/timescaledb-archive-keyring.gpg] https://packagecloud.io/timescale/timescaledb/debian/ $(. /etc/os-release && echo $VERSION_CODENAME) main" > /etc/apt/sources.list.d/timescaledb.list \
    && apt-get update -qq \
    && apt-get install -y --no-install-recommends -qq timescaledb-2-postgresql-16 postgresql-16-pgvector \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN echo "shared_preload_libraries = 'timescaledb'" >> /usr/share/postgresql/postgresql.conf.sample
