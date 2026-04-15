SELECT
     B.geo AS CountryCode
    ,C.CountryName
    ,C.Region
    ,C.RegionCode
    ,C.EuroZone
    ,C.EUMember
    ,C.Currency
    ,CAST(B.time_period AS INT) AS Year
    ,D.EraLabel
    ,D.IsCrisisYear
    ,D.Decade
    ,CASE B.indicator
        WHEN 'inflation_hicp'    THEN 'Inflation (HICP)'
        WHEN 'interest_rates_lt' THEN 'Long-term Interest Rate'
     END AS Indicator
    ,CAST(B.value AS FLOAT) AS Value
    ,CASE B.indicator
        WHEN 'inflation_hicp'    THEN 'Annual % change'
        WHEN 'interest_rates_lt' THEN 'Annual %'
     END AS Unit

FROM eurostat.bronze_raw AS B

LEFT JOIN eurostat.dim_country AS C ON C.CountryCode = B.geo
LEFT JOIN eurostat.dim_date AS D ON D.Year = CAST(B.time_period AS INT)

WHERE B.value IS NOT NULL
  AND B.indicator IN ('inflation_hicp', 'interest_rates_lt')