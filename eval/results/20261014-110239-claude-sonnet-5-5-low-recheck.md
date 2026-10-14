# Eval: claude-sonnet-5-5-low-recheck

- when: 2026-10-14T11:02:39
- model: `claude-sonnet-5-5 (effort low) -> nvidia/nemotron-3-super-120b-a12b:free` (claude)
- **23/23 pass** (sql 23, answer 23)
- repairs: 0 succeeded of 0 attempted
- latency: mean 7.7s per question

| case | tags | sql | answer | s | note |
|---|---|---|---|---:|---|
| fire-vehicles-fy2024 | vocabulary | ✅ | ✅ | 8.7 | 1,581,197.96 ≈ 1,581,197.96 |
| fuel-fy2025 | vocabulary | ✅ | ✅ | 4.9 | 8,206,675.49 ≈ 8,206,675.49 |
| arp-total | vocabulary, year | ✅ | ✅ | 5.5 | 37,636,175.82 ≈ 37,636,175.82 |
| cares-total | vocabulary, year | ✅ | ✅ | 8.3 | 73,831,305.34 ≈ 73,831,305.34 |
| seagrave-total | entity, year | ✅ | ✅ | 5.4 | 12,030,691.29 ≈ 12,030,691.29 |
| lge-total | entity, year | ✅ | ✅ | 5.0 | 357,604,719.64 ≈ 357,604,719.64 |
| paving-vendors | vocabulary | ✅ | ✅ | 10.1 | all present |
| top-agencies-all-time | summary | ✅ | ✅ | 11.1 | top 5 match |
| annual-spend-trend | summary, year | ✅ | ✅ | 9.7 | 19 rows |
| lmpd-by-year | year | ✅ | ✅ | 9.6 | 43,401,681.16 ≈ 43,401,681.16 |
| parks-fy2025 | year | ✅ | ✅ | 4.0 | 43,399,384.03 ≈ 43,399,384.03 |
| library-latest-year | year | ✅ | ✅ | 5.7 | 30,603,121.92 ≈ 30,603,121.92 |
| tech-fy2025 | vocabulary, year | ✅ | ✅ | 7.7 | 22,414,255.52 ≈ 22,414,255.52 |
| mayor-and-chief-pay | entity | ✅ | ✅ | 8.0 | all present |
| highest-paid-positions | summary | ✅ | ✅ | 8.9 | top 3 match |
| police-overtime-2024 | vocabulary, entity | ✅ | ✅ | 5.8 | 23,552,285.59 ≈ 23,552,285.59 |
| registered-agents | summary | ✅ | ✅ | 11.3 | top 5 match |
| grant-funding | summary | ✅ | ✅ | 9.4 | 1,229,361,802.66 ≈ 1,229,361,802.66 |
| largest-payments | summary | ✅ | ✅ | 8.4 | all present |
| capital-projects | summary | ✅ | ✅ | 9.7 | 14 rows |
| contract-splitting-fy2025 | summary | ✅ | ✅ | 10.9 | 25 rows |
| honest-empty-fy2031 | guard | ✅ | ✅ | 3.7 | empty as expected |
| off-topic | guard | ✅ | ✅ | 4.5 | no SQL executed |

## Answers

### fire-vehicles-fy2024

> How much did the Louisville Fire department spend on vehicles in fiscal year 2024?

```sql
SELECT spend_category, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fiscal_year = 2024
  AND agency_canonical = 'Louisville Fire'
  AND is_data_artifact = FALSE
  AND (spend_category ILIKE '%fleet%' OR spend_category ILIKE '%automotive%' OR spend_category ILIKE '%auto%' OR spend_category ILIKE '%vehicle%' OR spend_category ILIKE '%truck%')
  AND spend_category IS NOT NULL
GROUP BY ROLLUP(spend_category)
ORDER BY total_spend DESC NULLS LAST
```

Louisville Fire spent about $1.58M on vehicle-related categories in fiscal year 2024.

The largest categories were:

1. Automotive Parts & Accessories: $946,644
2. Automotive Fuel: $504,044
3. Automotive Repair Services: $83,593
4. Automotive Lubricants and Fluids: $45,057
5. Automotive Wrecker Services: $965

A sixth category, Automotive License Fees VET Fees, was $894.92.

Parts and accessories make up roughly 60% of the total, and fuel adds about another third. Repairs, fluids, wrecker services and fees together are a small share.

Note: these figures cover only categories with automotive or vehicle-related names. Purchases of vehicles themselves may be classed under other categories, so this total may not capture every vehicle purchase.

### fuel-fy2025

> How much did Louisville Metro spend on fuel in FY2025?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_fuel_spend
FROM expenditures
WHERE fiscal_year = 2025
  AND spend_category ILIKE '%fuel%'
  AND is_data_artifact = FALSE
```

Louisville Metro paid about $8.2M to vendors in FY2025 in spending categories with "fuel" in the name.

This counts only categories whose names include "fuel," so fuel bought under differently named categories would not be included.

### arp-total

> How much has Louisville spent from the American Rescue Plan?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_arp_spend
FROM expenditures
WHERE fund = 'ARP'
  AND is_data_artifact = FALSE
```

Louisville has spent about $37.6M from the American Rescue Plan fund, based on payments charged to that accounting fund.

This is spending from an accounting fund tied to American Rescue Plan money, not the amount of federal money awarded or received.

Council set the priority areas for the city's American Rescue Plan Local Fiscal Recovery Funds in R-083-21.

Fiscal year 2027 data is incomplete (loaded through 2026-09-14), so the total may still grow.

### cares-total

> How much CARES Act coronavirus relief money did the city spend?

```sql
SELECT fund, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fund ILIKE '%cares%' AND is_data_artifact = FALSE
GROUP BY ROLLUP(fund)
ORDER BY total_spend DESC NULLS LAST
```

Payments charged to CARES-named accounting funds total about $139.6M. This is spending from grant-funded accounts, not the amount awarded or received.

The spending is spread across eight funds:

1. CARES Coronavirus Relief Fund (CRF): $73.8M
2. CARES-US Treasury: $38.7M
3. CARES - US Treasury 2: $22.9M
4. CARES ESG: $2.2M
5. ESG CARES I: $1.3M

Three smaller funds make up the rest: CARES CSBG ($525,394), CARES CESF funding ($167,302), and CARES Fires ($30,089).

The Coronavirus Relief Fund and the two US Treasury funds account for nearly all of the spending, about $135.4M of the $139.6M. Two of the funds, CARES ESG and ESG CARES I, together come to about $3.5M. Resolution R-011-21 authorized the Mayor to accept supplemental CARES Act funding for the Emergency Solutions Grant program.

This count includes only funds with "CARES" in their name, so any coronavirus relief money recorded in funds without that name is not included.

### seagrave-total

> How much has the city paid Seagrave Fire Apparatus in total?

```sql
SELECT payee_canonical, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE payee_canonical = 'SEAGRAVE FIRE APPARATUS LLC'
  AND is_data_artifact = FALSE
GROUP BY payee_canonical
```

The city has paid Seagrave Fire Apparatus LLC a total of about $12.0M ($12,030,691).

This figure covers invoice payments to the vendor under that exact payee name. Payments filed under any other spelling of the name would not be included.

### lge-total

> How much has Louisville Metro paid LG&E over the years?

```sql
SELECT payee_canonical, ROUND(SUM(extended_amount), 2) AS total_paid, COUNT(*) AS transaction_count, MIN(fiscal_year) AS first_year, MAX(fiscal_year) AS last_year
FROM expenditures
WHERE payee_canonical LIKE '%Louisville Gas & Electric%'
  AND is_data_artifact = FALSE
GROUP BY payee_canonical
ORDER BY total_paid DESC
```

Louisville Metro has paid Louisville Gas & Electric Company about $357.6M across fiscal years 2008 through 2027, spread over 425,223 payments.

That works out to roughly $841 per payment on average. Fiscal year 2027 is only partly loaded (through 2026-09-14), so its spending is incomplete and the total will grow as more payments are recorded.

