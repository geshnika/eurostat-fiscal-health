# Eurostat Fiscal Health

Analysis of fiscal and macroeconomic health across the Schengen Area using official Eurostat data.

---

## Context

How do Schengen Area governments manage their finances? What priorities emerge in public spending across crises, recoveries, and shocks?

This project tracks 13 macroeconomic indicators across 25 Schengen countries from 2000 to the present, covering the Global Financial Crisis, the Eurozone Debt Crisis, the COVID-19 pandemic, and the 2022 inflation shock.

---

## Research Questions

### Fiscal
1. How has public debt evolved across the Schengen Area?
2. Which countries consolidated their finances after the Eurozone debt crisis — and which did not?
3. How did the composition of public expenditure change after COVID-19 and the 2022 inflation shock?
4. What regional patterns emerge in public expenditure across the different economic eras?

### Monetary
5. How have inflation and long-term interest rates evolved across the Schengen Area?
6. What differences can be observed between countries inside and outside the eurozone?

### Labor
7. How has unemployment by sex evolved across the Schengen Area?

---

## Architecture

```
Bronze (Python)         eurostat.bronze_raw          Raw data from Eurostat API
Seeds  (dbt)            eurostat.dim_country         25 Schengen countries with metadata
                        eurostat.dim_date            Years 2000–2025 with historical context
                        eurostat.dim_cofog           COFOG classification of government expenditure
Silver (dbt views)      eurostat.silver_fiscal       Debt, deficit and expenditure by COFOG
                        eurostat.silver_monetary     Inflation and long-term interest rates
                        eurostat.silver_labor        Unemployment by sex
Gold   (dbt views)      eurostat.gold_*              Fact tables for Power BI reporting
```

> **Note:** This architecture is designed to migrate to Microsoft Fabric (Lakehouse + dbt Core + Power BI Direct Lake). Current implementation uses Azure SQL Server + Power BI Import due to the absence of a free Fabric capacity tier.

---

## Stack

| Layer | Technology |
|---|---|
| Ingestion | Python 3.14, requests, pandas, SQLAlchemy |
| Storage | Azure SQL Server (Free Offer — portfolio database) |
| Transformation | dbt Core 1.11 + dbt-sqlserver adapter |
| Orchestration | GitHub Actions (monthly cron) |
| Reporting | Power BI Desktop (Import mode) |
| Version control | GitHub |

---

## Data Sources

| Dataset | Description | Frequency |
|---|---|---|
| `gov_10dd_edpt1` | Government debt and deficit | Annual |
| `gov_10a_exp` | Government expenditure by COFOG | Annual |
| `prc_hicp_ainr` | Inflation — HICP annual rate of change | Annual |
| `irt_lt_mcby_a` | Long-term interest rates | Annual |
| `une_rt_a` | Unemployment rate by sex | Annual |

All data sourced from the [Eurostat public API](https://ec.europa.eu/eurostat/web/main/data/web-services) — no authentication required.

---

## Countries

25 Schengen Area countries: AT, BE, CH, CZ, DE, DK, EE, EL, ES, FI, FR, HU, IS, IT, LT, LU, LV, MT, NL, NO, PL, PT, SE, SI, SK.

> Liechtenstein (LI) excluded due to insufficient data coverage in Eurostat.

---

## Pipeline

### Initial load
```bash
python ingestion/extract.py
```

### Monthly update
```bash
python ingestion/update.py
```
Automated via GitHub Actions on the 1st of every month at 07:00 UTC.

### dbt transformations
```bash
# Activate virtual environment
.venv-dbt\Scripts\Activate.ps1

# Run all models
dbt run --project-dir dbt

# Run tests
dbt test --project-dir dbt
```

---

## Repository Structure

```
eurostat-fiscal-health/
├── ingestion/
│   ├── extract.py          # Full historical load
│   └── update.py           # Incremental monthly update
├── dbt/
│   ├── models/
│   │   └── silver/
│   │       ├── silver_fiscal.sql
│   │       ├── silver_monetary.sql
│   │       ├── silver_labor.sql
│   │       └── schema.yml
│   ├── seeds/
│   │   ├── dim_country.csv
│   │   ├── dim_date.csv
│   │   └── dim_cofog.csv
│   └── macros/
│       └── generate_schema_name.sql
├── sql/
├── power_bi/
├── docs/
└── .github/
    └── workflows/
        └── eurostat_update.yml
```

---

## Results

See [RESULTS.md](RESULTS.md) for findings and answers to the research questions above.
