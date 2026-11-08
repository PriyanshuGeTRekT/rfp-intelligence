# Trace 20261108T115449Z-2c640f

193 spans, 14 with model usage, estimated cost $0.0122, longest root span 676.9 s.

```
agent.run (676.88s)
  agent.mode=extract
  llm.cost_usd=0.012214
  rfp.bid_id=Bid2
  rfp.run_id=20261108T115449Z-2c640f
  LangGraph (676.87s)
    plan (2ms)
      route (0ms)
    ingest (12ms)
    reconcile (11ms)
      RunnableCallable (0ms)
    retrieve (6.44s)
    retrieve (2.01s)
    retrieve (8.11s)
    retrieve (20.15s)
    retrieve (21.91s)
    retrieve (6.11s)
    retrieve (5.56s)
    retrieve (783ms)
    extract (2.54s)
    extract (59.93s)
    extract (60.09s)
    extract (60.77s)
    extract (67.04s)
    extract (54.27s)
    extract (58.55s)
    extract (58.78s)
    validate (16ms)
      RunnableCallable (0ms)
    retrieve (18.08s)
    retrieve (6.51s)
    retrieve (6.22s)
    extract (29.71s)
    extract (59.82s)
    extract (62.33s)
    validate (10ms)
      RunnableCallable (0ms)
    report (1.01s)
  agent.plan (0ms)
    agent.input={"bid_id":"Bid2","folder":"data\\bids\\Bid2","question":null}
    agent.mode=extract
    agent.output=[{"agent":"ingest","task":"index data\\bids\\Bid2 (new or changed files only)"},{"agent":"reconcile","task":"read addenda into change events; resolve date fi...
  agent.ingest (12ms)
    agent.input=data\bids\Bid2
    agent.output=[["Contract_Affidavit.pdf","affidavit"],["Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html","bid_page"],["Dell_Laptop_Specs.pdf"...
    rfp.bid_id=Bid2
    index.folder (9ms)
      index.added=0
      index.changed=0
      index.failed=0
      index.removed=0
      index.unchanged=5
      rfp.bid_id=Bid2
  agent.reconcile (10ms)
    agent.events=0
    agent.output={"due_date":"2024-06-10 14:00 EDT"}
  agent.retrieve.identity_dates (6.44s)
    agent.input={"batch":"identity_dates","fields":["bid_number","title","pre_bid_meeting"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"bid_number":["0add078209cc59571febe7ad","dc914406e49b3a21d4a75381","8b8ea66640ba1b48d06e8df6","18474d86b0e3cd8760b03821","8ac9bfa06f088876067a4e5b","7447c4...
    agent.reranked=true
    search (18ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=18.3
      search.lists=["dense:30", "bm25:9"]
      search.query=Bid Number
      search.top_scores=[0.0325, 0.0318, 0.0318, 0.031, 0.0308]
    search (16ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.8
      search.lists=["dense:30", "bm25:9"]
      search.query=solicitation number
      search.top_scores=[0.032, 0.032, 0.0315, 0.0313, 0.0308]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.7
      search.lists=["dense:30", "bm25:9"]
      search.query=bid number
      search.top_scores=[0.0325, 0.0318, 0.0318, 0.031, 0.0308]
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.4
      search.lists=["dense:30", "bm25:12"]
      search.query=RFP number reference number
      search.top_scores=[0.0323, 0.032, 0.0313, 0.0311, 0.031]
    rerank (2.21s)
      search.query=["Bid Number: The number the issuing agency assigned to this solicitation (RFP, RFQ, IFB, PORFP or sourcing event number). If the portal and the document giv...
      search.reranked=10
    search (16ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=16.3
      search.lists=["dense:30", "bm25:5"]
      search.query=Title
      search.top_scores=[0.0325, 0.0323, 0.0306, 0.0296, 0.0279]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.8
      search.lists=["dense:30", "bm25:9"]
      search.query=solicitation title
      search.top_scores=[0.0318, 0.0313, 0.031, 0.0306, 0.0299]
    search (11ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=10.5
      search.lists=["dense:30", "bm25:20"]
      search.query=request for proposal title
      search.top_scores=[0.0313, 0.0313, 0.031, 0.0297, 0.0297]
    rerank (2.00s)
      search.query=["Title: The solicitation's title as the agency states it, without the number."]
      search.reranked=10
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["pre_bid"]
      search.identifiers=[]
      search.latency_ms=28.6
      search.lists=["dense:30", "bm25:5", "facts_dense:0", "facts_bm25:0"]
      search.query=Pre Bid Meeting
      search.top_scores=[0.0318, 0.0315, 0.0301, 0.0292, 0.0282]
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["pre_bid"]
      search.identifiers=[]
      search.latency_ms=30.1
      search.lists=["dense:30", "bm25:15", "facts_dense:0", "facts_bm25:0"]
      search.query=pre-bid meeting
      search.top_scores=[0.0318, 0.031, 0.0308, 0.0304, 0.0299]
    search (78ms)
      search.config=hybrid_facts
      search.fact_types=["pre_bid"]
      search.identifiers=[]
      search.latency_ms=78.3
      search.lists=["dense:30", "bm25:15", "facts_dense:0", "facts_bm25:0"]
      search.query=pre-proposal conference
      search.top_scores=[0.032, 0.031, 0.0308, 0.0302, 0.0301]
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["pre_bid"]
      search.identifiers=[]
      search.latency_ms=29.7
      search.lists=["dense:30", "bm25:15", "facts_dense:0", "facts_bm25:0"]
      search.query=site visit
      search.top_scores=[0.0323, 0.0313, 0.0308, 0.0299, 0.0292]
    rerank (1.93s)
      search.query=["Pre Bid Meeting: Date, time, place or link of any pre-bid or pre-proposal meeting or site visit, and whether attendance is mandatory. \"None\" when the doc...
      search.reranked=9
  agent.retrieve.identity_dates/2 (2.01s)
    agent.input={"batch":"identity_dates/2","fields":["bid_submission_type"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"bid_submission_type":["0add078209cc59571febe7ad","b7931cc32d11e3596efc53af","57b478dcce95481a66ae2d49","44ada9f79ed19336fb1e3e9f","dc914406e49b3a21d4a75381...
    agent.reranked=true
    search (31ms)
      search.config=hybrid_facts
      search.fact_types=["submission_method"]
      search.identifiers=[]
      search.latency_ms=30.8
      search.lists=["dense:30", "bm25:12", "facts_dense:3", "facts_bm25:3"]
      search.query=Bid Submission Type
      search.top_scores=[0.0653, 0.0633, 0.0619, 0.0325, 0.0297]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["submission_method"]
      search.identifiers=[]
      search.latency_ms=28.1
      search.lists=["dense:30", "bm25:15", "facts_dense:3", "facts_bm25:3"]
      search.query=how to submit proposals
      search.top_scores=[0.0641, 0.064, 0.0628, 0.032, 0.0296]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["submission_method"]
      search.identifiers=[]
      search.latency_ms=28.4
      search.lists=["dense:30", "bm25:8", "facts_dense:3", "facts_bm25:3"]
      search.query=electronic submission portal
      search.top_scores=[0.065, 0.0641, 0.0623, 0.0318, 0.0291]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["submission_method"]
      search.identifiers=[]
      search.latency_ms=28.9
      search.lists=["dense:30", "bm25:10", "facts_dense:3", "facts_bm25:3"]
      search.query=sealed bids hard copy
      search.top_scores=[0.0636, 0.0633, 0.0621, 0.0315, 0.0301]
    rerank (1.88s)
      search.query=["Bid Submission Type: How responses must be submitted: electronic portal (which one), email, sealed hard copy, number of copies; and what is not accepted."]
      search.reranked=9
  agent.retrieve.commercial_legal (8.11s)
    agent.input={"batch":"commercial_legal","fields":["term_of_bid","bid_bond_requirement","payment_terms"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"term_of_bid":["0add078209cc59571febe7ad","57b478dcce95481a66ae2d49","cfb4071f1d12743e1f27e173","dc914406e49b3a21d4a75381","dbedc9e5039fc49d0bb82c8a","43eee...
    agent.reranked=true
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["term_renewal"]
      search.identifiers=[]
      search.latency_ms=30.0
      search.lists=["dense:30", "bm25:25", "facts_dense:2", "facts_bm25:2"]
      search.query=Term of Bid
      search.top_scores=[0.0631, 0.0588, 0.0325, 0.0306, 0.0304]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["term_renewal"]
      search.identifiers=[]
      search.latency_ms=28.1
      search.lists=["dense:30", "bm25:24", "facts_dense:2", "facts_bm25:2"]
      search.query=contract term renewal options
      search.top_scores=[0.0646, 0.0583, 0.0323, 0.032, 0.031]
    search (11ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=11.4
      search.lists=["dense:30", "bm25:20"]
      search.query=length of contract
      search.top_scores=[0.0325, 0.032, 0.0318, 0.0306, 0.0299]
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["deadline"]
      search.identifiers=[]
      search.latency_ms=30.3
      search.lists=["dense:30", "bm25:28", "facts_dense:2", "facts_bm25:2"]
      search.query=proposals quotes must remain valid days after due date
      search.top_scores=[0.0612, 0.0594, 0.0325, 0.0318, 0.0318]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["pricing"]
      search.identifiers=[]
      search.latency_ms=28.5
      search.lists=["dense:30", "bm25:19", "facts_dense:1", "facts_bm25:1"]
      search.query=procurement type fixed price purchase order
      search.top_scores=[0.0643, 0.0328, 0.0313, 0.0313, 0.0312]
    rerank (3.16s)
      search.query=["Term of Bid: Contract term and renewal options. When no term is stated, report what the solicitation says instead: the procurement type (for example a fixe...
      search.reranked=13
    search (31ms)
      search.config=hybrid_facts
      search.fact_types=["bond_insurance"]
      search.identifiers=[]
      search.latency_ms=31.1
      search.lists=["dense:30", "bm25:14", "facts_dense:0", "facts_bm25:0"]
      search.query=Bid Bond Requirement
      search.top_scores=[0.032, 0.0318, 0.0313, 0.0311, 0.0306]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["bond_insurance"]
      search.identifiers=[]
      search.latency_ms=28.7
      search.lists=["dense:30", "bm25:17", "facts_dense:0", "facts_bm25:0"]
      search.query=bid bond required amount
      search.top_scores=[0.032, 0.0313, 0.031, 0.0308, 0.0306]
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["bond_insurance"]
      search.identifiers=[]
      search.latency_ms=29.5
      search.lists=["dense:30", "bm25:18", "facts_dense:0", "facts_bm25:0"]
      search.query=bid security guarantee
      search.top_scores=[0.0323, 0.032, 0.0301, 0.0297, 0.0296]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["bond_insurance"]
      search.identifiers=[]
      search.latency_ms=29.5
      search.lists=["dense:30", "bm25:17", "facts_dense:0", "facts_bm25:0"]
      search.query=performance bond insurance
      search.top_scores=[0.0328, 0.0308, 0.0308, 0.0304, 0.0299]
    rerank (2.53s)
      search.query=["Bid Bond Requirement: Whether a bid bond, bid security or guarantee is required, and its amount or percentage. \"Not required\" only when a passage says so...
      search.reranked=11
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["payment_invoice"]
      search.identifiers=[]
      search.latency_ms=30.4
      search.lists=["dense:30", "bm25:15", "facts_dense:2", "facts_bm25:2"]
      search.query=Payment Terms
      search.top_scores=[0.065, 0.0633, 0.0328, 0.0315, 0.0301]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["payment_invoice"]
      search.identifiers=[]
      search.latency_ms=28.6
      search.lists=["dense:30", "bm25:16", "facts_dense:2", "facts_bm25:2"]
      search.query=payment terms net days
      search.top_scores=[0.0653, 0.0638, 0.0323, 0.0315, 0.0308]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["payment_invoice", "submission_method"]
      search.identifiers=[]
      search.latency_ms=29.1
      search.lists=["dense:30", "bm25:18", "facts_dense:4", "facts_bm25:4"]
      search.query=invoice submission payment
      search.top_scores=[0.0653, 0.0638, 0.0615, 0.0592, 0.0308]
    search (26ms)
      search.config=hybrid_facts
      search.fact_types=["payment_invoice"]
      search.identifiers=[]
      search.latency_ms=26.0
      search.lists=["dense:30", "bm25:15", "facts_dense:2", "facts_bm25:2"]
      search.query=prompt payment
      search.top_scores=[0.0643, 0.0634, 0.0311, 0.0308, 0.0292]
    rerank (2.05s)
      search.query=["Payment Terms: When and how the agency pays the vendor (Net days, invoicing rules, prompt payment). Not the vendor's own credit terms, and not subcontracto...
      search.reranked=9
  agent.retrieve.commercial_legal/2 (20.15s)
    agent.input={"batch":"commercial_legal/2","fields":["contract_or_cooperative","additional_documentation"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"contract_or_cooperative":["d9d0d345bae717d021315a5d","0add078209cc59571febe7ad","2870d3578d93bb7d11476833","18474d86b0e3cd8760b03821","57b478dcce95481a66ae...
    agent.reranked=true
    search (18ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=18.1
      search.lists=["dense:30", "bm25:24"]
      search.query=Contract or Cooperative to use
      search.top_scores=[0.0318, 0.0313, 0.0306, 0.0305, 0.03]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["contact"]
      search.identifiers=[]
      search.latency_ms=28.6
      search.lists=["dense:30", "bm25:21", "facts_dense:6", "facts_bm25:4"]
      search.query=master contract cooperative purchasing
      search.top_scores=[0.0653, 0.0622, 0.0616, 0.0616, 0.0318]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["term_renewal"]
      search.identifiers=[]
      search.latency_ms=28.1
      search.lists=["dense:30", "bm25:23", "facts_dense:2", "facts_bm25:2"]
      search.query=piggyback cooperative agreement
      search.top_scores=[0.0616, 0.057, 0.0325, 0.0308, 0.0305]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.5
      search.lists=["dense:30", "bm25:21"]
      search.query=contract vehicle
      search.top_scores=[0.032, 0.031, 0.0297, 0.0296, 0.0292]
    rerank (2.59s)
      search.query=["Contract or Cooperative to use: The contract vehicle or purchasing cooperative the purchase is made under (a master contract, a cooperative, piggyback elig...
      search.reranked=12
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=12.8
      search.lists=["dense:30", "bm25:15"]
      search.query=Any Additional Documentation Required
      search.top_scores=[0.0311, 0.0306, 0.0296, 0.0289, 0.0288]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.6
      search.lists=["dense:30", "bm25:18"]
      search.query=forms required with proposal
      search.top_scores=[0.032, 0.0312, 0.0311, 0.0311, 0.0299]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["submission_method"]
      search.identifiers=[]
      search.latency_ms=29.1
      search.lists=["dense:30", "bm25:19", "facts_dense:3", "facts_bm25:3"]
      search.query=affidavits certifications to submit
      search.top_scores=[0.0608, 0.0597, 0.059, 0.0325, 0.0318]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.8
      search.lists=["dense:30", "bm25:7"]
      search.query=acknowledge addendum signed
      search.top_scores=[0.032, 0.031, 0.0308, 0.0294, 0.029]
    search (11ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=11.3
      search.lists=["dense:30", "bm25:13"]
      search.query=references required
      search.top_scores=[0.0304, 0.0304, 0.0303, 0.0301, 0.03]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["submission_method"]
      search.identifiers=[]
      search.latency_ms=27.9
      search.lists=["dense:30", "bm25:15", "facts_dense:3", "facts_bm25:3"]
      search.query=attachments to complete and attach to the submission
      search.top_scores=[0.0638, 0.0625, 0.0611, 0.0318, 0.031]
    search (12ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=12.4
      search.lists=["dense:11", "bm25:4"]
      search.query=Any Additional Documentation Required
      search.top_scores=[0.0323, 0.0318, 0.0318, 0.0318, 0.0159]
    rerank (17.34s)
      search.query=["Any Additional Documentation Required: Forms, affidavits, certifications, references and acknowledgements that must be submitted with the response or on aw...
      search.reranked=14
  agent.retrieve.product_specs (21.90s)
    agent.input={"batch":"product_specs","fields":["product","model_no","part_no"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"product":["2870d3578d93bb7d11476833","18474d86b0e3cd8760b03821","cfb4071f1d12743e1f27e173","57b478dcce95481a66ae2d49","44ada9f79ed19336fb1e3e9f","0add07820...
    agent.reranked=true
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.3
      search.lists=["dense:30", "bm25:9"]
      search.query=Product
      search.top_scores=[0.0328, 0.032, 0.0313, 0.0305, 0.0302]
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.0
      search.lists=["dense:30", "bm25:16"]
      search.query=products to be purchased quantity
      search.top_scores=[0.0323, 0.032, 0.0318, 0.0313, 0.0304]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.0
      search.lists=["dense:30", "bm25:6"]
      search.query=scope of work devices
      search.top_scores=[0.0328, 0.032, 0.0313, 0.0305, 0.0303]
    search (23ms)
      search.config=hybrid_facts
      search.fact_types=["pricing"]
      search.identifiers=[]
      search.latency_ms=22.9
      search.lists=["dense:30", "bm25:6", "facts_dense:1", "facts_bm25:1"]
      search.query=price schedule line items
      search.top_scores=[0.0648, 0.0325, 0.0318, 0.0299, 0.0299]
    search (9ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.5
      search.lists=["dense:30", "bm25:4"]
      search.query=estimated quantity per tier
      search.top_scores=[0.0318, 0.0313, 0.0312, 0.0304, 0.0164]
    rerank (12.98s)
      search.query=["Product: The goods or services being bought, with quantities when stated. When the solicitation groups products into categories or tiers (in its requiremen...
      search.reranked=13
    search (17ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=17.2
      search.lists=["dense:30", "bm25:0"]
      search.query=Model_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.1
      search.lists=["dense:30", "bm25:11"]
      search.query=model number
      search.top_scores=[0.032, 0.0318, 0.0318, 0.0301, 0.0299]
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.4
      search.lists=["dense:30", "bm25:17"]
      search.query=product model required
      search.top_scores=[0.0328, 0.0318, 0.0308, 0.0302, 0.0299]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.0
      search.lists=["dense:30", "bm25:9"]
      search.query=brand and model
      search.top_scores=[0.0323, 0.0315, 0.0315, 0.0309, 0.0301]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.7
      search.lists=["dense:7", "bm25:0"]
      search.query=Model_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    rerank (4.16s)
      search.query=["Model_no: Manufacturer model names and numbers the documents require or quote, as the manufacturer markets them (a product line and number, for example a l...
      search.reranked=15
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.5
      search.lists=["dense:30", "bm25:0"]
      search.query=Part_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.4
      search.lists=["dense:30", "bm25:11"]
      search.query=part number SKU
      search.top_scores=[0.0323, 0.0323, 0.0315, 0.0303, 0.0299]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.1
      search.lists=["dense:30", "bm25:22"]
      search.query=configuration SKU list
      search.top_scores=[0.0318, 0.0318, 0.0311, 0.0304, 0.0299]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.9
      search.lists=["dense:30", "bm25:11"]
      search.query=item part numbers
      search.top_scores=[0.0323, 0.0306, 0.0304, 0.0304, 0.0301]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=10.4
      search.lists=["dense:7", "bm25:0"]
      search.query=Part_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    rerank (4.53s)
      search.query=["Part_no: Part numbers or SKUs listed in the documents (quotes, configurations, line items). Return not_found when none are listed."]
      search.reranked=19
  agent.retrieve.product_specs/2 (6.11s)
    agent.input={"batch":"product_specs/2","fields":["mfg_for_registration","product_specification"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"mfg_for_registration":["0add078209cc59571febe7ad","18474d86b0e3cd8760b03821","cfb4071f1d12743e1f27e173","57b478dcce95481a66ae2d49","2aa9264be1444770c32ad14...
    agent.reranked=true
    search (18ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=17.5
      search.lists=["dense:30", "bm25:8"]
      search.query=MFG for Registration
      search.top_scores=[0.0318, 0.0306, 0.0303, 0.0287, 0.0286]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.7
      search.lists=["dense:30", "bm25:13"]
      search.query=manufacturer OEM required
      search.top_scores=[0.0328, 0.031, 0.031, 0.0308, 0.0301]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["warranty"]
      search.identifiers=[]
      search.latency_ms=28.9
      search.lists=["dense:30", "bm25:16", "facts_dense:1", "facts_bm25:1"]
      search.query=manufacturer warranty registration
      search.top_scores=[0.0656, 0.0311, 0.031, 0.0298, 0.0297]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.8
      search.lists=["dense:30", "bm25:7"]
      search.query=brand
      search.top_scores=[0.0323, 0.0318, 0.0318, 0.0295, 0.0289]
    rerank (2.49s)
      search.query=["MFG for Registration: The manufacturer the products are registered with or must come from (OEM requirements, manufacturer warranty registration)."]
      search.reranked=12
    search (17ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=16.7
      search.lists=["dense:30", "bm25:18"]
      search.query=Product Specification
      search.top_scores=[0.0313, 0.0311, 0.0311, 0.0308, 0.0302]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.2
      search.lists=["dense:30", "bm25:18"]
      search.query=minimum specifications requirements
      search.top_scores=[0.0303, 0.0303, 0.0303, 0.0302, 0.0302]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.2
      search.lists=["dense:30", "bm25:1"]
      search.query=processor memory storage display
      search.top_scores=[0.0328, 0.0161, 0.0159, 0.0156, 0.0154]
    search (22ms)
      search.config=hybrid_facts
      search.fact_types=["warranty"]
      search.identifiers=[]
      search.latency_ms=21.9
      search.lists=["dense:30", "bm25:24", "facts_dense:1", "facts_bm25:1"]
      search.query=technical specifications warranty
      search.top_scores=[0.0643, 0.032, 0.0306, 0.03, 0.0299]
    search (9ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.1
      search.lists=["dense:7", "bm25:7"]
      search.query=Product Specification
      search.top_scores=[0.0325, 0.0325, 0.0318, 0.0308, 0.0308]
    rerank (3.46s)
      search.query=["Product Specification: The key technical specifications or minimum requirements, one item per specification (processor, memory, storage, display, battery, ...
      search.reranked=13
  agent.retrieve.parties_logistics (5.56s)
    agent.input={"batch":"parties_logistics","fields":["company_name","contact_info","installation"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"company_name":["8b8ea66640ba1b48d06e8df6","0add078209cc59571febe7ad","18474d86b0e3cd8760b03821","dc914406e49b3a21d4a75381","57b478dcce95481a66ae2d49","2b19...
    agent.reranked=true
    search (17ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=16.5
      search.lists=["dense:30", "bm25:0"]
      search.query=company_name
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.9
      search.lists=["dense:30", "bm25:5"]
      search.query=issuing organization
      search.top_scores=[0.032, 0.0299, 0.0289, 0.0279, 0.0274]
    search (27ms)
      search.config=hybrid_facts
      search.fact_types=["contact"]
      search.identifiers=[]
      search.latency_ms=26.8
      search.lists=["dense:30", "bm25:19", "facts_dense:6", "facts_bm25:4"]
      search.query=agency name purchasing department
      search.top_scores=[0.0653, 0.0643, 0.063, 0.0613, 0.032]
    rerank (2.23s)
      search.query=["company_name: The issuing agency or organisation (the buyer), not a vendor or manufacturer."]
      search.reranked=11
    search (23ms)
      search.config=hybrid_facts
      search.fact_types=["contact"]
      search.identifiers=[]
      search.latency_ms=22.9
      search.lists=["dense:30", "bm25:0", "facts_dense:6", "facts_bm25:0"]
      search.query=contact_info
      search.top_scores=[0.0328, 0.0323, 0.0318, 0.031, 0.0305]
    search (31ms)
      search.config=hybrid_facts
      search.fact_types=["contact"]
      search.identifiers=[]
      search.latency_ms=30.8
      search.lists=["dense:30", "bm25:24", "facts_dense:6", "facts_bm25:6"]
      search.query=buyer contact email phone
      search.top_scores=[0.065, 0.0645, 0.064, 0.0611, 0.0603]
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["contact"]
      search.identifiers=[]
      search.latency_ms=29.1
      search.lists=["dense:30", "bm25:24", "facts_dense:6", "facts_bm25:6"]
      search.query=point of contact procurement officer
      search.top_scores=[0.0645, 0.0645, 0.0643, 0.0611, 0.06]
    rerank (669ms)
      search.query=["contact_info: The agency's procurement contact for this solicitation: name, title, email and phone. Not contacts for unrelated processes (for example catal...
      search.reranked=6
    search (29ms)
      search.config=hybrid_facts
      search.fact_types=["delivery"]
      search.identifiers=[]
      search.latency_ms=29.3
      search.lists=["dense:30", "bm25:1", "facts_dense:4", "facts_bm25:0"]
      search.query=Installation
      search.top_scores=[0.0323, 0.0318, 0.0305, 0.0304, 0.0271]
    search (27ms)
      search.config=hybrid_facts
      search.fact_types=["delivery"]
      search.identifiers=[]
      search.latency_ms=26.9
      search.lists=["dense:30", "bm25:4", "facts_dense:4", "facts_bm25:1"]
      search.query=installation deployment services
      search.top_scores=[0.0589, 0.0323, 0.0318, 0.031, 0.0308]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.2
      search.lists=["dense:30", "bm25:1"]
      search.query=white glove imaging asset tagging
      search.top_scores=[0.028, 0.0164, 0.0161, 0.0159, 0.0156]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.2
      search.lists=["dense:30", "bm25:17"]
      search.query=setup configuration services
      search.top_scores=[0.0307, 0.0304, 0.0303, 0.0301, 0.0292]
    rerank (2.42s)
      search.query=["Installation: Installation, deployment, imaging, tagging or other on-site services the solicitation requires, or that none are required. A factory-install ...
      search.reranked=11
  agent.retrieve.parties_logistics/2 (783ms)
    agent.input={"batch":"parties_logistics/2","fields":["delivery_date"],"attempt":1,"reasons":{},"hints":{}}
    agent.output={"delivery_date":["57b478dcce95481a66ae2d49","cfb4071f1d12743e1f27e173","dc914406e49b3a21d4a75381","2b19ae3f5978e543d8ddea59","0d76dedc96d16a93f69a4bb2","bf3...
    agent.reranked=true
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["delivery"]
      search.identifiers=[]
      search.latency_ms=28.2
      search.lists=["dense:30", "bm25:14", "facts_dense:4", "facts_bm25:4"]
      search.query=Delivery Date
      search.top_scores=[0.065, 0.0645, 0.0635, 0.0619, 0.0305]
    search (30ms)
      search.config=hybrid_facts
      search.fact_types=["award", "delivery"]
      search.identifiers=[]
      search.latency_ms=29.6
      search.lists=["dense:30", "bm25:18", "facts_dense:5", "facts_bm25:5"]
      search.query=delivery timeline days after award
      search.top_scores=[0.065, 0.0645, 0.0633, 0.0617, 0.055]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["delivery"]
      search.identifiers=[]
      search.latency_ms=28.3
      search.lists=["dense:30", "bm25:15", "facts_dense:4", "facts_bm25:4"]
      search.query=delivery date location
      search.top_scores=[0.065, 0.0643, 0.0623, 0.0611, 0.031]
    search (28ms)
      search.config=hybrid_facts
      search.fact_types=["delivery"]
      search.identifiers=[]
      search.latency_ms=27.9
      search.lists=["dense:30", "bm25:14", "facts_dense:4", "facts_bm25:4"]
      search.query=shipment lead time
      search.top_scores=[0.065, 0.0643, 0.0633, 0.0625, 0.0315]
    rerank (657ms)
      search.query=["Delivery Date: When goods must be delivered: a date, or a period relative to award or order (for example \"within 45 days of award\"), and delivery locatio...
      search.reranked=6
  agent.extract.identity_dates (2.54s)
    agent.attempt=1
    agent.fields=["bid_number", "title", "pre_bid_meeting"]
    agent.output={"bid_number":"found","title":"found","pre_bid_meeting":"not_found"}
    llm.cost_usd=0.001065
    llm.input=Fields to extract:
- bid_number (Bid Number; identifier): The number the issuing agency assigned to this solicitation (RFP, RFQ, IFB, PORFP or sourcing event...
    llm.input_tokens=3455
    llm.latency_ms=2538.0
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"bid_number","status":"found","value":"#E20P4600040","items":null,"quotes":[{"evidence_id":"0add078209cc59571febe7ad","text":"PORFP Numbe...
    llm.output_tokens=912
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.identity_dates/2 (59.93s)
    agent.attempt=1
    agent.fields=["bid_submission_type"]
    agent.output={"bid_submission_type":"found"}
    llm.cost_usd=0.001016
    llm.input=Fields to extract:
- bid_submission_type (Bid Submission Type; text): How responses must be submitted: electronic portal (which one), email, sealed hard copy...
    llm.input_tokens=2971
    llm.latency_ms=2472.2
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"bid_submission_type","status":"found","value":"Electronic submission via eMaryland Marketplace Advantage (eMMA) portal only; email, fax,...
    llm.output_tokens=950
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.commercial_legal (60.09s)
    agent.attempt=1
    agent.fields=["term_of_bid", "bid_bond_requirement", "payment_terms"]
    agent.output={"term_of_bid":"found","bid_bond_requirement":"not_found","payment_terms":"found"}
    llm.cost_usd=0.00104
    llm.input=Fields to extract:
- term_of_bid (Term of Bid; text): Contract term and renewal options. When no term is stated, report what the solicitation says instead: t...
    llm.input_tokens=3016
    llm.latency_ms=2563.2
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"term_of_bid","status":"found","value":"Fixed Price; proposals must be valid for at least 90 days after the due date","items":null,"quote...
    llm.output_tokens=979
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.commercial_legal/2 (60.77s)
    agent.attempt=1
    agent.fields=["contract_or_cooperative", "additional_documentation"]
    agent.output={"contract_or_cooperative":"found","additional_documentation":"found"}
    llm.cost_usd=0.001255
    llm.input=Fields to extract:
- contract_or_cooperative (Contract or Cooperative to use; text): The contract vehicle or purchasing cooperative the purchase is made unde...
    llm.input_tokens=3023
    llm.latency_ms=3334.0
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"contract_or_cooperative","status":"found","value":"Desktop, Laptop and Tablet 2015 Master Contract, 060B5400007","items":null,"quotes":[...
    llm.output_tokens=1336
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.product_specs (67.04s)
    agent.attempt=1
    agent.fields=["product", "model_no", "part_no"]
    agent.output={"product":"not_found","model_no":"not_found","part_no":"not_found"}
    llm.error=LLMError: output truncated at 3500 tokens
    llm.input=Fields to extract:
- product (Product; text): The goods or services being bought, with quantities when stated. When the solicitation groups products into cat...
    llm.model=openai/gpt-oss-120b
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.product_specs/2 (54.27s)
    agent.attempt=1
    agent.fields=["mfg_for_registration", "product_specification"]
    agent.output={"mfg_for_registration":"found","product_specification":"found"}
    llm.cost_usd=0.001687
    llm.input=Fields to extract:
- mfg_for_registration (MFG for Registration; text): The manufacturer the products are registered with or must come from (OEM requirements...
    llm.input_tokens=3319
    llm.latency_ms=4649.0
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"mfg_for_registration","status":"found","value":"Dell","items":null,"quotes":[{"evidence_id":"0add078209cc59571febe7ad","text":"Manufactu...
    llm.output_tokens=1982
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.parties_logistics (58.55s)
    agent.attempt=1
    agent.fields=["company_name", "contact_info", "installation"]
    agent.output={"company_name":"found","contact_info":"found","installation":"not_found"}
    llm.cost_usd=0.001246
    llm.input=Fields to extract:
- company_name (company_name; text): The issuing agency or organisation (the buyer), not a vendor or manufacturer.
- contact_info (contact...
    llm.input_tokens=3190
    llm.latency_ms=3198.0
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"company_name","status":"found","value":"State of Maryland Treasurer's Office","items":null,"quotes":[{"evidence_id":"8b8ea66640ba1b48d06...
    llm.output_tokens=1280
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.parties_logistics/2 (58.78s)
    agent.attempt=1
    agent.fields=["delivery_date"]
    agent.output={"delivery_date":"found"}
    llm.cost_usd=0.000539
    llm.input=Fields to extract:
- delivery_date (Delivery Date; text): When goods must be delivered: a date, or a period relative to award or order (for example "within 4...
    llm.input_tokens=1993
    llm.latency_ms=1980.7
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"delivery_date","status":"found","value":"within 45 days of Award","items":null,"quotes":[{"evidence_id":"57b478dcce95481a66ae2d49","text...
    llm.output_tokens=381
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.validate (11ms)
    agent.checked=["additional_documentation", "bid_bond_requirement", "bid_number", "bid_submission_type", "company_name", "contact_info", "contract_or_cooperative", "deliver...
    agent.failed=["model_no", "part_no", "product"]
    agent.output=[{"field":"product","reason":"the model call failed: LLMError: output truncated at 3500 tokens","attempt":2},{"field":"model_no","reason":"the model call fai...
  agent.retrieve.retry:product (18.08s)
    agent.input={"batch":"retry:product","fields":["product"],"attempt":2,"reasons":{"product":"the model call failed: LLMError: output truncated at 3500 tokens"},"hints":{}}
    agent.output={"product":["2870d3578d93bb7d11476833","18474d86b0e3cd8760b03821","cfb4071f1d12743e1f27e173","57b478dcce95481a66ae2d49","0add078209cc59571febe7ad","d9d0d345b...
    agent.reranked=true
    search (12ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=11.8
      search.lists=["dense:30", "bm25:9"]
      search.query=Product
      search.top_scores=[0.0328, 0.032, 0.0313, 0.0305, 0.0302]
    search (12ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=12.4
      search.lists=["dense:30", "bm25:16"]
      search.query=products to be purchased quantity
      search.top_scores=[0.0323, 0.032, 0.0318, 0.0313, 0.0304]
    search (12ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=11.7
      search.lists=["dense:30", "bm25:6"]
      search.query=scope of work devices
      search.top_scores=[0.0328, 0.032, 0.0313, 0.0305, 0.0303]
    search (20ms)
      search.config=hybrid_facts
      search.fact_types=["pricing"]
      search.identifiers=[]
      search.latency_ms=20.0
      search.lists=["dense:30", "bm25:6", "facts_dense:1", "facts_bm25:1"]
      search.query=price schedule line items
      search.top_scores=[0.0648, 0.0325, 0.0318, 0.0299, 0.0299]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.7
      search.lists=["dense:30", "bm25:4"]
      search.query=estimated quantity per tier
      search.top_scores=[0.0318, 0.0313, 0.0312, 0.0304, 0.0164]
    search (9ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.2
      search.lists=["dense:30", "bm25:7"]
      search.query=Goods list with quantities
      search.top_scores=[0.0323, 0.0305, 0.0304, 0.0301, 0.0292]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=10.3
      search.lists=["dense:30", "bm25:8"]
      search.query=Items and estimated amounts
      search.top_scores=[0.0325, 0.0313, 0.0313, 0.0311, 0.031]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.9
      search.lists=["dense:30", "bm25:10"]
      search.query=Product categories and volumes
      search.top_scores=[0.0325, 0.0318, 0.0313, 0.031, 0.0305]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.2
      search.lists=["dense:30", "bm25:5"]
      search.query=Supply schedule quantity details
      search.top_scores=[0.032, 0.0315, 0.0306, 0.0302, 0.0274]
    rerank (17.29s)
      search.query=["Product: The goods or services being bought, with quantities when stated. When the solicitation groups products into categories or tiers (in its requiremen...
      search.reranked=17
  agent.retrieve.rewrite (666ms)
    llm.cost_usd=9.6e-05
    llm.input=Field: Product: The goods or services being bought, with quantities when stated. When the solicitation groups products into categories or tiers (in its requi...
    llm.input_tokens=361
    llm.latency_ms=665.7
    llm.model=openai/gpt-oss-20b
    llm.output={"queries":["Goods list with quantities","Items and estimated amounts","Product categories and volumes","Supply schedule quantity details"]}
    llm.output_tokens=229
    llm.schema=QueriesOut
    llm.system=You write search queries for a hybrid (keyword and semantic) search engine over procurement documents. A field could not be extracted from the passages found...
  agent.retrieve.retry:model_no (6.51s)
    agent.input={"batch":"retry:model_no","fields":["model_no"],"attempt":2,"reasons":{"model_no":"the model call failed: LLMError: output truncated at 3500 tokens"},"hints"...
    agent.output={"model_no":["2aa9264be1444770c32ad146","32c9a5dc21d21e7a5aeb01d3","18474d86b0e3cd8760b03821","1c7e43fe40e9d5d5d75850e1","2b19ae3f5978e543d8ddea59","17d2730e...
    agent.reranked=true
    search (17ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=16.5
      search.lists=["dense:30", "bm25:0"]
      search.query=Model_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    search (12ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=12.1
      search.lists=["dense:30", "bm25:11"]
      search.query=model number
      search.top_scores=[0.032, 0.0318, 0.0318, 0.0301, 0.0299]
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.0
      search.lists=["dense:30", "bm25:17"]
      search.query=product model required
      search.top_scores=[0.0328, 0.0318, 0.0308, 0.0302, 0.0299]
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=12.9
      search.lists=["dense:30", "bm25:9"]
      search.query=brand and model
      search.top_scores=[0.0323, 0.0315, 0.0315, 0.0309, 0.0301]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.9
      search.lists=["dense:30", "bm25:9"]
      search.query=Manufacturer model designation
      search.top_scores=[0.032, 0.0318, 0.0315, 0.0306, 0.0304]
    search (8ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=8.3
      search.lists=["dense:30", "bm25:11"]
      search.query=Product line identifier
      search.top_scores=[0.0313, 0.0311, 0.031, 0.0308, 0.0308]
    search (9ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=8.8
      search.lists=["dense:30", "bm25:19"]
      search.query=Model name requirement section
      search.top_scores=[0.0328, 0.0318, 0.0313, 0.0308, 0.0303]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.6
      search.lists=["dense:30", "bm25:4"]
      search.query=Vendor model entry field
      search.top_scores=[0.0323, 0.0318, 0.0312, 0.0161, 0.0161]
    search (9ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.0
      search.lists=["dense:7", "bm25:0"]
      search.query=Model_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    rerank (5.60s)
      search.query=["Model_no: Manufacturer model names and numbers the documents require or quote, as the manufacturer markets them (a product line and number, for example a l...
      search.reranked=20
  agent.retrieve.rewrite (803ms)
    llm.cost_usd=0.000128
    llm.input=Field: Model_no: Manufacturer model names and numbers the documents require or quote, as the manufacturer markets them (a product line and number, for exampl...
    llm.input_tokens=404
    llm.latency_ms=803.1
    llm.model=openai/gpt-oss-20b
    llm.output={"queries":["Manufacturer model designation","Product line identifier","Model name requirement section","Vendor model entry field"]}
    llm.output_tokens=326
    llm.schema=QueriesOut
    llm.system=You write search queries for a hybrid (keyword and semantic) search engine over procurement documents. A field could not be extracted from the passages found...
  agent.retrieve.retry:part_no (6.22s)
    agent.input={"batch":"retry:part_no","fields":["part_no"],"attempt":2,"reasons":{"part_no":"the model call failed: LLMError: output truncated at 3500 tokens"},"hints":{}}
    agent.output={"part_no":["32c9a5dc21d21e7a5aeb01d3","17d2730edb2a79a1731187fd","1c7e43fe40e9d5d5d75850e1","5c6e2104e8b274970ad01b85","2b19ae3f5978e543d8ddea59","fffbefd6e...
    agent.reranked=true
    search (12ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=12.0
      search.lists=["dense:30", "bm25:0"]
      search.query=Part_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    search (14ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.2
      search.lists=["dense:30", "bm25:11"]
      search.query=part number SKU
      search.top_scores=[0.0323, 0.0323, 0.0315, 0.0303, 0.0299]
    search (15ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=14.6
      search.lists=["dense:30", "bm25:22"]
      search.query=configuration SKU list
      search.top_scores=[0.0318, 0.0318, 0.0311, 0.0304, 0.0299]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.8
      search.lists=["dense:30", "bm25:11"]
      search.query=item part numbers
      search.top_scores=[0.0323, 0.0306, 0.0304, 0.0304, 0.0301]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.8
      search.lists=["dense:30", "bm25:10"]
      search.query=line item codes list
      search.top_scores=[0.032, 0.031, 0.0308, 0.029, 0.0287]
    search (10ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=9.9
      search.lists=["dense:30", "bm25:12"]
      search.query=item identifiers section
      search.top_scores=[0.0323, 0.0315, 0.0306, 0.0299, 0.0289]
    search (13ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=13.2
      search.lists=["dense:30", "bm25:7"]
      search.query=component numbers table
      search.top_scores=[0.0313, 0.0313, 0.031, 0.0308, 0.0305]
    search (16ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=15.6
      search.lists=["dense:30", "bm25:8"]
      search.query=bill of materials part numbers
      search.top_scores=[0.0313, 0.0313, 0.0311, 0.031, 0.031]
    search (11ms)
      search.config=hybrid_facts
      search.fact_types=[]
      search.identifiers=[]
      search.latency_ms=10.8
      search.lists=["dense:7", "bm25:0"]
      search.query=Part_no
      search.top_scores=[0.0164, 0.0161, 0.0159, 0.0156, 0.0154]
    rerank (5.27s)
      search.query=["Part_no: Part numbers or SKUs listed in the documents (quotes, configurations, line items). Return not_found when none are listed."]
      search.reranked=22
  agent.retrieve.rewrite (826ms)
    llm.cost_usd=0.000147
    llm.input=Field: Part_no: Part numbers or SKUs listed in the documents (quotes, configurations, line items). Return not_found when none are listed.
Why the last attemp...
    llm.input_tokens=339
    llm.latency_ms=825.5
    llm.model=openai/gpt-oss-20b
    llm.output={"queries":["line item codes list","item identifiers section","component numbers table","bill of materials part numbers"]}
    llm.output_tokens=406
    llm.schema=QueriesOut
    llm.system=You write search queries for a hybrid (keyword and semantic) search engine over procurement documents. A field could not be extracted from the passages found...
  agent.extract.retry:product (29.71s)
    agent.attempt=2
    agent.fields=["product"]
    agent.output={"product":"found"}
    llm.cost_usd=0.001016
    llm.input=Fields to extract:
- product (Product; text): The goods or services being bought, with quantities when stated. When the solicitation groups products into cat...
    llm.input_tokens=2939
    llm.latency_ms=2544.4
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"product","status":"found","value":null,"items":["Dell Latitude 5550 Laptop – Qty 30","Dell Thunderbolt 4 Dock – WD22TB4 – Qty 30"],"quot...
    llm.output_tokens=959
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.retry:model_no (59.82s)
    agent.attempt=2
    agent.fields=["model_no"]
    agent.output={"model_no":"found"}
    llm.cost_usd=0.001001
    llm.input=Fields to extract:
- model_no (Model_no; list of items): Manufacturer model names and numbers the documents require or quote, as the manufacturer markets the...
    llm.input_tokens=3237
    llm.latency_ms=2362.1
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"model_no","status":"found","value":null,"items":["Dell Latitude 5550","Dell Thunderbolt 4 Dock – WD22TB4"],"quotes":[{"evidence_id":"32c...
    llm.output_tokens=859
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.extract.retry:part_no (62.33s)
    agent.attempt=2
    agent.fields=["part_no"]
    agent.output={"part_no":"found"}
    llm.cost_usd=0.001746
    llm.input=Fields to extract:
- part_no (Part_no; list of items): Part numbers or SKUs listed in the documents (quotes, configurations, line items). Return not_found wh...
    llm.input_tokens=3837
    llm.latency_ms=4692.9
    llm.model=openai/gpt-oss-120b
    llm.output={"drafts":[{"field":"part_no","status":"found","value":null,"items":["210-BLYZ","379-BFNZ","619-ARSB","658-BCSB","338-CNRG","338-CNRK","321-BKTQ","409-BCXY",...
    llm.output_tokens=1950
    llm.schema=GroupDraftOut
    llm.system=You extract fields from public procurement documents (RFPs, addenda, purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking syste...
  agent.validate (4ms)
    agent.checked=["model_no", "part_no", "product"]
    agent.failed=[]
    agent.output=[]
  agent.report (1.00s)
    agent.output=passed 17, failed 0, not_found 3, conflicts 0
    agent.result_path=outputs\Bid2.json
  agent.validate.consistency (0ms)
    agent.issues=[]
  agent.summary (1.00s)
    llm.cost_usd=0.000232
    llm.input=Extracted fields:
- bid_number: #E20P4600040
- title: Dell Laptops w/Extended Warranty
- due_date: June 10, 2024, 2:00 PM EDT
- pre_bid_meeting: not specifie...
    llm.input_tokens=993
    llm.latency_ms=1002.1
    llm.model=openai/gpt-oss-20b
    llm.output={"summary":"The State of Maryland Treasurer's Office is purchasing 30 Dell Latitude 5550 laptops and 30 Dell Thunderbolt 4 Dock WD22TB4 units. The final bid ...
    llm.output_tokens=524
    llm.schema=SummaryOut
    llm.system=You write a short summary of a procurement bid for a sales team, from the extracted fields given. Three to six plain sentences: who is buying what (with quan...
```

