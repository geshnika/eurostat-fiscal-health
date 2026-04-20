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
    ,CASE B.sex
        WHEN 'M' THEN 'Male'
        WHEN 'F' THEN 'Female'
     END AS Sex
    ,B.age AS AgeGroup
    ,CAST(B.value AS FLOAT) AS Value
    ,'% of active population' AS Unit

FROM {{ source('bronze', 'bronze_raw') }} AS B

LEFT JOIN {{ ref('dim_country') }} AS C ON C.CountryCode = B.geo
LEFT JOIN {{ ref('dim_date') }} AS D ON D.Year = CAST(B.time_period AS INT)

WHERE B.value IS NOT NULL
  AND B.indicator IN ('unemployment_male', 'unemployment_female')
