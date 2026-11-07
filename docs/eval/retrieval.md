# Retrieval evaluation

Run 2026-11-07T11:05:17+00:00 at commit `41c15df` on `eval/retrieval_gold.yaml`: 42 questions (26 dev, 6 held out, 10 on an unseen bid), each question searched within its own bid.
Recall@k is the share of questions with a relevant passage in the top k (for `match: all` questions, the share of their passages found). MRR uses the first relevant hit within 10.

## All questions

| Config | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | Median ms |
|---|---|---|---|---|---|---|
| `dense` | 0.381 | 0.548 | 0.651 | 0.746 | 0.496 | 4 |
| `sparse` | 0.357 | 0.556 | 0.675 | 0.833 | 0.486 | 7 |
| `hybrid` | 0.429 | 0.667 | 0.698 | 0.833 | 0.559 | 11 |
| `hybrid_facts` | 0.532 | 0.794 | 0.817 | 0.873 | 0.681 | 19 |
| `hybrid_facts_rerank` | 0.675 | 0.889 | 0.897 | 0.921 | 0.788 | 5012 |

## Held-out questions only

| Config | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | Median ms |
|---|---|---|---|---|---|---|
| `dense` | 0.333 | 0.500 | 0.833 | 0.833 | 0.472 | 5 |
| `sparse` | 0.167 | 0.500 | 0.667 | 0.833 | 0.363 | 7 |
| `hybrid` | 0.500 | 0.833 | 0.833 | 0.833 | 0.667 | 10 |
| `hybrid_facts` | 0.500 | 0.667 | 0.833 | 0.833 | 0.617 | 19 |
| `hybrid_facts_rerank` | 0.667 | 0.833 | 0.833 | 1.000 | 0.739 | 5473 |

## Unseen bid only

Questions on a bid folder added after the system was built (a scanned RFP read by OCR, two addenda); nothing was tuned on it.

| Config | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | Median ms |
|---|---|---|---|---|---|---|
| `dense` | 0.200 | 0.200 | 0.300 | 0.400 | 0.233 | 5 |
| `sparse` | 0.100 | 0.300 | 0.500 | 0.700 | 0.237 | 7 |
| `hybrid` | 0.200 | 0.300 | 0.400 | 0.600 | 0.287 | 11 |
| `hybrid_facts` | 0.200 | 0.700 | 0.700 | 0.800 | 0.448 | 14 |
| `hybrid_facts_rerank` | 0.600 | 0.800 | 0.800 | 0.800 | 0.683 | 4470 |

## Configurations

- `dense`: bge-small embeddings only
- `sparse`: BM25 only (Qdrant sparse vectors with IDF), with synonym expansion
- `hybrid`: dense + BM25 + exact identifier matches, fused with RRF (k=60)
- `hybrid_facts`: hybrid plus dense and BM25 lists restricted to chunks with the fact labels the question routes to (the default)
- `hybrid_facts_rerank`: hybrid_facts, top 30 reranked by the configured cross-encoder (RFP_RERANK_MODEL, default BAAI/bge-reranker-v2-m3-int8)

## Per question, `hybrid_facts_rerank`