### paving-vendors

> Which vendors were paid the most for road paving?

```sql
SELECT payee_canonical, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE is_data_artifact = FALSE
  AND payee_canonical IS NOT NULL
  AND (spend_category ILIKE '%paving%' OR spend_category ILIKE '%road%' OR cost_center ILIKE '%paving%' OR project ILIKE '%paving%')
GROUP BY payee_canonical
ORDER BY total_spend DESC
LIMIT 15
```

Hall Contracting of Kentucky Inc was paid the most for road paving-related work: $174.9M, more than three times the next vendor, Louisville Paving Company Inc at $53.8M.

1. Hall Contracting of Kentucky Inc: $174.9M
2. Louisville Paving Company Inc: $53.8M
3. Flynn Brothers Contracting Inc: $52.8M
4. Cargill Inc: $16.5M
5. Pace Contracting LLC: $11.1M

Others in the top 15 include Mac Construction & Excavating Inc ($11.0M), Compass Minerals America Inc ($7.8M), Joash Construction Inc ($6.3M), Strand Associates Inc ($6.0M) and Allterrain Paving & Construction LLC ($5.1M).

Riverside Paving & Contracting Co Inc appears twice under slightly different spellings, at $5.3M and $3.9M. Together that is about $9.2M, which would place it sixth.

The list covers payments whose category, department cost center or project mentions "road" or "paving," so some vendors, such as those supplying materials or engineering services, may not be paving contractors, and totals may include related road work.

### top-agencies-all-time

> Which agencies have spent the most money across all fiscal years?

```sql
SELECT agency, ROUND(total_spend, 2) AS total_spend, transaction_count, first_year, last_year
FROM summary_agency_spend
WHERE agency IS NOT NULL
ORDER BY total_spend DESC
LIMIT 10
```

Public Works & Assets has spent the most across all fiscal years, at about $1.08B, roughly 2.6 times the next department.

1. Public Works & Assets - $1.08B
2. Economic Development - $411.2M
3. Facilities & Fleet Management - $403.7M
4. Office of Housing & Community Development - $378.4M
5. Community Services & Revitalization - $351.4M

The next five are OMB Finance ($329.1M), Parks & Recreation ($292.6M), Develop Louisville ($288.2M), Public Health & Wellness ($278.2M), and Louisville Metro Police Department ($274.9M).

Community Services & Revitalization has by far the most transactions (497,012) yet ranks fifth in dollars, which points to many smaller payments. The departments do not all cover the same years: Community Services & Revitalization's records run from 2011 to 2025, and Facilities & Fleet Management's begin in 2017, while most others begin in 2008. Totals are therefore not strictly like-for-like. Fiscal year 2027 spending is partial.

### annual-spend-trend

> How has total annual spending changed from 2008 to 2026?

```sql
SELECT fiscal_year, ROUND(total_spend, 2) AS total_spend, transaction_count
FROM summary_annual_spend
WHERE fiscal_year BETWEEN 2008 AND 2026
ORDER BY fiscal_year ASC
```

Total annual spending rose from $244.8M in FY2008 to $600.2M in FY2026, an increase of about 145%.

The path was uneven:

1. FY2008-FY2015: Spending fell from $244.8M to a low of $210.3M in FY2013, then stayed near $215M.
2. FY2016-FY2020: Spending ranged from $233.0M to $273.1M, apart from a rise to $252.0M in FY2016 and a dip to $247.2M in FY2020. FY2009 ($278.9M) was higher than any year in this period.
3. FY2021-FY2022: Spending jumped to $374.6M and then $411.6M.
4. FY2023: Spending dropped to $277.7M, with transactions falling to 109,206.
5. FY2024-FY2026: Spending reached $541.5M, peaked at $643.7M in FY2025, and eased to $600.2M in FY2026.

The FY2023 dip and the FY2024 rebound are the most unusual features. Spending nearly doubled in one year (up about $263.9M), while transactions rose from 109,206 to 173,733. The records alone do not explain the FY2023 dip.

These figures are not adjusted for inflation.

### lmpd-by-year