## Model calls in full

### agent.extract.identity_dates

Model `openai/gpt-oss-120b`, 3455 input and 912 output tokens.

Prompt (user turn):

```text
Fields to extract:
- bid_number (Bid Number; identifier): The number the issuing agency assigned to this solicitation (RFP, RFQ, IFB, PORFP or sourcing event number). If the portal and the document give different numbering systems, report the primary solicitation number and mention the other in notes.
- title (Title; text): The solicitation's title as the agency states it, without the number.
- pre_bid_meeting (Pre Bid Meeting; date and time with zone): Date, time, place or link of any pre-bid or pre-proposal meeting or site visit, and whether attendance is mandatory. "None" when the documents say there is no meeting.

Candidate facts for bid_number:
- identifier "00004079359" = 00004079359 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Reference Number: 00004079359"
- identifier "BPM044557" = BPM044557 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Solicitation Number: BPM044557"
- identifier "CC7802" = CC7802 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Description: 1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 D"
- identifier "CC7802" = CC7802 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Description: 1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 D"
- identifier "CC7802" = CC7802 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Description: 1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 D"
- identifier "WD22TB4" = WD22TB4 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Description: 1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 D"
- identifier "WD22TB4" = WD22TB4 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Description: 1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 D"
- identifier "WD22TB4" = WD22TB4 (Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html p1, bid_page): "Description: 1. SI# CC7802 Dell Latitude 5550 SI# CC7802 Dell Latitude 5550 *Laptops must be Microsoft Copilot ready* SI# CC7802 30 06/10/2024 2. Dell Thunderbolt 4 Dock – WD22TB4 Dell Thunderbolt 4 D"
- identifier "210-BLYZ" = 210-BLYZ (Dell_Laptop_Specs.pdf p1, specs): "SKU | 210-BLYZ"
- identifier "379-BFNZ" = 379-BFNZ (Dell_Laptop_Specs.pdf p1, specs): "SKU | 379-BFNZ"
- identifier "619-ARSB" = 619-ARSB (Dell_Laptop_Specs.pdf p1, specs): "SKU | 619-ARSB"
- identifier "658-BCSB" = 658-BCSB (Dell_Laptop_Specs.pdf p1, specs): "SKU | 658-BCSB"
- identifier "338-CNRG" = 338-CNRG (Dell_Laptop_Specs.pdf p1, specs): "SKU | 338-CNRG"
- identifier "338-CNRK" = 338-CNRK (Dell_Laptop_Specs.pdf p1, specs): "SKU | 338-CNRK"
- identifier "321-BKTQ" = 321-BKTQ (Dell_Laptop_Specs.pdf p1, specs): "SKU | 321-BKTQ"
- identifier "409-BCXY" = 409-BCXY (Dell_Laptop_Specs.pdf p1, specs): "SKU | 409-BCXY"
- identifier "631-BBSQ" = 631-BBSQ (Dell_Laptop_Specs.pdf p1, specs): "SKU | 631-BBSQ"
- identifier "370-BBTL" = 370-BBTL (Dell_Laptop_Specs.pdf p1, specs): "SKU | 370-BBTL"
- identifier "400-BRFT" = 400-BRFT (Dell_Laptop_Specs.pdf p1, specs): "SKU | 400-BRFT"
- identifier "391-BJHB" = 391-BJHB (Dell_Laptop_Specs.pdf p1, specs): "SKU | 391-BJHB"
- identifier "583-BLNH" = 583-BLNH (Dell_Laptop_Specs.pdf p1, specs): "SKU | 583-BLNH"
- identifier "AX211" = AX211 (Dell_Laptop_Specs.pdf p1, specs): "Description | Intel AX211 WLAN Driver"
- identifier "555-BKQC" = 555-BKQC (Dell_Laptop_Specs.pdf p1, specs): "SKU | 555-BKQC"
- identifier "AX211" = AX211 (Dell_Laptop_Specs.pdf p1, specs): "Description | Intel Wi-Fi 6E (6 where 6E unavailable) AX211, 2x2, 802.11ax, Bluetooth 5.3 wireless card"
- identifier "555-BKLQ" = 555-BKLQ (Dell_Laptop_Specs.pdf p1, specs): "SKU | 555-BKLQ"

Passages:

[0add078209cc59571febe7ad] PORFP_-_Dell_Laptop_Final.pdf p1 (rfp; document title "Purchase Order Request for Proposals (PORFP) Hardware Master Contract")
Section 1 –General Information
PORFP Number: | #E20P4600040 eMMA Project Number: BPM044557
PORFP Type: | Fixed Price
Functional Area/s (FA) for this PORFP: | Functional Area/s (FA) for this PORFP: | FA I (Printers and Associated Peripherals) FA V (Manufacturer’s Extended Warranty)
Manufacturer Name | Dell
Designated Small Business Reserve?(SBR): | Yes
Minority Business Enterprise (MBE) Goal for FA IV Below (See “Hardware Master Contract MBE Participation Worksheet”): | 0 %
PORFP Issue Date: | 05/24/2024 | PROPOSAL DUE | 06/10/2024
mm/dd/yyyy | DATE and TIME:
Place of Performance: | Place of Performance: | MD State Treasurer's Office 80 Clavert Street Annapolis MD 21401
Special Instructions: | LIMITED TO MASTER CONTRACTORS Only Master Contractors that are awarded a contract under the Desktop, Laptop and Tablet 2015 Master Contract, 060B5400007, are eligible to submit a bid in response to this secondary competition Purchase Order Request for Proposal (PORFP). SMALL BUSINESS RESERVE (SBR) PROCUREMENT This is a Small Business Reserve Procurement for which award will be limited to certified small business vendors. Only businesses that meet the statutory requirements set forth in State Finance and Procurement Article, §§14-501—14-505, Annotated Code of Maryland, and that are c
... [3308 more]
```

