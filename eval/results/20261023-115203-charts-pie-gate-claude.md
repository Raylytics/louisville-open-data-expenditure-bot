# Eval: charts-pie-gate-claude

- when: 2026-10-23T11:52:03
- model: `claude-sonnet-5-5,claude-haiku-5-5 (effort high) -> nvidia/nemotron-3-super-120b-a12b:free` (claude)
- **23/23 pass** (sql 23, answer 23)
- repairs: 0 succeeded of 0 attempted
- latency: mean 10.9s per question

| case | tags | sql | answer | s | note |
|---|---|---|---|---:|---|
| fire-vehicles-fy2024 | vocabulary | ✅ | ✅ | 8.2 | 1,581,197.96 ≈ 1,581,197.96 |
| fuel-fy2025 | vocabulary | ✅ | ✅ | 4.7 | 8,206,675.49 ≈ 8,206,675.49 |
| arp-total | vocabulary, year | ✅ | ✅ | 7.8 | 37,636,175.82 ≈ 37,636,175.82 |
| cares-total | vocabulary, year | ✅ | ✅ | 16.9 | 73,831,305.34 ≈ 73,831,305.34 |
| seagrave-total | entity, year | ✅ | ✅ | 3.8 | 12,030,691.29 ≈ 12,030,691.29 |
| lge-total | entity, year | ✅ | ✅ | 12.7 | 357,604,719.64 ≈ 357,604,719.64 |
| paving-vendors | vocabulary | ✅ | ✅ | 18.5 | all present |
| top-agencies-all-time | summary | ✅ | ✅ | 14.2 | top 5 match |
| annual-spend-trend | summary, year | ✅ | ✅ | 10.0 | 19 rows |
| lmpd-by-year | year | ✅ | ✅ | 17.4 | 43,401,681.16 ≈ 43,401,681.16 |
| parks-fy2025 | year | ✅ | ✅ | 5.6 | 43,399,384.03 ≈ 43,399,384.03 |
| library-latest-year | year | ✅ | ✅ | 4.8 | 30,603,121.92 ≈ 30,603,121.92 |
| tech-fy2025 | vocabulary, year | ✅ | ✅ | 8.0 | 22,414,255.52 ≈ 22,414,255.52 |
| mayor-and-chief-pay | entity | ✅ | ✅ | 11.0 | all present |
| highest-paid-positions | summary | ✅ | ✅ | 14.2 | top 3 match |
| police-overtime-2024 | vocabulary, entity | ✅ | ✅ | 12.9 | 23,552,285.59 ≈ 23,552,285.59 |
| registered-agents | summary | ✅ | ✅ | 14.0 | top 5 match |
| grant-funding | summary | ✅ | ✅ | 13.2 | 1,229,361,802.66 ≈ 1,229,361,802.66 |
| largest-payments | summary | ✅ | ✅ | 14.9 | all present |
| capital-projects | summary | ✅ | ✅ | 10.7 | 14 rows |
| contract-splitting-fy2025 | summary | ✅ | ✅ | 20.0 | 25 rows |
| honest-empty-fy2031 | guard | ✅ | ✅ | 3.8 | empty as expected |
| off-topic | guard | ✅ | ✅ | 3.6 | no SQL executed |

## Answers

### fire-vehicles-fy2024

> How much did the Louisville Fire department spend on vehicles in fiscal year 2024?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fiscal_year = 2024
  AND agency_canonical = 'Louisville Fire'
  AND is_data_artifact = FALSE
  AND (spend_category ILIKE '%fleet%' OR spend_category ILIKE '%automotive%' OR spend_category ILIKE '%auto%' OR spend_category ILIKE '%vehicle%' OR spend_category ILIKE '%truck%')
```

Louisville Fire spent about $1.58M on vehicle-related purchases in fiscal year 2024.

### fuel-fy2025

> How much did Louisville Metro spend on fuel in FY2025?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fiscal_year = 2025
  AND spend_category ILIKE '%fuel%'
  AND is_data_artifact = FALSE
```

Louisville Metro paid about $8.2M to vendors for fuel in FY2025.

This is a single combined figure, so it does not show which departments or vendors account for it.

### arp-total

> How much has Louisville spent from the American Rescue Plan?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fund = 'ARP'
  AND is_data_artifact = FALSE