| Question | Split | First relevant rank | Top hit |
|---|---|---|---|
| b1-due-final: When is the proposal due now that the addenda have been issued? | dev | 1 | Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf p1 |
| b1-due-original: What was the original submission deadline in the RFP? | dev | 1 | JA-207652 Student and Staff Computing Devices FINAL.pdf p2 |
| b1-prebid: When is the pre-bid meeting and how do vendors attend? | dev | 2 | Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html p1 |
| b1-number: What is the solicitation number for this bid? | dev | 3 | JA-207652 Student and Staff Computing Devices FINAL.pdf p14 |
| b1-term: How long is the contract and can it be renewed? | dev | 2 | JA-207652 Student and Staff Computing Devices FINAL.pdf p2 |
| b1-bond: Does the bidder need to provide a bid bond? | dev | 2 | JA-207652 Student and Staff Computing Devices FINAL.pdf p9 |
| b1-install: What deployment or installation services must the vendor provide? | dev | 1 | JA-207652 Student and Staff Computing Devices FINAL.pdf p3-4 |
| b1-etching: Do monitors need to be laser etched? | dev | 1 | Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf p1 |
| b1-extension: Did the district agree to give vendors more time to respond? | dev | 1 | Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf p1 |
| b1-buyer: Who is the buyer for this solicitation and what is their email? | dev | 2 | JA-207652 Student and Staff Computing Devices FINAL.pdf p2-3 |
| b1-warranty-staff: What minimum warranty is required on staff laptops? | dev | 1 | JA-207652 Student and Staff Computing Devices FINAL.pdf p6 |
| b1-qty-chromebook: How many small touch Chromebooks does the district expect to buy? | dev | 2 | JA-207652 Student and Staff Computing Devices FINAL.pdf p34 |
| b1-form-1295: Is the certificate of interested parties form required with the response? | dev | 1 | Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf p4 |
| b1-mwbe-goal: What is the minority and women-owned business participation goal? | dev | not in top 10 | JA-207652 Student and Staff Computing Devices FINAL.pdf p53-54 |
| b1-price-change: How far in advance must a vendor request a price increase? | dev | 1 | JA-207652 Student and Staff Computing Devices FINAL.pdf p21 |
| b1-autopilot: Must Windows devices be enrolled in a management service before delivery? | dev | 1 | Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf p4 |
| b1-repair-time: How quickly must warranty repairs be completed? | heldout | 1 | JA-207652 Student and Staff Computing Devices FINAL.pdf p3-4 |
| b1-punchout: Does the vendor have to set up an online catalog connection with the district? | heldout | 10 | JA-207652 Student and Staff Computing Devices FINAL.pdf p21 |
| b1-references: How many customer references are needed? | heldout | 3 | JA-207652 Student and Staff Computing Devices FINAL.pdf p30 |
| b2-due: What is the closing date and time for the Dell laptop bid? | dev | 1 | Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1 |
| b2-affidavits: Which affidavits must the vendor submit? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p2 |
| b2-delivery: How soon after award must the laptops be delivered? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p2 |
| b2-warranty: What warranty coverage is required for the laptops? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p3 |
| b2-invoice: Where and when should invoices be sent? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p2 |
| b2-sku-cpu: What is the SKU for the Intel Core Ultra 5 processor? | dev | 1 | Dell_Laptop_Specs.pdf p1 |
| b2-dock: WD22TB4 | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p3 |
| b2-qty: How many laptops and docks are being purchased? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p3 |
| b2-eligibility: Which vendors are allowed to bid on this purchase order? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p1 |
| b2-questions: What is the deadline for submitting questions about the Dell laptop solicitation? | dev | 1 | PORFP_-_Dell_Laptop_Final.pdf p2 |
| b2-poc: Who is the agency point of contact and what is their phone number? | heldout | 1 | PORFP_-_Dell_Laptop_Final.pdf p3 |
| b2-submission: How must proposals be submitted, and are emailed bids accepted? | heldout | 1 | PORFP_-_Dell_Laptop_Final.pdf p1 |
| b2-memory: How much RAM does the quoted laptop configuration have? | heldout | 1 | Dell_Laptop_Specs.pdf p1 |
| b3-due: When are proposals due? | unseen | 2 | RFP 2025-003 Computer Equipment.pdf p15-17 |
| b3-bond: Do we need a bid bond or some other security, and how much? | unseen | 1 | RFP 2025-003 Computer Equipment Addendum 1.pdf p1 |
| b3-substitution: Was any substitute product approved? | unseen | 1 | RFP 2025-003 Computer Equipment Addendum 2.pdf p1 |
| b3-term: How long does the contract last? | unseen | 1 | RFP 2025-003 Computer Equipment.pdf p4-5 |
| b3-delivery: By what date must the equipment arrive? | unseen | 1 | RFP 2025-003 Computer Equipment.pdf p4-5 |
| b3-cooperative: Which purchasing contracts can vendors propose under? | unseen | not in top 10 | RFP 2025-003 Computer Equipment.pdf p34-35 |
| b3-spec: What processor and memory must the Chromebooks have? | unseen | 1 | RFP 2025-003 Computer Equipment.pdf p17-18 |
| b3-quantity: How many Chromebooks is the district buying? | unseen | 1 | RFP 2025-003 Computer Equipment.pdf p17-18 |
| b3-acknowledge: Do bidders have to return anything for the addenda? | unseen | not in top 10 | RFP 2025-003 Computer Equipment.pdf p6 |
| b3-contact: Who should questions be sent to, and by when? | unseen | 3 | RFP 2025-003 Computer Equipment.pdf p51-52 |

## Misses at 5, by configuration

- `dense`: b1-due-original (7), b1-number (>10), b1-term (7), b1-buyer (>10), b1-mwbe-goal (>10), b1-references (>10), b2-affidavits (4), b2-warranty (8), b3-due (>10), b3-bond (8), b3-substitution (>10), b3-term (>10), b3-cooperative (>10), b3-acknowledge (>10), b3-contact (>10)
- `sparse`: b1-due-original (7), b1-bond (7), b1-extension (>10), b1-buyer (>10), b1-mwbe-goal (>10), b1-punchout (7), b1-references (>10), b2-affidavits (3), b2-warranty (8), b3-due (8), b3-term (>10), b3-delivery (8), b3-cooperative (>10), b3-acknowledge (>10)
- `hybrid`: b1-number (9), b1-extension (>10), b1-buyer (7), b1-mwbe-goal (>10), b1-references (>10), b2-affidavits (4), b2-warranty (8), b3-due (>10), b3-substitution (7), b3-term (>10), b3-cooperative (>10), b3-acknowledge (>10), b3-contact (7)
- `hybrid_facts`: b1-number (9), b1-extension (>10), b1-mwbe-goal (>10), b1-references (>10), b2-affidavits (1), b3-substitution (7), b3-term (>10), b3-acknowledge (>10)
- `hybrid_facts_rerank`: b1-mwbe-goal (>10), b1-punchout (10), b2-affidavits (1), b3-cooperative (>10), b3-acknowledge (>10)