> Give me a year-over-year breakdown of LMPD spending

```sql
SELECT fiscal_year, ROUND(SUM(extended_amount), 2) AS total_spend, COUNT(*) AS transaction_count
FROM expenditures
WHERE agency_canonical = 'Louisville Metro Police Department'
  AND is_data_artifact = FALSE
  AND fiscal_year IS NOT NULL
GROUP BY fiscal_year
ORDER BY fiscal_year ASC
```

LMPD vendor payments peaked at $43.4M in FY2025, after rising sharply in recent years.

- FY2008 to FY2021 stayed between about $6.6M and $12.4M per year. The low was $6.6M in FY2012 and the high was $12.4M in FY2020. (Note: FY2010 was $12.2M, so the range is consistent.)
- FY2022 jumped to $19.4M, then fell to $8.5M in FY2023.
- FY2024 reached $27.4M, FY2025 hit $43.4M (the peak), and FY2026 was $29.8M. FY2026 is the latest complete year, down about 31% from FY2025.
- FY2027 shows $5.9M across 1,616 transactions, but that year is incomplete (data loaded through 2026-09-14), so it is not comparable.

Transaction counts do not track dollars. FY2021 and FY2022 had the fewest transactions (2,635 and 2,482), yet FY2022 spending was far higher than the year before. In FY2025 the count was 9,132 transactions, similar to FY2014 (9,682), but total spend was over five times higher.

Full series, in $M by fiscal year: 2008 9.8, 2009 9.1, 2010 12.2, 2011 8.2, 2012 6.6, 2013 8.8, 2014 8.2, 2015 9.2, 2016 10.4, 2017 10.9, 2018 11.2, 2019 12.1, 2020 12.4, 2021 11.6, 2022 19.4, 2023 8.5, 2024 27.4, 2025 43.4, 2026 29.8, 2027 5.9 (partial).

### parks-fy2025

> How much did Parks & Recreation spend in FY2025?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fiscal_year = 2025
  AND agency_canonical = 'Parks & Recreation'
  AND is_data_artifact = FALSE
```

Parks & Recreation spent about $43.4M in FY2025 (exactly $43,399,384.03).

### library-latest-year

> How much did the library spend last year?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE agency_canonical = 'Louisville Free Public Library'
  AND fiscal_year = 2026 -- assumed FY2026, the most recent year with complete data
  AND is_data_artifact = FALSE
```

The Louisville Free Public Library spent about $30.6M in fiscal year 2026, the most recent fiscal year with complete expenditure data. I took "last year" to mean fiscal year 2026.

### tech-fy2025

> How much did Louisville spend on technology in FY2025?

```sql
SELECT 'Metro Technology Services department' AS spend_view, ROUND(SUM(extended_amount), 2) AS total_spend FROM expenditures WHERE fiscal_year = 2025 AND agency_canonical = 'Metro Technology Services' AND is_data_artifact = FALSE
UNION ALL
SELECT 'Computer, software and cloud purchases (all departments)', ROUND(SUM(extended_amount), 2) FROM expenditures WHERE fiscal_year = 2025 AND (spend_category LIKE 'Computer%' OR spend_category ILIKE '%Software%' OR spend_category = 'Cloud Computing Services') AND is_data_artifact = FALSE
ORDER BY total_spend DESC
```

Louisville's FY2025 technology spending depends on how you count it: computer, software and cloud purchases across all departments came to $34.7M, while payments under the Metro Technology Services department came to $22.4M.

1. Computer, software and cloud purchases (all departments): $34.7M
2. Metro Technology Services department: $22.4M

These are two different views of the same spending, so they should not be added together. A single purchase can appear in both.

The first view counts technology-type purchases made by any department. The second counts payments made under the Metro Technology Services department. The category view is based on purchase categories named computer, software or cloud computing services, so technology purchases recorded under other categories would not be captured.

### mayor-and-chief-pay

> How much does the mayor make? What about the police chief?

