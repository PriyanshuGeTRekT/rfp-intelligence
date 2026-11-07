# Extraction evaluation

Results from `outputs` scored against `eval/extraction_gold.yaml`: 60 fields, accuracy 85.0%.

| Bid | Accuracy |
|---|---|
| Bid1 | 90.0% |
| Bid2 | 100.0% |
| Bid3 | 65.0% |

## Calibration: accuracy per confidence tier

A well-ordered table has accuracy falling as the tier falls. Tiers with few fields say little; the counts are shown for that reason.

| Tier | Fields | Correct | Accuracy |
|---|---|---|---|
| A | 9 | 8 | 89% |
| B | 25 | 24 | 96% |
| C | 13 | 10 | 77% |
| NF-1 | 10 | 8 | 80% |
| NF-2 | 3 | 1 | 33% |

## Per field

| Bid | Field | Pass | Tier | Status | Value | Reason |
|---|---|---|---|---|---|---|
| Bid1 | bid_number | yes | B | found | JA-207652 | a pattern matched |
| Bid1 | title | yes | B | found | Student and Staff Computing Devices | all patterns present |
| Bid1 | due_date | yes | A | found | 2024-07-09 14:00 CDT | instant matches |
| Bid1 | pre_bid_meeting | yes | A | found | 2024-06-10 14:00 CST via TEAMS video conference (link: https | instant matches |
| Bid1 | bid_submission_type | yes | B | found | Responses must be submitted online via the iSupplier portal  | a pattern matched |
| Bid1 | term_of_bid | yes | B | found | 3-year initial term with two one-year extensions, not to exc | all patterns present |
| Bid1 | bid_bond_requirement | yes | NF-1 | not_found | null | absent, as expected |
| Bid1 | delivery_date | yes | NF-2 | not_found | null | absent, as expected |
| Bid1 | payment_terms | yes | B | found | within 10 days of receiving payment from the district | found, but states the absence |
| Bid1 | additional_documentation | NO | A | found | INTERLOCAL AGREEMENT ("Rider") CONSENT FORM ; FORM 1295 - CE | missing items ['M/?WBE|minority', 'W-?9'] |
| Bid1 | installation | yes | A | found | White glove deployment services (asset decal, reporting, etc | all patterns present |
| Bid1 | mfg_for_registration | yes | B | found | OEM | found, but states the absence |
| Bid1 | contract_or_cooperative | yes | B | found | Educational Purchasing Cooperative of North Texas (EPCNT) In | found, but states the absence |
| Bid1 | model_no | yes | NF-1 | not_found | null | absent, as expected |
| Bid1 | part_no | yes | NF-1 | not_found | null | absent, as expected |
| Bid1 | product | NO | B | found | Student Tablet - 50,000 | missing ['Chromebook', 'laptop'] |
| Bid1 | contact_info | yes | B | found | JASMINE ALZATE, Buyer, JALZATE@dallasisd.org, 972.925.3700 | a pattern matched |
| Bid1 | company_name | yes | B | found | Dallas Independent School District | all patterns present |
| Bid1 | product_specification | yes | A | found | Student Windows – Screen Resolution 1920-1080 Non-Touch, Stu | all patterns present |
| Bid1 | bid_summary | yes | B | found | Dallas Independent School District is seeking to purchase 50 | all patterns present |
| Bid2 | bid_number | yes | B | found | BPM044557 | a pattern matched |
| Bid2 | title | yes | B | found | Dell Laptops w/Extended Warranty | all patterns present |
| Bid2 | due_date | yes | C | found | 2024-06-10 14:00 EDT | instant matches |
| Bid2 | pre_bid_meeting | yes | NF-1 | not_found | null | absent, as expected |
| Bid2 | bid_submission_type | yes | B | found | Electronic submission through eMMA portal; bids not accepted | all patterns present |
| Bid2 | term_of_bid | yes | A | found | Fixed Price; pricing valid for thirty days | a pattern matched |
| Bid2 | bid_bond_requirement | yes | NF-1 | not_found | null | absent, as expected |
| Bid2 | delivery_date | yes | B | found | within 45 days of Award | all patterns present |
| Bid2 | payment_terms | yes | B | found | Invoices must be emailed to STOaccountspayable@treasurer.sta | all patterns present |
| Bid2 | additional_documentation | yes | A | found | MERCURY CONTENT INFORMATION ; Proposal Affidavit | all items present |
| Bid2 | installation | yes | NF-1 | not_found | null | absent, as expected |
| Bid2 | mfg_for_registration | yes | B | found | Dell | all patterns present |
| Bid2 | contract_or_cooperative | yes | B | found | Master Contract: Desktop, Laptop and Tablet 2015 Master Cont | a pattern matched |
| Bid2 | model_no | yes | B | found | Dell Latitude 5550 ; Dell Thunderbolt 4 Dock – WD22TB4 | all items present |
| Bid2 | part_no | yes | B | found | 210-BLYZ ; 379-BFNZ ; 619-ARSB ; 658-BCSB ; 338-CNRG ; 338-C | all items present |
| Bid2 | product | yes | B | found | SI# CC7802 Dell Latitude 5550 (Qty: 30), Dell Thunderbolt 4  | all patterns present |
| Bid2 | contact_info | yes | A | found | Tamaira Hawkins, Phone: 410-260-7533, Email: thawkins@treasu | all patterns present |
| Bid2 | company_name | yes | B | found | State of Maryland Treasurer's Office | all patterns present |
| Bid2 | product_specification | yes | A | found | Intel Core Ultra 5 125U processor (12 MB cache, 12 cores, 14 | all patterns present |
| Bid2 | bid_summary | yes | B | found | The State of Maryland Treasurer's Office (bid_number BPM0445 | all patterns present |
| Bid3 | bid_number | yes | C | found | 2025-003 | a pattern matched |
| Bid3 | title | NO | NF-1 | not_found | null | expected a value, got null |
| Bid3 | due_date | yes | B | found | 2024-09-06 13:00 | all patterns present |
| Bid3 | pre_bid_meeting | yes | NF-1 | not_found | null | absent, as expected |
| Bid3 | bid_submission_type | NO | NF-2 | not_found | null | expected a value, got null |
| Bid3 | term_of_bid | yes | C | found | twelve (12) months | all patterns present |
| Bid3 | bid_bond_requirement | yes | C | found | 10% bid security in cash, a certified cashier’s check or fur | all patterns present |
| Bid3 | delivery_date | NO | C | found | November30,2024 | missing ['October 31, 2024|2024-10-31'] |
| Bid3 | payment_terms | NO | NF-2 | not_found | null | expected a value, got null |
| Bid3 | additional_documentation | NO | C | found | Instructions to Bidders ; Bid Form ; Substitution Listing ;  | missing items ['Non-?Collusion', 'Addend'] |
| Bid3 | installation | yes | NF-1 | not_found | null | absent, as expected |
| Bid3 | mfg_for_registration | yes | C | found | Dell Chrome 3120 Chromebook* (Latest Model) or functionally  | found, but states the absence |
| Bid3 | contract_or_cooperative | NO | C | found | Purchase Contract | none of ['NASPO', 'CMAS', 'WSCA', 'CALNET'] matched |
| Bid3 | model_no | yes | C | found | Dell Chrome 3120 Chromebook ; GOOGLE CHROME OS MANAGEMENT CO | all items present |
| Bid3 | part_no | NO | NF-1 | not_found | null | expected a value, got null |
| Bid3 | product | yes | C | found | Dell Chrome 3120 Chromebook* (Latest Model) or functionally  | all patterns present |
| Bid3 | contact_info | yes | C | found | Sandra Rivera, Assistant Superintendent of Business, email:  | a pattern matched |
| Bid3 | company_name | yes | C | found | Delano Union School District | all patterns present |
| Bid3 | product_specification | yes | C | found | HP Fortis 11 inch G10 Chromebook,11.6 HD LED UWVA 250N TOP T | all patterns present |
| Bid3 | bid_summary | yes | B | found | Bid number 2025-003 from Delano Union School District seeks  | all patterns present |