Response:

```json
{
  "drafts": [
    {
      "field": "bid_number",
      "status": "found",
      "value": "#E20P4600040",
      "items": null,
      "quotes": [
        {
          "evidence_id": "0add078209cc59571febe7ad",
          "text": "PORFP Number: | #E20P4600040 eMMA Project Number: BPM044557"
        }
      ],
      "notes": "The eMMA Project Number BPM044557 is also listed but the primary PORFP Number is used."
    },
    {
      "field": "title",
      "status": "found",
      "value": "Dell Laptops w/Extended Warranty",
      "items": null,
      "quotes": [
        {
          "evidence_id": "8b8ea66640ba1b48d06e8df6",
          "text": "Title: Dell Laptops w/Extended Warranty"
        }
      ],
      "notes": null
    },
    {
      "field": "pre_bid_meeting",
      "status": "not_found",
      "value": null,
      "items": null,
      "quotes": [],
      "notes": "No pre‑bid meeting information provided in the passages."
    }
  ]
}
```

### agent.retrieve.rewrite

Model `openai/gpt-oss-20b`, 361 input and 229 output tokens.

Prompt (user turn):

```text
Field: Product: The goods or services being bought, with quantities when stated. When the solicitation groups products into categories or tiers (in its requirements or price schedule), name each category and give its quantity or estimated quantity.
Why the last attempt failed: the model call failed: LLMError: output truncated at 3500 tokens
Queries already tried: Product; products to be purchased quantity; scope of work devices; price schedule line items; estimated quantity per tier
```