```

Louisville Metro has paid about $37.6M ($37,636,175.82) from its American Rescue Plan fund. This is spending charged to that accounting fund, not the amount of federal money received or awarded.

Council set priority areas for the city's American Rescue Plan recovery funds in R-083-21.

Note: fiscal year 2027 data is partial, so the total may grow as more payments are loaded.

### cares-total

> How much CARES Act coronavirus relief money did the city spend?

```sql
SELECT COALESCE(fund, 'TOTAL - ALL CARES FUNDS') AS fund, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fund ILIKE '%cares%'
  AND fund IS NOT NULL
  AND is_data_artifact = FALSE
GROUP BY ROLLUP(fund)
ORDER BY total_spend DESC NULLS LAST
```

Spending from CARES-named, grant-type accounting funds totals $139,614,685.03 (about $139.6M) across 8 funds.

1. CARES Coronavirus Relief Fund (CRF): $73.8M
2. CARES-US Treasury: $38.7M
3. CARES - US Treasury 2: $22.9M
4. CARES ESG: $2.2M
5. ESG CARES I: $1.3M

Three smaller funds make up the rest: CARES CSBG ($525.4K), CARES CESF funding ($167.3K) and CARES Fires ($30.1K).

The Coronavirus Relief Fund alone is about 53% of the total. Together with the two US Treasury funds, it accounts for about 97%. Resolution R-011-21 authorized the mayor to accept CARES Act funding through the U.S. Department of Housing and Urban Development for the Emergency Solutions Grant program.

These figures are payments from funds with CARES in the name, not the amount of CARES Act money the city received. Funds without "CARES" in their names are not counted.

### seagrave-total

> How much has the city paid Seagrave Fire Apparatus in total?

```sql
SELECT payee_canonical, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE payee_canonical = 'SEAGRAVE FIRE APPARATUS LLC'
GROUP BY payee_canonical
```

The city has paid Seagrave Fire Apparatus LLC a total of about $12.0M ($12,030,691.29).

### lge-total

> How much has Louisville Metro paid LG&E over the years?

```sql
SELECT payee_canonical, ROUND(SUM(extended_amount), 2) AS total_spend, COUNT(*) AS payment_count, MIN(fiscal_year) AS first_year, MAX(fiscal_year) AS last_year
FROM expenditures
WHERE payee_canonical LIKE '%Louisville Gas & Electric%'
  AND is_data_artifact = FALSE
  AND payee_canonical IS NOT NULL
GROUP BY payee_canonical
ORDER BY total_spend DESC
```

Louisville Metro has paid Louisville Gas & Electric Company about $357.6M across 425,223 payments, in records running from fiscal year 2008 through fiscal year 2027.

That averages about $841 per payment.

Fiscal year 2027 is incomplete (loaded through 2026-09-14), so its part of the total is partial. The figure covers only payments recorded under the name "Louisville Gas & Electric Company."

### paving-vendors

> Which vendors were paid the most for road paving?

```sql
SELECT payee_canonical,
       ROUND(SUM(extended_amount), 2) AS total_spend,
       COUNT(*) AS payment_count
FROM expenditures
WHERE is_data_artifact = FALSE
  AND payee_canonical IS NOT NULL
  AND (spend_category ILIKE '%paving%'
       OR project ILIKE '%paving%'
       OR cost_center ILIKE '%paving%')
