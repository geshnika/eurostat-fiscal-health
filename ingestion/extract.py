import os
import time
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

DB_SERVER   = os.getenv("DB_SERVER")
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# ── Países Schengen (códigos ISO Eurostat) ───────────────────
# LI (Liechtenstein) excluido — datos insuficientes en Eurostat
SCHENGEN_COUNTRIES = [
    "AT", "BE", "CZ", "DK", "EE", "FI", "FR", "DE", "EL", "HU",
    "IS", "IT", "LV", "LT", "LU", "MT", "NL", "NO", "PL",
    "PT", "SK", "SI", "ES", "SE", "CH"
]

# ── Datasets a ingestar ──────────────────────────────────────
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

BASE_URL   = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
START_YEAR = "2000"

# ── Conexión — siempre nueva para evitar timeouts ────────────
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

# ── Verificar / crear tabla bronze con reintento ─────────────
CREATE_BRONZE = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'eurostat'
    AND TABLE_NAME = 'bronze_raw'
)
CREATE TABLE eurostat.bronze_raw (
     Id          INT IDENTITY(1,1) PRIMARY KEY
    ,dataset     NVARCHAR(100)     NOT NULL
    ,indicator   NVARCHAR(100)     NOT NULL
    ,geo         NVARCHAR(10)      NOT NULL
    ,time_period NVARCHAR(20)      NOT NULL
    ,value       FLOAT             NULL
    ,unit        NVARCHAR(50)      NULL
    ,freq        NVARCHAR(10)      NULL
    ,na_item     NVARCHAR(50)      NULL
    ,sector      NVARCHAR(50)      NULL
    ,cofog       NVARCHAR(50)      NULL
    ,sex         NVARCHAR(10)      NULL
    ,age         NVARCHAR(20)      NULL
    ,loaded_at   DATETIME          DEFAULT GETDATE()
)
"""

for intento in range(5):
    try:
        with crear_engine().connect() as conn:
            conn.execute(text(CREATE_BRONZE))
            conn.commit()
            print("Tabla eurostat.bronze_raw verificada")
        break
    except Exception as e:
        print(f"  Conexión fallida (intento {intento + 1}/5): {e}")
        print("  Esperando 30s para que la database se reactive...")
        time.sleep(30)
else:
    raise RuntimeError("No se pudo conectar a la database después de 5 intentos")

# ── Función auxiliar: parsear respuesta JSON:stat ────────────
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

# ── Función auxiliar: escribir a SQL con reintento ───────────
def escribir_sql(df, name):
    for intento in range(5):
        try:
            with crear_engine().connect() as conn:
                conn.execute(text(f"DELETE FROM eurostat.bronze_raw WHERE indicator = '{name}'"))
                conn.commit()
            df.to_sql("bronze_raw", crear_engine(), schema="eurostat", if_exists="append", index=False)
            return
        except Exception as e:
            print(f"  SQL fallido (intento {intento + 1}/5): {e}")
            print("  Esperando 30s...")
            time.sleep(30)
    raise RuntimeError(f"No se pudo escribir {name} después de 5 intentos")

# ── Función de extracción ────────────────────────────────────
def extract_dataset(dataset_config):
    code      = dataset_config["code"]
    name      = dataset_config["name"]
    f_unit    = dataset_config.get("unit")
    f_sector  = dataset_config.get("sector")
    f_na_item = dataset_config.get("na_item")
    f_cofog   = dataset_config.get("cofog")
    f_sex     = dataset_config.get("sex")

    print(f"\n{'='*60}")
    print(f"Extrayendo: {name} ({code})")
    print(f"{'='*60}")

    start = time.time()

    # ── Datasets que requieren request por país ──────────────
    if code in ("gov_10a_exp", "prc_hicp_ainr"):
        todos_registros = []

        for pais in SCHENGEN_COUNTRIES:
            params_pais = {
                "format" : "JSON",
                "lang"   : "EN",
                "geo"    : pais,
            }
            if code == "gov_10a_exp":
                params_pais["cofog99"]         = f_cofog
                params_pais["sinceTimePeriod"] = START_YEAR

            try:
                r = requests.get(
                    f"{BASE_URL}/{code}",
                    params  = params_pais,
                    headers = {"Accept": "application/json"},
                    timeout = 60
                )
                r.raise_for_status()
                d = r.json()
            except Exception as e:
                print(f"  {pais}: ERROR — {e}")
                time.sleep(1)
                continue

            ids, dim_maps, strides, values = parsear_respuesta(d)

            for idx_str, val in values.items():
                idx    = int(idx_str)
                rem    = idx
                coords = {}
                for i, dim_name in enumerate(ids):
                    coord            = rem // strides[i]
                    rem              = rem %  strides[i]
                    coords[dim_name] = dim_maps[dim_name].get(coord)

                if code == "gov_10a_exp":
                    if f_unit   and coords.get("unit")   != f_unit:   continue
                    if f_sector and coords.get("sector") != f_sector: continue

                if code == "prc_hicp_ainr":
                    if coords.get("coicop18") != "TOTAL":              continue
                    if f_unit and coords.get("unit") != f_unit:        continue
                    time_code = coords.get("time")
                    if time_code and int(time_code) < int(START_YEAR): continue

                todos_registros.append({
                    "dataset"    : code,
                    "indicator"  : name,
                    "geo"        : pais,
                    "time_period": coords.get("time"),
                    "value"      : val,
                    "unit"       : coords.get("unit"),
                    "freq"       : coords.get("freq"),
                    "na_item"    : None,
                    "sector"     : coords.get("sector"),
                    "cofog"      : f_cofog,
                    "sex"        : None,
                    "age"        : None,
                })

            print(f"  {pais}: {len(values)} valores")
            time.sleep(0.3)

        if not todos_registros:
            print(f"  Sin datos para {code} / {name}")
            return 0

        df = pd.DataFrame(todos_registros)
        df = df[df["time_period"].notna()]

        escribir_sql(df, name)

        elapsed = round(time.time() - start, 2)
        print(f"  {len(df):,} filas cargadas | {elapsed}s")
        return len(df)

    # ── Caso general: request única, filtrado en Python ──────
    params = {
        "format"          : "JSON",
        "lang"            : "EN",
        "sinceTimePeriod" : START_YEAR
    }

    try:
        response = requests.get(
            f"{BASE_URL}/{code}",
            params  = params,
            headers = {"Accept": "application/json"},
            timeout = 120
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"  ERROR en API: {e}")
        return 0

    ids, dim_maps, strides, values = parsear_respuesta(data)

    registros = []
    for idx_str, val in values.items():
        idx    = int(idx_str)
        rem    = idx
        coords = {}
        for i, dim_name in enumerate(ids):
            coord            = rem // strides[i]
            rem              = rem %  strides[i]
            coords[dim_name] = dim_maps[dim_name].get(coord)

        geo_code  = coords.get("geo")
        time_code = coords.get("time")

        if not geo_code or not time_code:
            continue

        if geo_code not in SCHENGEN_COUNTRIES:
            continue

        if f_unit    and coords.get("unit")    != f_unit:    continue
        if f_sector  and coords.get("sector")  != f_sector:  continue
        if f_na_item and coords.get("na_item") != f_na_item: continue
        if f_sex     and coords.get("sex")     != f_sex:     continue

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
            "age"        : coords.get("age") if code == "une_rt_a" else None,
        })

    if not registros:
        print(f"  Sin datos para {code} / {name}")
        return 0

    df = pd.DataFrame(registros)

    escribir_sql(df, name)

    elapsed = round(time.time() - start, 2)
    print(f"  {len(df):,} filas cargadas | {elapsed}s")
    return len(df)

# ── Ejecutar todos los datasets ──────────────────────────────
total = 0
for ds in DATASETS:
    total += extract_dataset(ds)

print(f"\n{'='*60}")
print(f"Ingesta completada: {total:,} filas totales")
print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*60}")
