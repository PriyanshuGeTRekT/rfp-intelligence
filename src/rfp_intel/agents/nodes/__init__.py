"""The agents, one module each. Every node is a function `(services, state) -> update`;
`graph.py` binds the services and wires the nodes together.

- orchestrator: plans the run, routes extract vs ask, dispatches field batches, decides retries
- ingest: indexes the bid folder (incremental) and lists its documents
- reconcile: turns addenda into change events and resolves the date fields
- retrieve: plans and rewrites queries, searches with filters and reranking, returns evidence
- extract: fills a batch of fields from the evidence, with quotes
- validate: checks every draft and sends failures back with a reason
- report: assembles the record, runs cross-field checks, writes the JSON and the summary
- answer: answers a question with checked citations
"""