Response:

```json
{
  "queries": [
    "Goods list with quantities",
    "Items and estimated amounts",
    "Product categories and volumes",
    "Supply schedule quantity details"
  ]
}
```

### agent.summary

Model `openai/gpt-oss-20b`, 993 input and 524 output tokens.

Prompt (user turn):

```text
Extracted fields:
- bid_number: #E20P4600040
- title: Dell Laptops w/Extended Warranty
- due_date: June 10, 2024, 2:00 PM EDT
- pre_bid_meeting: not specified
- bid_submission_type: Electronic submission via eMaryland Marketplace Advantage (eMMA) portal only; email, fax, U.S. Mail, and hand delivery not accepted.
- term_of_bid: Fixed Price; proposals must be valid for at least 90 days after the due date
- bid_bond_requirement: not specified
- payment_terms: Invoice(s) shall be submitted within 10 days of delivering the equipment
- contract_or_cooperative: Desktop, Laptop and Tablet 2015 Master Contract, 060B5400007
- additional_documentation: Mercury Affidavit, Attachment N – Contract Affidavit
- product: Dell Latitude 5550 Laptop – Qty 30, Dell Thunderbolt 4 Dock – WD22TB4 – Qty 30
- model_no: Dell Latitude 5550, Dell Thunderbolt 4 Dock – WD22TB4
- part_no: 210-BLYZ, 379-BFNZ, 619-ARSB, 658-BCSB, 338-CNRG, 338-CNRK, 321-BKTQ, 409-BCXY, 631-BBSQ, 370-BBTL, 400-BRFT, 391-BJHB, 583-BLNH, 555-BKQC, 555-BKLQ, 451-BDGX, 492-BDMN, 346-BKLV, 537-BBDO, 340-DMNY, 340-AGIK, 387-BBPC, 817-BBBB, 658-BFQB, 340-DMMK, 389-FGSN, 319-BBKK, 634-BRWG, 379-BDZB, 362-7806, 364-1846, 364-4107, 365-0257, 366-0135, 366-0141, 371-0941, 375-3088, 383-0464
- mfg_for_registration: Dell
- product_specification: Intel Core Ultra 5 125U processor (12 MB cache, 12 cores, 14 threads, up to 4.3 GHz Turbo), 16 GB: 2 x 8 GB, DDR5, 5600 MT/s (5200 MT/s with 13th Gen Intel Core processors), 256 GB, M.2 2230, TLC, Gen 4 PCIe NVMe, SSD, 15.6", FHD 1920x1080, 60Hz, IPS, Non-Touch, AG, 250 nit, 45% NTSC, FHD Cam, 3-cell, 54 Wh, ExpressCharge Capable, ExpressCharge Boost Capable, Dell Limited Hardware Warranty Extended for all machines purchased - 3 Years, ENERGY STAR Qualified, Laptops must be Microsoft Copilot ready, Windows 11 Pro, English, Brazilian Portuguese PT-BR, French, Spanish
- company_name: State of Maryland Treasurer's Office
- contact_info: Tamaira Hawkins, Email: [EMAIL], Phone: [PHONE]
- installation: not specified
- delivery_date: within 45 days of Award
```

Response:

```json
{
  "summary": "The State of Maryland Treasurer's Office is purchasing 30 Dell Latitude 5550 laptops and 30 Dell Thunderbolt 4 Dock WD22TB4 units. The final bid due date is June 10, 2024, 2:00 PM EDT, and proposals must be valid for at least 90 days after that date. Submissions must be made electronically via the eMaryland Marketplace Advantage (eMMA) portal only; email, fax, U.S. Mail, and hand delivery are not accepted. The contract requires a 3‑year extended warranty, delivery within 45 days of award, and invoices submitted within 10 days of delivery, along with a Mercury Affidavit and Attachment N – Contract Affidavit. Notably, the bid bond requirement, pre‑bid meeting, and installation details are not specified."
}
```