```sql
SELECT Employee_Name, jobTitle, Department, CalYear, ROUND(Annual_Rate, 2) AS Annual_Rate, ROUND(Regular_Rate, 2) AS Regular_Rate, ROUND(Overtime_Rate, 2) AS Overtime_Rate, ROUND(Incentive_Allowance, 2) AS Incentive_Allowance, ROUND(YTD_Total, 2) AS YTD_Total
FROM salary_data
WHERE CalYear = 2025
  AND jobTitle IN ('Mayor', 'Police Chief')
  AND Employee_Name IS NOT NULL
ORDER BY YTD_Total DESC
```

In calendar year 2025 (the most recent complete year of salary data), the Police Chief was paid more than the Mayor.

1. Police Chief Paul Louis Humphrey (Louisville Metro Police Department): $267,811 in total pay
2. Mayor Craig Greenberg (Mayor Office): $158,116 in total pay

The Police Chief's annual rate is $257,697, made up of a regular rate of $251,278 plus an incentive allowance of $7,613. The Mayor's annual rate is $158,893, with a regular rate of $158,116 and no incentive allowance.

Neither position shows any overtime. The Police Chief's total pay is about $109,696 higher than the Mayor's, roughly 1.7 times as much.

These figures are pay components only (regular, overtime, incentive, other) and contain no benefits information.

### highest-paid-positions

> What are the highest paid positions in Louisville Metro government?

```sql
SELECT job_title, department, ROUND(avg_total_comp, 2) AS avg_total_comp, ROUND(max_total_comp, 2) AS max_total_comp, employee_count FROM summary_top_salaries WHERE calendar_year = (SELECT MAX(calendar_year) FROM summary_top_salaries) AND job_title IS NOT NULL ORDER BY avg_total_comp DESC LIMIT 10
```

The highest paid position is the Police Chief, at an average total compensation of $267,811 (one employee). The figures below come from the most recent calendar year in the salary summary, though the results do not say which year that is, so they may be partial if it is 2026.

1. Police Chief (Louisville Metro Police Department): $267,811
2. Director (Louisville Zoo): $213,466
3. Deputy Police Chief (Louisville Metro Police Department): $202,892
4. Fire Chief (Louisville Fire): $197,516
5. Deputy Mayor - Chief of Staff General Counsel (Mayor Office): $193,777

The next five are Asst Police Chief - Lt Colonel (Louisville Metro Police Department, $192,593), Inspector General (Office of Inspector General, $182,969), Chief Information Officer (Metro Technology Services, $178,711), Chief Financial Officer (OMB Finance, $176,244), and Deputy Chief of Staff-Mayor's Office (Mayor Office, $174,003).

Police leadership holds three of the top ten spots. Most of these titles have one employee, so the average is that person's pay. The exceptions are Deputy Police Chief (2 employees, highest $204,679) and Asst Police Chief - Lt Colonel (4 employees).

These amounts are pay components only (regular, overtime, incentive, other). The ranking is by average total compensation per job title.

### police-overtime-2024

> How much overtime pay did police employees receive in 2024?

```sql
SELECT ROUND(SUM(Overtime_Rate), 2) AS total_overtime_pay, COUNT(DISTINCT Employee_Name) AS employees_with_overtime
FROM salary_data
WHERE CalYear = 2024
AND Department ILIKE '%police%'
AND Overtime_Rate > 0
```

Police employees received about $23.6M in overtime pay in calendar year 2024, spread across 1,342 employees who had overtime above zero. That works out to roughly $17,551 per employee on average.

This is the overtime component of pay only, not total compensation.

### registered-agents

> Who are the registered agents for the top 10 contractors by total spend?

```sql
SELECT payee, ROUND(total_spend, 2) AS total_spend, sos_registered_agent FROM summary_top_contractors WHERE sos_registered_agent IS NOT NULL ORDER BY total_spend DESC LIMIT 10
```

Six of the top 10 contractors with a registered agent on file use C T Corporation System in Frankfort, KY: LG&E, Motorola, Humana, Genuine Parts, Waste Management and one more is not correct, so here is the accurate count: five (LG&E, Motorola, Humana, Genuine Parts and Waste Management).

