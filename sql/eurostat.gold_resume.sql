-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
--														 CTE: Inicio														  --
-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --

WITH
  Inflation AS ( -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- - Cumulative inflation in the last decade <<<
	SELECT
		 CountryCode
		,MAX(IIF(YEAR = YEAR(GETDATE()) - 1, Value, NULL)) AS LY_Inflation
		,EXP(SUM(LOG(1 + Value / 100.0))) - 1 AS Cumulative_Inflation
	FROM eurostat.silver_monetary AS M
	WHERE Year >= YEAR(GETDATE()) -10
	  AND Indicator = 'Inflation (HICP)'
	GROUP BY CountryCode
),

  Interest AS ( -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- - - Long-term interest rate <<<
	SELECT
		 CountryCode
		,MAX(IIF(YEAR = YEAR(GETDATE()) - 1, ROUND(Value, 2), NULL)) AS LY_Interest
		,ROUND(AVG(Value), 2) AS AVG_Interest
	FROM eurostat.silver_monetary AS M
	WHERE Year >= YEAR(GETDATE()) -10
	  AND Indicator = 'Long-term Interest Rate'
	GROUP BY CountryCode
),

  Fiscal AS ( -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- - - Fiscal spending as a percentage of the previous year's GDP <<<
	SELECT
		 F.CountryCode
		,MAX(IIF(Indicator = 'Health', Value, NULL)) AS Health
		,MAX(IIF(Indicator = 'Defence', Value, NULL)) AS Defence
		,MAX(IIF(Indicator = 'Housing', Value, NULL)) AS Housing
		,MAX(IIF(Indicator = 'Social Protection', Value, NULL)) AS SocialProtection
		,MAX(IIF(Indicator = 'Education', Value, NULL)) AS Education
		,MAX(IIF(Indicator = 'Economic Affairs', Value, NULL)) AS EconomicAffairs
		,MAX(IIF(Indicator = 'Debt', Value, NULL)) AS Debt
		,MAX(IIF(Indicator = 'Deficit', Value, NULL)) AS Deficit
	FROM eurostat.silver_fiscal AS F
	INNER JOIN (
		SELECT
			 CountryCode
			,MAX(Year) AS LastYear
		FROM eurostat.silver_fiscal
		GROUP BY CountryCode
		) AS LY ON LY.CountryCode = F.CountryCode AND LY.LastYear = F.Year
	GROUP BY F.CountryCode
),

  Labor AS (
	SELECT
		 L.CountryCode
		,MAX(IIF(Year = LastYear AND Sex = 'Male', Value, NULL)) AS LY_MaleValue
		,MAX(IIF(Year = LastYear AND Sex = 'Female', Value, NULL)) AS LY_FemaleValue
		,ROUND(AVG(IIF(Sex = 'Male', Value, NULL)), 2) AS AVG_MaleValue
		,ROUND(AVG(IIF(Sex = 'Female', Value, NULL)), 2) AS AVG_FemaleValue
	FROM eurostat.silver_labor AS L
	LEFT JOIN (
		SELECT
			 CountryCode
			,MAX(Year) AS LastYear
		FROM eurostat.silver_labor
		GROUP BY CountryCode
		) AS LY ON LY.CountryCode = L.CountryCode
	WHERE L.Year >= YEAR(GETDATE()) - 10
	GROUP BY L.CountryCode
)

-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
--														  CTE: Fin														      --
-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --

SELECT
	 C.CountryName AS Country
	,C.Region

	,Debt -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- Fiscal >>>
	,Deficit
	,Defence
	,EconomicAffairs
	,Education
	,Health
	,Housing
	,SocialProtection

	,Inf.LY_Inflation -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- Inflation >>>
	,ROUND(Inf.Cumulative_Inflation * 100, 2) AS Cumulative_Inflation

	,Int.LY_Interest -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- - Interest >>>
	,Int.AVG_Interest

	,LY_MaleValue -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- - Labor >>>
	,LY_FemaleValue
	,AVG_MaleValue
	,AVG_FemaleValue

FROM eurostat.dim_country AS C

LEFT JOIN Inflation AS Inf ON Inf.CountryCode = C.CountryCode
LEFT JOIN Interest AS Int ON Int.CountryCode = C.CountryCode
LEFT JOIN Fiscal AS F ON F.CountryCode = C.CountryCode
LEFT JOIN Labor AS L ON L.CountryCode = C.CountryCode