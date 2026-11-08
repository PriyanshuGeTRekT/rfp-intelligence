# Extraction evaluation

Results from `outputs` scored against `eval/extraction_gold.yaml`: 60 fields, accuracy 83.3%.

| Bid | Accuracy |
|---|---|
| Bid1 | 90.0% |
| Bid2 | 95.0% |
| Bid3 | 65.0% |

## Calibration: accuracy per confidence tier

A well-ordered table has accuracy falling as the tier falls. Tiers with few fields say little; the counts are shown for that reason.

| Tier | Fields | Correct | Accuracy |
|---|---|---|---|
| A | 8 | 7 | 88% |
| B | 24 | 23 | 96% |
| C | 10 | 10 | 100% |
| NF-1 | 11 | 8 | 73% |
| NF-2 | 3 | 2 | 67% |
| X | 4 | 0 | 0% |

## Per field

| Bid | Field | Pass | Tier | Status | Value | Reason |
|---|---|---|---|---|---|---|
| Bid1 | bid_number | yes | B | found | JA-207652 | a pattern matched |
| Bid1 | title | yes | B | found | Student and Staff Computing Devices | all patterns present |
| Bid1 | due_date | yes | A | found | 2024-07-09 14:00 CDT | instant matches |
| Bid1 | pre_bid_meeting | yes | A | found | 2024-06-10 14:00 CST via TEAMS video conference; attendance  | instant matches |
| Bid1 | bid_submission_type | yes | B | found | Electronic submission via iSupplier portal (https://www.dall | a pattern matched |
| Bid1 | term_of_bid | yes | B | found | Initial term of 3 years with two one-year renewals, not to e | all patterns present |
| Bid1 | bid_bond_requirement | yes | NF-1 | not_found | null | absent, as expected |
| Bid1 | delivery_date | yes | NF-2 | not_found | null | absent, as expected |
| Bid1 | payment_terms | yes | NF-2 | not_found | null | absent, as expected |
| Bid1 | additional_documentation | yes | A | found | MWBE Forms ; W9 Form ; Punch Out Process - OPTIONAL ; 1295 f | all items present |
| Bid1 | installation | yes | A | found | White glove services including asset decaling, asset reporti | all patterns present |
| Bid1 | mfg_for_registration | yes | A | found | OEM | found, but states the absence |
| Bid1 | contract_or_cooperative | yes | B | found | Educational Purchasing Cooperative of North Texas (EPCNT) an | found, but states the absence |
| Bid1 | model_no | yes | NF-1 | not_found | null | absent, as expected |
| Bid1 | part_no | yes | NF-1 | not_found | null | absent, as expected |
| Bid1 | product | NO | B | found | Tier 1 Small Student Chromebook Laptop (Touch) – 1, Tier 2 L | missing ['50,?000'] |
| Bid1 | contact_info | yes | B | found | Procurement Services, 972-925-3700, ProcurementCS@dallasisd. | a pattern matched |
| Bid1 | company_name | yes | B | found | Dallas Independent School District | all patterns present |
| Bid1 | product_specification | NO | X | failed | null | expected a value, got null |
| Bid1 | bid_summary | yes | B | found | Dallas Independent School District is seeking to purchase on | all patterns present |
| Bid2 | bid_number | yes | B | found | #E20P4600040 | a pattern matched |
| Bid2 | title | yes | B | found | Dell Laptops w/Extended Warranty | all patterns present |
| Bid2 | due_date | yes | C | found | 2024-06-10 14:00 EDT | instant matches |
| Bid2 | pre_bid_meeting | yes | NF-1 | not_found | null | absent, as expected |
| Bid2 | bid_submission_type | yes | B | found | Electronic submission via eMaryland Marketplace Advantage (e | all patterns present |
| Bid2 | term_of_bid | yes | B | found | Fixed Price; proposals must be valid for at least 90 days af | all patterns present |
| Bid2 | bid_bond_requirement | yes | NF-1 | not_found | null | absent, as expected |
| Bid2 | delivery_date | yes | B | found | within 45 days of Award | all patterns present |
| Bid2 | payment_terms | yes | B | found | Invoice(s) shall be submitted within 10 days of delivering t | all patterns present |
| Bid2 | additional_documentation | NO | A | found | Mercury Affidavit ; Attachment N – Contract Affidavit | missing items ['warrant'] |
| Bid2 | installation | yes | NF-1 | not_found | null | absent, as expected |
| Bid2 | mfg_for_registration | yes | B | found | Dell | all patterns present |
| Bid2 | contract_or_cooperative | yes | B | found | Desktop, Laptop and Tablet 2015 Master Contract, 060B5400007 | a pattern matched |
| Bid2 | model_no | yes | A | found | Dell Latitude 5550 ; Dell Thunderbolt 4 Dock – WD22TB4 | all items present |
| Bid2 | part_no | yes | B | found | 210-BLYZ ; 379-BFNZ ; 619-ARSB ; 658-BCSB ; 338-CNRG ; 338-C | all items present |
| Bid2 | product | yes | B | found | Dell Latitude 5550 Laptop – Qty 30, Dell Thunderbolt 4 Dock  | all patterns present |
| Bid2 | contact_info | yes | B | found | Tamaira Hawkins, Email: thawkins@treasurer.state.md.us, Phon | all patterns present |
| Bid2 | company_name | yes | B | found | State of Maryland Treasurer's Office | all patterns present |
| Bid2 | product_specification | yes | A | found | Intel Core Ultra 5 125U processor (12 MB cache, 12 cores, 14 | all patterns present |
| Bid2 | bid_summary | yes | B | found | The State of Maryland Treasurer's Office is purchasing 30 De | all patterns present |
| Bid3 | bid_number | yes | C | found | 2025-003 | a pattern matched |
| Bid3 | title | NO | X | failed | null | expected a value, got null |
| Bid3 | due_date | yes | B | found | 2024-09-06 13:00 | all patterns present |
| Bid3 | pre_bid_meeting | yes | NF-1 | not_found | null | absent, as expected |
| Bid3 | bid_submission_type | yes | C | found | Proposals must be received prior to 1:00 PM on September 6,  | all patterns present |
| Bid3 | term_of_bid | yes | C | found | twelve (12) months | all patterns present |
| Bid3 | bid_bond_requirement | yes | C | found | 10% bid security in cash, a certified cashier’s check or fur | all patterns present |
| Bid3 | delivery_date | yes | C | found | October 31, 2024 | all patterns present |
| Bid3 | payment_terms | NO | NF-2 | not_found | null | expected a value, got null |
| Bid3 | additional_documentation | NO | X | failed | null | expected a value, got null |
| Bid3 | installation | yes | NF-1 | not_found | null | absent, as expected |
| Bid3 | mfg_for_registration | yes | C | found | Dell | found, but states the absence |
| Bid3 | contract_or_cooperative | NO | NF-1 | not_found | null | expected a value, got null |
| Bid3 | model_no | yes | C | found | Dell Chrome 3120 Chromebook | all items present |
| Bid3 | part_no | NO | NF-1 | not_found | null | expected a value, got null |
| Bid3 | product | NO | NF-1 | not_found | null | expected a value, got null |
| Bid3 | contact_info | NO | X | failed | null | expected a value, got null |
| Bid3 | company_name | yes | C | found | Delano Union School District | all patterns present |
| Bid3 | product_specification | yes | C | found | HP Fortis 11 inch G10 Chromebook,11.6 HD LED UWVA 250N TOP T | all patterns present |
| Bid3 | bid_summary | yes | B | found | The Delano Union School District (bid number 2025-003) seeks | all patterns present |