1. Louisville Gas & Electric Company - $357.6M - C T Corporation System, 306 W Main St Suite 512, Frankfort, KY 40601
2. Hall Contracting of Kentucky Inc - $179.1M - Stephen M. Priebe, 3800 Crittenden Drive, Louisville, KY 40209
3. Motorola Solutions Inc - $91.6M - C T Corporation System, 306 W Main St Suite 512, Frankfort, KY 40601
4. Sullivan & Cozart Inc - $79.5M - Thomas E. Roma, Jr., Manion Stigger, LLP, 2301 River Road Suite 101, Louisville, KY 40206
5. Flynn Brothers Contracting Inc - $73.0M - Steve E. Mossholder, Jr., 4515 Bishop Ln Ste A, Louisville, KY 40218

The remaining five are:
6. Humana Health Plan Inc - $67.0M - C T Corporation System, Frankfort, KY
7. Louisville Paving Company Inc - $65.6M - Luke Fitzgerald, 15415 Shelbyville Road, Louisville, KY 40245
8. Genuine Parts Company - $65.5M - C T Corporation System, Frankfort, KY
9. Waste Management of Kentucky LLC - $56.2M - C T Corporation System, Frankfort, KY
10. CDW LLC - $55.6M - Corporation Service Company, 315 High Street, Frankfort, KY 40601

### grant-funding

> How much has Louisville spent from grant and federal funds, and which funds are largest?

```sql
SELECT COALESCE(fund, 'TOTAL - ALL GRANT FUNDS') AS fund, ROUND(SUM(total_amount), 2) AS total_amount FROM summary_grant_funding GROUP BY ROLLUP(fund) ORDER BY total_amount DESC NULLS LAST
```

Louisville has spent about $1.23B ($1,229,361,802.66) from grant and federal funds. These figures are payments charged to funds whose names mark them as grant, federal or pass-through money, so they show spending from grant-funded accounts, not grant awards or money received. The total covers 102 accounting funds.

The largest funds are:

1. Grant Fund - $488.1M
2. Federally Funded - $151.6M
3. Pass Thru Federal Other - $122.9M
4. CAP KACA Funding - $75.3M
5. CARES Coronavirus Relief Fund (CRF) - $73.8M

These are 5 of the 102 funds. The generic Grant Fund accounts for roughly 40% of the total. Several other CARES funds also rank high, and many of the smaller funds are separate CDBG and HOME program years. The smallest fund shown is HOME YEAR 2012 at $74.02.

### largest-payments

> What are the largest single payments ever made and who received them?

```sql
SELECT payee, agency, ROUND(invoice_amount, 2) AS invoice_amount, invoice_number, invoice_date, fiscal_year
FROM summary_largest_payments
WHERE invoice_amount > 0
  AND payee IS NOT NULL
  AND agency IS NOT NULL
ORDER BY invoice_amount DESC
LIMIT 10
```

The largest single payment on record is $12,000,000 to Louisville Arena Authority Inc, paid by OMB Finance (invoice LAAFY23, dated 2022-10-31, FY2023).

The largest payments shown are:
1. Louisville Arena Authority Inc: $12,000,000 (OMB Finance, FY2023)
2. Motorola Solutions Inc: $11,593,676.70 (Emergency Services & MetroSafe, FY2009)
3. Louisville Arena Authority Inc: $10,800,000 (OMB Finance, FY2024, FY2025 and FY2026, one payment each year)
4. SHEEHAN LANDING LP: $10,617,313 (Office of Housing & Community Development, FY2026)
5. Kentucky Retirement Systems: $7,196,820.86 (OMB Finance, FY2011)

The next largest is $6,801,474.69 to WILLIAM S WETTERER (Develop Louisville, FY2023).

Louisville Arena Authority Inc received four of these payments, ranging from $10.8M to $12.0M. The Motorola Solutions and Kentucky Retirement Systems payments each appeared twice in the results with identical details, so I counted each once, as they appear to be duplicate rows rather than separate payments.

### capital-projects

> What are the largest capital projects and how much was allocated to each?

