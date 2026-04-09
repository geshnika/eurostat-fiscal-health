import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

DB_SERVER   = os.getenv("DB_SERVER")
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# ── Países Schengen (códigos ISO Eurostat) ───────────────────
SCHENGEN_COUNTRIES = [
    "AT", "BE", "CZ", "DK", "EE", "FI", "FR", "DE", "EL", "HU",
    "IS", "IT", "LV", "LT", "LU", "MT", "NL", "NO", "PL",
    "PT", "SK", "SI", "ES", "SE", "CH"
]

# ── Datasets a actualizar ────────────────────────────────────
DATASETS = [
    {"code": "gov_10dd_edpt1", "name": "government_debt",                  "unit": "PC_GDP",   "sector": "S13", "na_item": "GD",   "cofog": None,    "sex": None},
    {"code": "gov_10dd_edpt1", "name": "government_deficit",               "unit": "PC_GDP",   "sector": "S13", "na_item": "B9",   "cofog": None,    "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_total",     "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "TOTAL", "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_defence",   "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "GF02",  "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_economic",  "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "GF04",  "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_housing",   "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "GF06",  "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_health",    "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "GF07",  "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_education", "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "GF09",  "sex": None},
    {"code": "gov_10a_exp",    "name": "government_expenditure_social",    "unit": "PC_GDP",   "sector": "S13", "na_item": None,   "cofog": "GF10",  "sex": None},
    {"code": "prc_hicp_ainr",  "name": "inflation_hicp",                   "unit": "RCH_A_AVG","sector": None,  "na_item": None,   "cofog": None,    "sex": None},
    {"code": "irt_lt_mcby_a",  "name": "interest_rates_lt",                "unit": None,       "sector": None,  "na_item": None,   "cofog": None,    "sex": None},
    {"code": "une_rt_a",       "name": "unemployment_male",                "unit": "PC_ACT",   "sector": None,  "na_item": None,   "cofog": None,    "sex": "M"},
    {"code": "une_rt_a",       "name": "unemployment_female",              "unit": "PC_ACT",   "sector": None,  "na_item": None,   "cofog": None,    "sex": "F"},
]

BASE_URL    = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
START_YEAR  = "2000"
MAX_WORKERS = 5          # Requests paralelas para datasets por país
API_TIMEOUT = 60         # Segundos por request
INDICATOR_TIMEOUT = 600  # Segundos máximos por indicador completo

# ── Log acumulado de la ejecución ────────────────────────────
run_log = []

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    run_log.append(line)

# ── Conexión ─────────────────────────────────────────────────
def crear_engine():
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        f"Encrypt=yes;TrustServerCertificate=yes;"
    )
    conn_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(conn_str)}"
    return create_engine(conn_url, connect_args={"timeout": 180})

# ── Conexión con reintento y backoff exponencial ─────────────
def conectar(max_intentos=5):
    for intento in range(max_intentos):
        try:
            engine = crear_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine
        except Exception as e:
            espera = 2 ** intento  # 1s, 2s, 4s, 8s, 16s
            log(f"  Conexión fallida (intento {intento + 1}/{max_intentos}): {e}")
            if intento < max_intentos - 1:
                log(f"  Reintentando en {espera}s...")
                time.sleep(espera)
    raise RuntimeError("No se pudo conectar a la database después de varios intentos")

# ── Crear tablas si no existen ───────────────────────────────
CREATE_BRONZE = """
IF NOT EXISTS (
    SELECT 1 
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'eurostat' 
      AND TABLE_NAME   = 'bronze_raw'
)
CREATE TABLE eurostat.bronze_raw (
     Id          INT IDENTITY(1,1) PRIMARY KEY
    ,dataset     NVARCHAR(100)  NOT NULL
    ,indicator   NVARCHAR(100)  NOT NULL
    ,geo         NVARCHAR(10)   NOT NULL
    ,time_period NVARCHAR(20)   NOT NULL
    ,value       FLOAT          NULL
    ,unit        NVARCHAR(50)   NULL
    ,freq        NVARCHAR(10)   NULL
    ,na_item     NVARCHAR(50)   NULL
    ,sector      NVARCHAR(50)   NULL
    ,cofog       NVARCHAR(50)   NULL
    ,sex         NVARCHAR(10)   NULL
    ,loaded_at   DATETIME       DEFAULT GETDATE()
)
"""

