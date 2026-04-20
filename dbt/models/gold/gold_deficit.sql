SELECT
     CountryName AS Country
    ,MAX(IIF(LastYear = 1, Value, NULL)) AS LastYear
    ,ROUND(AVG(IIF(Decade = '2000', Value, NULL)), 2) AS Avg2000s
    ,ROUND(AVG(IIF(Decade = '2010', Value, NULL)), 2) AS Avg2010s
    ,ROUND(AVG(IIF(Decade = '2020', Value, NULL)), 2) AS Avg2020s
    ,MAX(IIF(BestYear = 1, Year, NULL)) AS BestYear
    ,MAX(IIF(BestYear = 1, ROUND(Value, 2), NULL)) AS BestValue
    ,MAX(IIF(WorstYear = 1, Year, NULL)) AS WorstYear
    ,MAX(IIF(WorstYear = 1, ROUND(Value, 2), NULL)) AS WorstValue

FROM (
    SELECT
         CountryName
        ,Year
        ,Decade
        ,Indicator
        ,Value
        ,ROW_NUMBER() OVER (PARTITION BY CountryName ORDER BY Year DESC) AS LastYear
        ,ROW_NUMBER() OVER (PARTITION BY CountryName ORDER BY Value DESC) AS BestYear
        ,ROW_NUMBER() OVER (PARTITION BY CountryName ORDER BY Value ASC) AS WorstYear
    FROM {{ ref('silver_fiscal') }}
    WHERE Indicator = 'Deficit'
    ) AS F

GROUP BY CountryName