GROUP BY payee_canonical
HAVING SUM(extended_amount) IS NOT NULL
ORDER BY total_spend DESC
LIMIT 10
```

Hall Contracting of Kentucky Inc was paid the most for road paving, at $151.5M across 2,544 payments. That is about three times the next vendor.

The top five vendors by total payments:

1. Hall Contracting of Kentucky Inc - $151.5M (2,544 payments)
2. Louisville Paving Company Inc - $48.8M (666 payments)
3. Pace Contracting LLC - $10.7M (63 payments)
4. Joash Construction Inc - $6.3M (349 payments)
5. Strand Associates Inc - $6.0M (795 payments)

Pace Contracting averaged about $169K per payment, while Strand Associates had many more payments (795) with a much smaller total.

Payments were counted as paving when the word "paving" appeared in their spending category, project, or cost center. Some vendors listed may therefore have been paid for work related to paving projects rather than the paving itself.

### top-agencies-all-time

> Which agencies have spent the most money across all fiscal years?

```sql
SELECT agency, ROUND(total_spend, 2) AS total_spend, transaction_count, first_year, last_year
FROM summary_agency_spend
WHERE agency IS NOT NULL
ORDER BY total_spend DESC
LIMIT 10
```

Public Works & Assets has spent the most across all fiscal years: about $1.08B, roughly 2.6 times the next department. Spending for fiscal year 2027 is partial.

The top five by total spending:
1. Public Works & Assets: $1.08B
2. Economic Development: $411.2M
3. Facilities & Fleet Management: $403.7M
4. Office of Housing & Community Development: $378.4M
5. Community Services & Revitalization: $351.4M

Community Services & Revitalization has by far the most transactions in the top ten (497,012), averaging about $707 each, yet it ranks fifth in dollars. Its records end in 2025, while most other departments' records run through 2027. Facilities & Fleet Management's records begin in 2017, later than the 2008 start for several others, so its total covers fewer years.

### annual-spend-trend

> How has total annual spending changed from 2008 to 2026?

```sql
SELECT fiscal_year, ROUND(total_spend, 2) AS total_spend, transaction_count
FROM summary_annual_spend
WHERE fiscal_year BETWEEN 2008 AND 2026
ORDER BY fiscal_year ASC
```

Annual spending rose from $244.8M in FY2008 to $600.2M in FY2026, about 2.5 times higher, with most of the growth coming after FY2020.

1. From FY2008 to FY2020, spending stayed between about $210M and $279M. The low was $210.3M in FY2013 and the peak was $278.9M in FY2009.
2. Spending jumped from $247.2M in FY2020 to $374.6M in FY2021 and $411.6M in FY2022.
3. FY2023 dropped to $277.7M, then spending rose to $541.5M in FY2024.
4. The high point was $643.7M in FY2025. FY2026 came in at $600.2M, about $43.5M lower.

Transaction counts did not always move with dollars. FY2008 had 129,647 transactions, FY2013 had 94,113, and FY2026 had 164,760. FY2023's drop to $277.7M came with 109,206 transactions, well below the 163,631 in FY2022 and 173,733 in FY2024.

### lmpd-by-year

> Give me a year-over-year breakdown of LMPD spending

```sql
SELECT fiscal_year, ROUND(SUM(extended_amount), 2) AS total_spend, COUNT(*) AS payment_count
FROM expenditures
WHERE agency_canonical = 'Louisville Metro Police Department'
  AND is_data_artifact = FALSE
  AND fiscal_year IS NOT NULL
GROUP BY fiscal_year
ORDER BY fiscal_year ASC
```

LMPD spending was fairly steady through FY2021, rose sharply after FY2023, and peaked at $43.4M in FY2025. Here is each fiscal year from FY2008 to FY2027, with its total and number of payments:

1. FY2008 - $9.8M (8,117 payments)
2. FY2009 - $9.1M (5,412)
3. FY2010 - $12.2M (5,500)
4. FY2011 - $8.2M (4,869)
5. FY2012 - $6.6M (6,673)
6. FY2013 - $8.8M (8,875)
7. FY2014 - $8.2M (9,682)
8. FY2015 - $9.2M (8,277)
9. FY2016 - $10.4M (5,305)
10. FY2017 - $10.9M (5,627)
11. FY2018 - $11.2M (6,266)
12. FY2019 - $12.1M (4,658)
13. FY2020 - $12.4M (3,507)
14. FY2021 - $11.6M (2,635)
15. FY2022 - $19.4M (2,482)
16. FY2023 - $8.5M (6,935)
17. FY2024 - $27.4M (8,507)
18. FY2025 - $43.4M (9,132)
19. FY2026 - $29.8M (9,005)
20. FY2027 - $5.9M (1,616), partial

Spending stayed between $6.6M and $12.4M through FY2021. FY2022 jumped to $19.4M on the fewest payments of any complete year (2,482), then fell back to $8.5M in FY2023. From FY2023 to FY2025 spending rose about fivefold, with FY2025 up 58% over FY2024. FY2026, a complete year, dropped about 31% from the FY2025 peak but remains well above any year before FY2024.

Note: FY2027 is incomplete (data loaded through 2026-09-14), so don't compare it to full years.

### parks-fy2025

> How much did Parks & Recreation spend in FY2025?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE agency_canonical = 'Parks & Recreation'
  AND fiscal_year = 2025
  AND is_data_artifact = FALSE
```

Parks & Recreation spent about $43.4M in FY2025.

### library-latest-year

> How much did the library spend last year?

```sql
-- Assumed "last year" = fiscal year 2026, the most recent year with complete data
SELECT 2026 AS fiscal_year, ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE fiscal_year = 2026
  AND agency_canonical = 'Louisville Free Public Library'
  AND is_data_artifact = FALSE
```

