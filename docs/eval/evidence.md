# Evidence reach

Whether each expected value (from `eval/extraction_gold.yaml`) reaches the extraction
prompt that asks for its field, with a scripted model and no API calls
(`uv run rfp eval evidence`). A value that is missing here cannot be extracted by any
model: the cause is retrieval or the prompt budget, not the model.

**51 of 54** fields asked of the model have their expected text in the prompt.

| Bid | Field | Reached | Missing | Passages | Prompt tokens |
|---|---|---|---|---|---|
| Bid1 | bid_number | yes |  | 6 | 2798 |
| Bid1 | title | yes |  | 6 | 2798 |
| Bid1 | due_date | not asked | | | |
| Bid1 | pre_bid_meeting | yes |  | 6 | 2798 |
| Bid1 | bid_submission_type | yes |  | 5 | 2533 |
| Bid1 | term_of_bid | yes |  | 4 | 2730 |
| Bid1 | bid_bond_requirement | yes |  | 4 | 2730 |
| Bid1 | delivery_date | yes |  | 9 | 2445 |
| Bid1 | payment_terms | yes |  | 4 | 2730 |
| Bid1 | additional_documentation | yes |  | 7 | 2746 |
| Bid1 | installation | yes |  | 10 | 2701 |
| Bid1 | mfg_for_registration | yes |  | 10 | 2616 |
| Bid1 | contract_or_cooperative | yes |  | 7 | 2746 |
| Bid1 | model_no | yes |  | 7 | 2688 |
| Bid1 | part_no | yes |  | 7 | 2688 |
| Bid1 | product | yes |  | 7 | 2688 |
| Bid1 | contact_info | yes |  | 10 | 2701 |
| Bid1 | company_name | yes |  | 10 | 2701 |
| Bid1 | product_specification | yes |  | 10 | 2616 |
| Bid1 | bid_summary | not asked | | | |
| Bid2 | bid_number | yes |  | 5 | 2676 |
| Bid2 | title | yes |  | 5 | 2676 |
| Bid2 | due_date | not asked | | | |
| Bid2 | pre_bid_meeting | yes |  | 5 | 2676 |
| Bid2 | bid_submission_type | yes |  | 6 | 2535 |
| Bid2 | term_of_bid | yes |  | 6 | 2654 |
| Bid2 | bid_bond_requirement | yes |  | 6 | 2654 |
| Bid2 | delivery_date | yes |  | 6 | 2469 |
| Bid2 | payment_terms | yes |  | 6 | 2654 |
| Bid2 | additional_documentation | yes |  | 9 | 2678 |
| Bid2 | installation | yes |  | 8 | 2736 |
| Bid2 | mfg_for_registration | yes |  | 9 | 2699 |
| Bid2 | contract_or_cooperative | yes |  | 9 | 2678 |
| Bid2 | model_no | yes |  | 6 | 2717 |
| Bid2 | part_no | yes |  | 6 | 2717 |
| Bid2 | product | yes |  | 6 | 2717 |
| Bid2 | contact_info | yes |  | 8 | 2736 |
| Bid2 | company_name | yes |  | 8 | 2736 |
| Bid2 | product_specification | yes |  | 9 | 2699 |
| Bid2 | bid_summary | not asked | | | |
| Bid3 | bid_number | yes |  | 6 | 2711 |
| Bid3 | title | yes |  | 6 | 2711 |
| Bid3 | due_date | not asked | | | |
| Bid3 | pre_bid_meeting | yes |  | 6 | 2711 |
| Bid3 | bid_submission_type | yes |  | 4 | 2588 |
| Bid3 | term_of_bid | yes |  | 3 | 2739 |
| Bid3 | bid_bond_requirement | yes |  | 3 | 2739 |
| Bid3 | delivery_date | yes |  | 6 | 2733 |
| Bid3 | payment_terms | yes |  | 3 | 2739 |
| Bid3 | additional_documentation | **no** | `Non-?Collusion` | 8 | 2694 |
| Bid3 | installation | yes |  | 7 | 2748 |
| Bid3 | mfg_for_registration | yes |  | 5 | 2587 |
| Bid3 | contract_or_cooperative | **no** | `NASPO`, `CMAS`, `WSCA`, `CALNET` | 8 | 2694 |
| Bid3 | model_no | yes |  | 4 | 2688 |
| Bid3 | part_no | **no** | `9R3B5UT` | 4 | 2688 |
| Bid3 | product | yes |  | 4 | 2688 |
| Bid3 | contact_info | yes |  | 7 | 2748 |
| Bid3 | company_name | yes |  | 7 | 2748 |
| Bid3 | product_specification | yes |  | 5 | 2587 |
| Bid3 | bid_summary | not asked | | | |
