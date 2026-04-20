WITH
  Inflation AS (
    SELECT
         CountryName
        ,Year
        ,Decade
        ,Indicator
        ,Value
        ,ROW_NUMBER() OVER (PARTITION BY CountryName ORDER BY Year DESC) AS LastYear
        ,ROW_NUMBER() OVER (PARTITION BY CountryName ORDER BY Value ASC) AS BestYear
        ,ROW_NUMBER() OVER (PARTITION BY CountryName ORDER BY Value DESC) AS WorstYear
    FROM {{ ref('silver_monetary') }}
    WHERE Indicator = 'Inflation (HICP)'
),

  CumulativeInflation AS (
    SELECT
         CountryName
        ,Decade
        ,ROUND((EXP(SUM(LOG(1 + Value/100))) - 1) * 100, 2) AS CumulativeInflation
    FROM Inflation
    GROUP BY
         CountryName
        ,Decade
)

SELECT
     I.CountryName AS Country
    ,MAX(IIF(I.LastYear = 1, Value, NULL)) AS LastYear
    ,ROUND(AVG(IIF(I.Decade = '2000', Value, NULL)), 2) AS Avg2000s
    ,MAX(IIF(Ci.Decade = '2000', CumulativeInflation, NULL)) AS Cumulative2000s
    ,ROUND(AVG(IIF(I.Decade = '2010', value, NULL)), 2) AS Avg2010s
    ,MAX(IIF(Ci.Decade = '2010', CumulativeInflation, NULL)) AS Cumulative2010s
    ,ROUND(AVG(IIF(I.Decade = '2020', value, NULL)), 2) AS Avg2020s
    ,MAX(IIF(Ci.Decade = '2020', CumulativeInflation, NULL)) AS Cumulative2020s
    ,MAX(IIF(I.BestYear = 1, Year, NULL)) AS LowestYear
    ,MAX(IIF(I.BestYear = 1, ROUND(Value, 2), NULL)) AS LowestValue
    ,MAX(IIF(I.WorstYear = 1, Year, NULL)) AS HighestYear
    ,MAX(IIF(I.WorstYear = 1, ROUND(Value, 2), NULL)) AS HighestValue

FROM Inflation AS I
LEFT JOIN CumulativeInflation AS Ci ON Ci.CountryName = I.CountryName

GROUP BY I.CountryName