Louisville Free Public Library spent about $30.6M in fiscal year 2026, the most recent fiscal year with complete expenditure data. I took "last year" to mean fiscal year 2026.

### tech-fy2025

> How much did Louisville spend on technology in FY2025?

```sql
SELECT 'Metro Technology Services department' AS spend_view, ROUND(SUM(extended_amount), 2) AS total_spend FROM expenditures WHERE fiscal_year = 2025 AND agency_canonical = 'Metro Technology Services' AND is_data_artifact = FALSE UNION ALL SELECT 'Computer, software and cloud purchases (all departments)', ROUND(SUM(extended_amount), 2) FROM expenditures WHERE fiscal_year = 2025 AND (spend_category LIKE 'Computer%' OR spend_category ILIKE '%Software%' OR spend_category = 'Cloud Computing Services') AND is_data_artifact = FALSE ORDER BY total_spend DESC
```

Louisville's FY2025 technology spending is $34.7M if you count computer, software and cloud purchases across all departments, or $22.4M if you count only payments charged to Metro Technology Services.

1. Computer, software and cloud purchases (all departments): $34.7M
2. Metro Technology Services department: $22.4M

These are overlapping views of the same spending, not separate slices, so they should not be added together.

### mayor-and-chief-pay

> How much does the mayor make? What about the police chief?

```sql
SELECT Employee_Name, jobTitle, Department, CalYear, Annual_Rate, Regular_Rate, Overtime_Rate, Incentive_Allowance, Other, ROUND(YTD_Total, 2) AS total_pay
FROM salary_data
WHERE CalYear = 2025
  AND jobTitle IN ('Mayor', 'Police Chief')
  AND Employee_Name IS NOT NULL
ORDER BY total_pay DESC
```

In calendar year 2025, the Police Chief was paid more than the Mayor: about $267,811 compared with about $158,116.

1. Police Chief (Paul Louis Humphrey, Louisville Metro Police Department): $267,811 total pay
2. Mayor (Craig Greenberg, Mayor Office): $158,116 total pay

The records list these pay components:
- Police Chief: annual rate $257,697, regular pay $251,278, incentive allowance $7,613, no overtime.
- Mayor: annual rate $158,893, regular pay $158,116, no incentive allowance or overtime.

The Chief's total pay is about $109.7K higher than the Mayor's. Regular pay accounts for about $93.2K of that gap, and the Chief's incentive allowance accounts for another $7,613.

These figures cover pay components only (regular, overtime, incentive, other) and do not include benefits. 2025 is the most recent complete calendar year of salary data.

### highest-paid-positions

> What are the highest paid positions in Louisville Metro government?

```sql
SELECT job_title, department, ROUND(avg_total_comp, 2) AS avg_total_comp, ROUND(max_total_comp, 2) AS max_total_comp, employee_count FROM summary_top_salaries WHERE calendar_year = (SELECT MAX(calendar_year) FROM summary_top_salaries) AND job_title IS NOT NULL ORDER BY avg_total_comp DESC LIMIT 10
```

The highest paid position is the Police Chief at an average of $267,811 in total compensation, followed by the Louisville Zoo Director at $213,466. These figures rank job titles by average total pay for the most recent calendar year in the salary data.

1. Police Chief (Louisville Metro Police Department): $267,811
2. Director (Louisville Zoo): $213,466
3. Deputy Police Chief (Louisville Metro Police Department): $202,892 average, 2 employees
4. Fire Chief (Louisville Fire): $197,516
5. Deputy Mayor - Chief of Staff General Counsel (Mayor Office): $193,777

The next five are the Asst Police Chief - Lt Colonel ($192,593 average, 4 employees), Inspector General ($182,969), Chief Information Officer ($178,711), Chief Financial Officer ($176,244), and Deputy Chief of Staff-Mayor's Office ($174,003).

Police leadership holds three of the top six spots, and the Zoo Director earns more than the Fire Chief. Most titles have one employee, so the figure is that person's pay. For the Deputy Police Chief title, the highest individual amount is $204,679.

Compensation covers pay components only (regular, overtime, incentive, other) and does not include benefits.

### police-overtime-2024

> How much overtime pay did police employees receive in 2024?

