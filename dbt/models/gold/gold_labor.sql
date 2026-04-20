SELECT
     CountryName AS Country
    ,MAX(IIF(Sex = 'Male' AND LastYear = 1, Value, NULL)) AS LastYearMale
    ,MAX(IIF(Sex = 'Male' AND RankBest = 1, Year, NULL)) AS BestYearMale
    ,MAX(IIF(Sex = 'Male' AND RankBest = 1, Value, NULL)) AS BestValueMale
    ,MAX(IIF(Sex = 'Male' AND RankWorst = 1, Year, NULL)) AS WorstYearMale
    ,MAX(IIF(Sex = 'Male' AND RankWorst = 1, Value, NULL)) AS WorstValueMale
    ,ROUND(AVG(IIF(Sex = 'Male' AND AgeGroup = 'Y15-24', Value, NULL)), 2) AS YoungMale
    ,ROUND(AVG(IIF(Sex = 'Male' AND AgeGroup = 'Y25-54', Value, NULL)), 2) AS PrimeAgeMale
    ,ROUND(AVG(IIF(Sex = 'Male' AND AgeGroup = 'Y55-74', Value, NULL)), 2) AS AdultMale
    ,ROUND(AVG(IIF(Sex = 'Male' AND AgeGroup = 'Y15-74' AND Decade = '2000', Value, NULL)), 2) AS Male2000s
    ,ROUND(AVG(IIF(Sex = 'Male' AND AgeGroup = 'Y15-74' AND Decade = '2010', Value, NULL)), 2) AS Male2010s
    ,ROUND(AVG(IIF(Sex = 'Male' AND AgeGroup = 'Y15-74' AND Decade = '2020', Value, NULL)), 2) AS Male2020s
    ,MAX(IIF(Sex = 'Female' AND LastYear = 1, Value, NULL)) AS LastYearFemale
    ,MAX(IIF(Sex = 'Female' AND RankBest = 1, Year, NULL)) AS BestYearFemale
    ,MAX(IIF(Sex = 'Female' AND RankBest = 1, Value, NULL)) AS BestValueFemale
    ,MAX(IIF(Sex = 'Female' AND RankWorst = 1, Year, NULL)) AS WorstYearFemale
    ,MAX(IIF(Sex = 'Female' AND RankWorst = 1, Value, NULL)) AS WorstValueFemale
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y15-24', Value, NULL)), 2) AS YoungFemale
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y25-54', Value, NULL)), 2) AS PrimeAgeFemale
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y55-74', Value, NULL)), 2) AS AdultFemale
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y15-74' AND Decade = '2000', Value, NULL)), 2) AS Female2000s
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y15-74' AND Decade = '2010', Value, NULL)), 2) AS Female2010s
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y15-74' AND Decade = '2020', Value, NULL)), 2) AS Female2020s
    ,ROUND(AVG(IIF(Sex = 'Female' AND AgeGroup = 'Y15-74', Value, NULL)) -
           AVG(IIF(Sex = 'Male'   AND AgeGroup = 'Y15-74', Value, NULL)), 2) AS GenderGap

FROM (
    SELECT
         CountryName
        ,Region
        ,EuroZone
        ,EUMember
        ,Year
        ,Decade
        ,Sex
        ,AgeGroup
        ,Value
        ,IIF(AgeGroup = 'Y15-74', DENSE_RANK() OVER (PARTITION BY CountryName, Sex ORDER BY Year DESC), NULL) AS LastYear
        ,IIF(AgeGroup = 'Y15-74', ROW_NUMBER() OVER (PARTITION BY CountryName, Sex, AgeGroup ORDER BY Value ASC), NULL) AS RankBest
        ,IIF(AgeGroup = 'Y15-74', ROW_NUMBER() OVER (PARTITION BY CountryName, Sex, AgeGroup ORDER BY Value DESC), NULL) AS RankWorst
    FROM {{ ref('silver_labor') }}
    WHERE AgeGroup IN ('Y15-74', 'Y15-24', 'Y25-54', 'Y55-74')
    ) AS L

GROUP BY CountryName