CREATE_LOG = """
IF NOT EXISTS (
    SELECT 1 
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'eurostat' 
      AND TABLE_NAME   = 'update_log'
)
CREATE TABLE eurostat.update_log (
     Id             INT IDENTITY(1,1) PRIMARY KEY
    ,run_at         DATETIME       NOT NULL DEFAULT GETDATE()
    ,indicator      NVARCHAR(100)  NOT NULL
    ,rows_before    INT            NOT NULL
    ,rows_inserted  INT            NOT NULL
    ,rows_after     INT            NOT NULL
    ,period_from    NVARCHAR(20)   NULL
    ,period_to      NVARCHAR(20)   NULL
    ,status         NVARCHAR(20)   NOT NULL  -- 'ok' | 'error' | 'no_new_data'
    ,error_msg      NVARCHAR(500)  NULL
)
"""

# ── Request a la API con backoff exponencial ─────────────────
def fetch_api(url, params, max_intentos=4):
    for intento in range(max_intentos):
        try:
            r = requests.get(
                url,
                params  = params,
                headers = {"Accept": "application/json"},
                timeout = API_TIMEOUT
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (400, 404):
                raise  # No reintentar errores de cliente
            espera = 2 ** intento
            log(f"    HTTP {e.response.status_code} — reintentando en {espera}s...")
            time.sleep(espera)
        except Exception as e:
            espera = 2 ** intento
            log(f"    Error de red — reintentando en {espera}s... ({e})")
            time.sleep(espera)
    raise RuntimeError(f"API no respondió después de {max_intentos} intentos")

# ── Parsear respuesta JSON:stat ──────────────────────────────
def parsear_respuesta(data):
    dims   = data.get("dimension", {})
    values = data.get("value", {})
    size   = data.get("size", [])
    ids    = data.get("id", [])

    dim_maps = {}
    for dim_name in ids:
        dim_maps[dim_name] = {
            int(v): k
            for k, v in dims[dim_name]["category"]["index"].items()
        }

    strides = []
    s = 1
    for sz in reversed(size):
        strides.insert(0, s)
        s *= sz

    return ids, dim_maps, strides, values

# ── Extraer registros de una respuesta JSON:stat ─────────────
def extraer_registros(data, code, name, pais, f_unit, f_sector, f_na_item, f_cofog, f_sex):
    ids, dim_maps, strides, values = parsear_respuesta(data)
    registros = []

    for idx_str, val in values.items():
        if val is None:
            continue

        idx    = int(idx_str)
        rem    = idx
        coords = {}
        for i, dim_name in enumerate(ids):
            coord            = rem // strides[i]
            rem              = rem %  strides[i]
            coords[dim_name] = dim_maps[dim_name].get(coord)

        geo_code  = pais if pais else coords.get("geo")
        time_code = coords.get("time")

        if not geo_code or not time_code:
            continue

        if not pais and geo_code not in SCHENGEN_COUNTRIES:
            continue

        # Filtros por dimensión
        if f_unit    and coords.get("unit")    != f_unit:    continue
        if f_sector  and coords.get("sector")  != f_sector:  continue
        if f_na_item and coords.get("na_item") != f_na_item: continue
        if f_sex     and coords.get("sex")     != f_sex:     continue

        if code == "gov_10a_exp":
            if f_unit   and coords.get("unit")   != f_unit:   continue
            if f_sector and coords.get("sector") != f_sector: continue

        if code == "prc_hicp_ainr":
            if coords.get("coicop18") != "TOTAL":              continue
            if f_unit and coords.get("unit") != f_unit:        continue
            if time_code and int(time_code) < int(START_YEAR): continue

        registros.append({
            "dataset"    : code,
            "indicator"  : name,
            "geo"        : geo_code,
            "time_period": time_code,
            "value"      : val,
            "unit"       : coords.get("unit"),
            "freq"       : coords.get("freq"),
            "na_item"    : coords.get("na_item"),
            "sector"     : coords.get("sector"),
            "cofog"      : f_cofog,
            "sex"        : f_sex,
        })

    return registros

# ── Fetch por país (para datasets grandes) ───────────────────
def fetch_pais(pais, code, name, f_unit, f_sector, f_na_item, f_cofog, f_sex):
    params = {"format": "JSON", "lang": "EN", "geo": pais}
    if code == "gov_10a_exp":
        params["cofog99"]         = f_cofog
        params["sinceTimePeriod"] = START_YEAR

    try:
        data = fetch_api(f"{BASE_URL}/{code}", params)
        registros = extraer_registros(data, code, name, pais, f_unit, f_sector, f_na_item, f_cofog, f_sex)
        return pais, registros, None
    except Exception as e:
        return pais, [], str(e)

# ── Insertar solo filas nuevas ───────────────────────────────
def insertar_nuevas(df_nuevo, name, engine):
    # Obtener claves existentes
    with engine.connect() as conn:
        existentes = pd.read_sql(
            text(f"SELECT geo, time_period FROM eurostat.bronze_raw WHERE indicator = '{name}'"),
            conn
        )

    rows_before = len(existentes)

    if rows_before > 0:
        # Obtener período actual antes de insertar
        with engine.connect() as conn:
            periodo = conn.execute(text(
                f"SELECT MIN(time_period), MAX(time_period) FROM eurostat.bronze_raw WHERE indicator = '{name}'"
            )).fetchone()
        period_from_before = periodo[0]
        period_to_before   = periodo[1]
    else:
        period_from_before = None
        period_to_before   = None

    # Identificar filas nuevas
    if rows_before > 0:
        key_existentes = set(zip(existentes["geo"], existentes["time_period"]))
        mask = df_nuevo.apply(
            lambda r: (r["geo"], r["time_period"]) not in key_existentes, axis=1
        )
        df_insertar = df_nuevo[mask].copy()
    else:
        df_insertar = df_nuevo.copy()

    rows_inserted = len(df_insertar)

    if rows_inserted > 0:
        df_insertar.to_sql(
            "bronze_raw",
            crear_engine(),
            schema    = "eurostat",
            if_exists = "append",
            index     = False,
            method    = "multi",
            chunksize = 500
        )

    # Obtener período después de insertar
    with engine.connect() as conn:
        periodo_new = conn.execute(text(
            f"SELECT MIN(time_period), MAX(time_period), COUNT(*) FROM eurostat.bronze_raw WHERE indicator = '{name}'"
        )).fetchone()

    rows_after    = periodo_new[2]
    period_from   = periodo_new[0]
    period_to     = periodo_new[1]

    return rows_before, rows_inserted, rows_after, period_from, period_to

# ── Registrar en update_log ──────────────────────────────────
def registrar_log(engine, indicator, rows_before, rows_inserted, rows_after,
                  period_from, period_to, status, error_msg=None):
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO eurostat.update_log
                (indicator, rows_before, rows_inserted, rows_after,
                 period_from, period_to, status, error_msg)
            VALUES
                (:indicator, :rows_before, :rows_inserted, :rows_after,
                 :period_from, :period_to, :status, :error_msg)
        """), {
            "indicator"    : indicator,
            "rows_before"  : rows_before,
            "rows_inserted": rows_inserted,
            "rows_after"   : rows_after,
            "period_from"  : period_from,
            "period_to"    : period_to,
            "status"       : status,
            "error_msg"    : error_msg
        })
        conn.commit()

# ── Actualizar un indicador ──────────────────────────────────
def update_indicator(dataset_config, engine):
    code      = dataset_config["code"]
    name      = dataset_config["name"]
    f_unit    = dataset_config.get("unit")
    f_sector  = dataset_config.get("sector")
    f_na_item = dataset_config.get("na_item")
    f_cofog   = dataset_config.get("cofog")
    f_sex     = dataset_config.get("sex")

    log(f"\n{'='*60}")
    log(f"Actualizando: {name} ({code})")
    log(f"{'='*60}")

    start_ts = time.time()

    try:
        # ── Datasets que requieren request por país ──────────
        if code in ("gov_10a_exp", "prc_hicp_ainr"):
            todos_registros = []
            errores_pais    = []

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        fetch_pais, pais, code, name,
                        f_unit, f_sector, f_na_item, f_cofog, f_sex
                    ): pais
                    for pais in SCHENGEN_COUNTRIES
                }
                for future in as_completed(futures):
                    pais, registros, error = future.result()
                    if error:
                        log(f"  {pais}: ERROR — {error}")
                        errores_pais.append(pais)
                    else:
                        todos_registros.extend(registros)
                        log(f"  {pais}: {len(registros)} registros filtrados")

            if errores_pais:
                log(f"  Países con error: {errores_pais}")

            if not todos_registros:
                log(f"  Sin datos para {name}")
                registrar_log(engine, name, 0, 0, 0, None, None, "no_new_data")
                return

            df_nuevo = pd.DataFrame(todos_registros)
            df_nuevo = df_nuevo[df_nuevo["time_period"].notna()]

        # ── Caso general: request única ──────────────────────
        else:
            params = {
                "format"          : "JSON",
                "lang"            : "EN",
                "sinceTimePeriod" : START_YEAR
            }
            data     = fetch_api(f"{BASE_URL}/{code}", params)
            registros = extraer_registros(
                data, code, name, None,
                f_unit, f_sector, f_na_item, f_cofog, f_sex
            )

            if not registros:
                log(f"  Sin datos para {name}")
                registrar_log(engine, name, 0, 0, 0, None, None, "no_new_data")
                return

            df_nuevo = pd.DataFrame(registros)

        # ── Insertar solo filas nuevas ───────────────────────
        rows_before, rows_inserted, rows_after, period_from, period_to = \
            insertar_nuevas(df_nuevo, name, engine)

        elapsed = round(time.time() - start_ts, 2)

        if rows_inserted > 0:
            log(f"  Filas previas   : {rows_before:,}")
            log(f"  Filas insertadas: {rows_inserted:,}")
            log(f"  Filas totales   : {rows_after:,}")
            log(f"  Período         : {period_from} → {period_to}")
            log(f"  Tiempo          : {elapsed}s")
            registrar_log(engine, name, rows_before, rows_inserted, rows_after,
                         period_from, period_to, "ok")
        else:
            log(f"  Sin datos nuevos | Filas existentes: {rows_before:,} | Período: {period_from} → {period_to}")
            registrar_log(engine, name, rows_before, 0, rows_after,
                         period_from, period_to, "no_new_data")

    except Exception as e:
        elapsed = round(time.time() - start_ts, 2)
        log(f"  ERROR en {name}: {e} | {elapsed}s")
        registrar_log(engine, name, 0, 0, 0, None, None, "error", str(e)[:500])

# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    run_start = datetime.now(timezone.utc)
    log(f"Iniciando actualización Eurostat — {run_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Conectar con reintento
    engine = conectar()

    # Crear tablas si no existen
    with engine.connect() as conn:
        conn.execute(text(CREATE_BRONZE))
        conn.execute(text(CREATE_LOG))
        conn.commit()
    log("Tablas verificadas")

    # Actualizar cada indicador
    total_insertadas = 0
    for ds in DATASETS:
        update_indicator(ds, engine)

    # Resumen final
    run_end = datetime.now(timezone.utc)
    elapsed_total = round((run_end - run_start).total_seconds(), 1)

    log(f"\n{'='*60}")
    log(f"Actualización completada | Tiempo total: {elapsed_total}s")
    log(f"{'='*60}")

    # Imprimir resumen desde update_log
    with engine.connect() as conn:
        resumen = pd.read_sql(text("""
            SELECT
                 indicator
                ,rows_before
                ,rows_inserted
                ,rows_after
                ,period_from
                ,period_to
                ,status
            FROM eurostat.update_log
            WHERE CAST(run_at AS DATE) = CAST(GETDATE() AS DATE)
            ORDER BY Id ASC
        """), conn)

    print("\n" + resumen.to_string(index=False))