```sql
SELECT Department, ROUND(SUM(Overtime_Rate), 2) AS total_overtime_pay, COUNT(DISTINCT Employee_Name) AS employee_count
FROM salary_data
WHERE CalYear = 2024
  AND Department ILIKE '%police%'
  AND Department IS NOT NULL
  AND Overtime_Rate IS NOT NULL
GROUP BY Department
ORDER BY total_overtime_pay DESC
```

Louisville Metro Police Department employees received about $23.6M in overtime pay in calendar year 2024 ($23,552,286).

That covers 1,564 employees, or about $15,059 each on average. Only one department name containing "police" appears in the 2024 salary data, so this is the full result for that match.

This figure is overtime pay only, one component of compensation. It does not include regular pay or other pay components.

### registered-agents

> Who are the registered agents for the top 10 contractors by total spend?

```sql
SELECT payee, ROUND(total_spend, 2) AS total_spend, sos_registered_agent
FROM summary_top_contractors
WHERE sos_registered_agent IS NOT NULL
ORDER BY total_spend DESC
LIMIT 10
```

Five of the ten top contractors by total spend use the same registered agent, C T Corporation System (306 W Main St, Suite 512, Frankfort, KY). The other five use a different Frankfort company, a law firm, or an individual, and four of those five have Louisville addresses.

1. Louisville Gas & Electric Company - $357.6M - C T Corporation System, Frankfort
2. Hall Contracting of Kentucky Inc - $179.1M - Stephen M. Priebe, Louisville
3. Motorola Solutions Inc - $91.6M - C T Corporation System, Frankfort
4. Sullivan & Cozart Inc - $79.5M - Thomas E. Roma, Jr., Manion Stigger, LLP, Louisville
5. Flynn Brothers Contracting Inc - $73.0M - Steve E. Mossholder, Jr., Louisville
6. Humana Health Plan Inc - $67.0M - C T Corporation System, Frankfort
7. Louisville Paving Company Inc - $65.6M - Luke Fitzgerald, Louisville
8. Genuine Parts Company - $65.5M - C T Corporation System, Frankfort
9. Waste Management of Kentucky LLC - $56.2M - C T Corporation System, Frankfort
10. CDW LLC - $55.6M - Corporation Service Company, Frankfort

Note: this list only includes contractors with a registered agent on file. A larger contractor with no agent recorded would not appear, so this may not be the top 10 overall.

### grant-funding

> How much has Louisville spent from grant and federal funds, and which funds are largest?

```sql
SELECT COALESCE(fund, 'TOTAL - ALL GRANT FUNDS') AS fund, ROUND(SUM(total_amount), 2) AS total_amount FROM summary_grant_funding GROUP BY ROLLUP(fund) ORDER BY total_amount DESC NULLS LAST
```

Louisville has spent about $1.23B ($1,229,361,802.66) across 102 accounting funds whose names mark them as grant, federal or pass-through money. This is spending from grant-funded accounts, not grant awards or money received.

The five largest funds:
1. Grant Fund - $488.1M
2. Federally Funded - $151.6M
3. Pass Thru Federal Other - $122.9M
4. CAP KACA Funding - $75.3M
5. CARES Coronavirus Relief Fund (CRF) - $73.8M

The generic "Grant Fund" accounts for about 40% of the total, far more than any other fund. Other large funds include Pass Thru Federal ($45.0M), CARES-US Treasury ($38.7M), Shelter Plus Care ($22.9M) and CARES - US Treasury 2 ($22.9M).

Many of the smaller funds are year-specific CDBG and HOME funds. The smallest, HOME YEAR 2012, shows only $74.02.

I'm naming only 11 of the 102 funds, so this is not a complete list.

### largest-payments

> What are the largest single payments ever made and who received them?

```sql
SELECT DISTINCT payee_canonical, agency_canonical, invoice_amount, invoice_number, invoice_date, fiscal_year
FROM expenditures
WHERE is_data_artifact = FALSE
  AND invoice_amount > 0
  AND payee_canonical IS NOT NULL
  AND agency_canonical IS NOT NULL
ORDER BY invoice_amount DESC
LIMIT 10
```

The largest single payment in the records is $12.0M to Louisville Arena Authority Inc, paid by OMB Finance on 2022-10-31 (FY2023).

The five largest payments:

1. Louisville Arena Authority Inc (OMB Finance): $12.0M, FY2023
2. Motorola Solutions Inc (Emergency Services & MetroSafe): $11.6M, FY2009
3. Louisville Arena Authority Inc (OMB Finance): $10.8M, FY2026
4. Louisville Arena Authority Inc (OMB Finance): $10.8M, FY2025
5. Louisville Arena Authority Inc (OMB Finance): $10.8M, FY2024

