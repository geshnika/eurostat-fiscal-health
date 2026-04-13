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
        WHEN 'government_debt' 	  THEN 'Debt'
        WHEN 'government_deficit' THEN 'Deficit'
        ELSE CF.CofogName
     END AS Indicator
    ,CAST(B.value AS FLOAT) AS Value
	,'% of GDP' AS Unit

FROM {{ source('bronze', 'bronze_raw') }} AS B

LEFT JOIN {{ ref('dim_country') }} AS C ON C.CountryCode = B.geo
LEFT JOIN {{ ref('dim_date') }} AS D ON D.Year = CAST(B.time_period AS INT)
LEFT JOIN {{ ref('dim_cofog') }} AS CF ON CF.CofogCode = B.cofog

WHERE B.value IS NOT NULL
  AND (
        B.indicator IN ('government_debt', 'government_deficit')
        OR B.indicator LIKE 'government_expenditure%'
      )
  AND (B.cofog <> 'TOTAL' OR B.cofog IS NULL)