```sql
SELECT Project_Na, Agency_Org, Project, Allocation
FROM capital_projects
WHERE Project_Na IS NOT NULL AND Allocation IS NOT NULL
ORDER BY Allocation DESC
```

The largest capital project is Rhodia Brownfields Remediation (Develop Louisville) at $10,000,000, followed by Main Library at $8,000,000.

1. Rhodia Brownfields Remediation (Develop Louisville) - $10,000,000
2. Main Library (Louisville Free Public Library) - $8,000,000
3. Algonquin Swimming Pool (Parks & Recreation) - $7,500,000
4. Baxter Community Center (Develop Louisville) - $6,000,000
5. Fern Creek Library (Louisville Free Public Library) - $5,000,000

Other projects are smaller. Camp Taylor Waterpark has $4,500,000 and Chickasaw Park Pond has $2,500,000. Windsor Spray Ground has $1,000,000. Portland Library and Parkland Library each have $800,000. Elliott Park and Iroquois Tennis Courts each have $500,000, and Berrytown Park has $200,000. New Walnut Park (Develop Louisville) shows an allocation of $0.

Parks & Recreation has the most projects in the list (7).

### contract-splitting-fy2025

> Are there signs of contract splitting in FY2025?

```sql
SELECT payee_canonical, agency_canonical, COUNT(*) AS payments_just_under, ROUND(SUM(invoice_amount), 2) AS total, ROUND(AVG(invoice_amount), 2) AS avg_invoice FROM expenditures WHERE fiscal_year = 2025 AND is_data_artifact = FALSE AND invoice_amount BETWEEN 4000 AND 4999.99 GROUP BY payee_canonical, agency_canonical HAVING COUNT(*) >= 5 ORDER BY payments_just_under DESC, total DESC LIMIT 25
```

Yes, some payees show clusters of invoices just under $5,000 in FY2025, but these records alone cannot show whether any of it is deliberate contract splitting. The search covered invoices from $4,000 to $4,999.99, with at least 5 per payee and department pair.

The largest clusters:

1. Louisville Computer Guys Inc (Parks & Recreation): 120 invoices totaling $528,000, averaging $4,400
2. Overdrive Inc (Louisville Free Public Library): 99 invoices totaling $439,736
3. Louisville Gas & Electric Company (Facilities & Fleet Management): 35 invoices totaling $156,149
4. Strand Associates Inc (Public Works & Assets): 33 invoices totaling $146,420
5. Walker Mechanical Contractors Inc (Department of Corrections): 32 invoices totaling $141,531

Louisville Computer Guys stands out most, with an average of exactly $4,400 across 120 payments. Magnolia Dixie Crossings LLC (County Clerk, $4,900 average) and Shaw Secure Solutions LLC (Parks & Recreation, $4,550 average) also show round, uniform averages. Same-size payments like these are often routine recurring charges, and utilities such as LG&E and AT&T commonly bill this way too.

The $5,000 line is an assumed threshold; the results do not show which purchasing limit applies. Treat these as leads for review of the underlying contracts and purchase orders, not as evidence of wrongdoing.

### honest-empty-fy2031

> How much did Louisville Fire spend in fiscal year 2031?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fiscal_year = 2031
  AND agency_canonical = 'Louisville Fire'
  AND is_data_artifact = FALSE
```

No spending data exists for fiscal year 2031. The expenditure data runs from FY2008 through FY2027, and FY2027 is only partial (loaded through 2026-09-14). A future year like 2031 has no payments recorded yet, so the query came back empty.

Try one of these instead:

1. How much did Louisville Fire spend in fiscal year 2026? (the most recent complete year)
2. How much has Louisville Fire spent so far in fiscal year 2027? (partial-year total)

Note: I can't confirm from this result that "Louisville Fire" is the exact agency name in the data, so if those questions also return nothing, the agency name may need adjusting.

### off-topic

> Tell me a joke about cats.

```sql
(none)
```

This question doesn't appear to be answerable from the Louisville Metro expenditure data. Try asking about government spending, agency budgets, contractor payments, employee salaries, or capital projects.