Louisville Arena Authority Inc received four of the ten largest payments, all from OMB Finance, one in each of FY2023 through FY2026. The next largest were $10.6M to Sheehan Landing LP (Office of Housing & Community Development, FY2026) and $7.2M to Kentucky Retirement Systems (OMB Finance, FY2011). Axon Enterprise Inc also appears twice in the top ten, with payments of about $6.7M each from the Louisville Metro Police Department.

### capital-projects

> What are the largest capital projects and how much was allocated to each?

```sql
SELECT Project_Na AS project_name, ROUND(Allocation, 2) AS allocation_amount, Agency_Org AS agency, Project AS project_type
FROM capital_projects
WHERE Project_Na IS NOT NULL AND Allocation IS NOT NULL
ORDER BY allocation_amount DESC
```

The largest capital project is Rhodia Brownfields Remediation (Develop Louisville), with $10,000,000 allocated. The five largest projects are:

1. Rhodia Brownfields Remediation (Develop Louisville): $10,000,000
2. Main Library (Louisville Free Public Library): $8,000,000
3. Algonquin Swimming Pool (Parks & Recreation): $7,500,000
4. Baxter Community Center (Develop Louisville): $6,000,000
5. Fern Creek Library (Louisville Free Public Library): $5,000,000

The data lists 14 capital projects in all. Parks & Recreation has the most (7), and its largest allocation is $7.5M for Algonquin Swimming Pool. The smallest entry is New Walnut Park, which shows a $0 allocation.

### contract-splitting-fy2025

> Are there signs of contract splitting in FY2025?

```sql
SELECT payee_canonical, agency_canonical, COUNT(*) AS payments_just_under, ROUND(SUM(invoice_amount), 2) AS total, ROUND(AVG(invoice_amount), 2) AS avg_invoice FROM expenditures WHERE fiscal_year = 2025 AND is_data_artifact = FALSE AND invoice_amount BETWEEN 4000 AND 4999.99 GROUP BY payee_canonical, agency_canonical HAVING COUNT(*) >= 5 ORDER BY payments_just_under DESC, total DESC LIMIT 25
```

Some payees show clusters of payments between $4,000 and $4,999.99 in FY2025, but the data alone can't show whether any of it is contract splitting. The search looked for payee and department pairs with five or more payments in that range, and the list below covers the top 25 by payment count.

Largest clusters by payment count:
1. Louisville Computer Guys Inc (Parks & Recreation): 120 payments, $528,000
2. OverDrive Inc (Louisville Free Public Library): 99 payments, $439,736
3. Louisville Gas & Electric Company (Facilities & Fleet Management): 35 payments, $156,149
4. Strand Associates Inc (Public Works & Assets): 33 payments, $146,420
5. Walker Mechanical Contractors Inc (Department of Corrections): 32 payments, $141,531

Louisville Computer Guys has the most payments, averaging exactly $4,400. Magnolia Dixie Crossings LLC (County Clerk, 17 payments) averages exactly $4,900, and Shaw Secure Solutions LLC (Parks & Recreation, 15 payments) averages exactly $4,550. Payments of the same size are often routine, and this pattern is not evidence of wrongdoing.

The results show only payment counts and amounts. They don't show contract terms, purchase orders or the approval threshold that applies, so confirming splitting would need that information.

### honest-empty-fy2031

> How much did Louisville Fire spend in fiscal year 2031?

```sql
SELECT ROUND(SUM(extended_amount), 2) AS total_spend
FROM expenditures
WHERE agency_canonical = 'Louisville Fire'
  AND fiscal_year = 2031
  AND is_data_artifact = FALSE
```

No rows came back because fiscal year 2031 is outside the range of the expenditure data, which covers FY2008 through FY2027. FY2027 is also incomplete, loaded only through 2026-09-14. No payments have been recorded for 2031 yet.

Try one of these instead:

1. How much did Louisville Fire spend in fiscal year 2026? FY2026 is the most recent complete year.
2. How has Louisville Fire spending changed by fiscal year from FY2008 through FY2027?

Note: Expenditure totals are invoice payments to vendors and other payees, and the FY2027 figures are partial.

### off-topic

> Tell me a joke about cats.

```sql
(none)
```

This question doesn't appear to be answerable from the Louisville Metro expenditure data. Try asking about government spending, agency budgets, contractor payments, employee salaries, or capital projects.
