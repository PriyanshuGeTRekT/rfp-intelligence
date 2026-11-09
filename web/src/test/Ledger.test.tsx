import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { TooltipProvider } from "../components/ui/overlay";
import { Ledger } from "../features/ledger/Ledger";
import type { AddendumChange, DocumentInfo, FieldResult } from "../lib/types";

const documents: DocumentInfo[] = [
  { file: "JA-207652 FINAL.pdf", doc_type: "rfp", addendum_number: null, doc_date: "2024-05-26", pages: 62 },
  { file: "Addendum 2.pdf", doc_type: "addendum", addendum_number: 2, doc_date: "2024-06-27", pages: 1 },
];

const fields: Record<string, FieldResult> = {
  "Due Date": {
    key: "due_date",
    value: "2024-07-09 14:00 CDT",
    status: "found",
    sources: [{ file: "Addendum 2.pdf", page: 1, quote: "The new due date is July 9, 2024 at 2:00 PM CST.", doc_type: "addendum", addendum_number: 2, evidence_id: "e1" }],
    confidence: 0.95,
    tier: "A",
    normalized: { date: "2024-07-09", display: "July 9, 2024, 2:00 PM CDT" },
    notes: "Extended by Addendum 2 (original date: 2024-06-27 14:00 CDT).",
  },
  "Bid Bond Requirement": {
    key: "bid_bond_requirement",
    value: null,
    status: "not_found",
    sources: [],
    confidence: 0.8,
    tier: "NF-1",
    normalized: null,
    notes: "Not found in documents. Searched 4 queries.",
  },
  "Term of Bid": {
    key: "term_of_bid",
    value: "Initial term of 3 years",
    status: "found",
    sources: [{ file: "JA-207652 FINAL.pdf", page: 2, quote: "Initial Term: 3", doc_type: "rfp", addendum_number: null, evidence_id: "e2" }],
    confidence: 0.85,
    tier: "B",
    normalized: null,
    notes: null,
  },
};

const changes: AddendumChange[] = [
  {
    field: "due_date",
    operation: "replace",
    addendum_number: 2,
    doc_date: "2024-06-27",
    old_value: "27-JUN-2024 14:00:00",
    new_value: "July 9, 2024 at 2:00 PM CST",
    source: { file: "Addendum 2.pdf", page: 1, quote: "The new due date is July 9, 2024 at 2:00 PM CST.", doc_type: "addendum", addendum_number: 2, evidence_id: null },
  },
];

const renderLedger = (url = "/bids/Bid1") =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <TooltipProvider>
        <Ledger fields={fields} bidId="Bid1" documents={documents} changes={changes} />
      </TooltipProvider>
    </MemoryRouter>,
  );

describe("Ledger", () => {
  it("shows values, absent fields, readable dates and the field groups", () => {
    renderLedger();
    expect(screen.getByText("2024-07-09 14:00 CDT")).toBeInTheDocument();
    expect(screen.getByText("July 9, 2024, 2:00 PM CDT")).toBeInTheDocument();
    expect(screen.getByText("Not found in documents")).toBeInTheDocument();
    expect(screen.getByText("Identity & dates")).toBeInTheDocument();
    expect(screen.getByText("Commercial & legal")).toBeInTheDocument();
  });

  it("marks a changed value with its addendum and cites the short document label", () => {
    renderLedger();
    const row = screen.getByText("Due Date").closest("tr")!;
    expect(within(row).getByText(/Add\. 2 · Replaced/)).toBeInTheDocument();
    const cite = within(row).getByRole("button", { name: /Open Addendum 2\.pdf at p\. 1/ });
    expect(cite).toHaveTextContent("Add. 2");
    expect(cite).toHaveTextContent("p. 1");
  });

  it("filters by status and by text", async () => {
    const user = userEvent.setup();
    renderLedger();
    const filters = within(screen.getByRole("group", { name: "Filter by status" }));
    await user.click(filters.getByRole("button", { name: /Not found/ }));
    expect(screen.queryByText("Due Date")).not.toBeInTheDocument();
    expect(screen.getByText("Bid Bond Requirement")).toBeInTheDocument();
    await user.click(filters.getByRole("button", { name: /All/ }));
    await user.type(screen.getByLabelText("Filter fields"), "due");
    expect(screen.getByText("Due Date")).toBeInTheDocument();
    expect(screen.queryByText("Bid Bond Requirement")).not.toBeInTheDocument();
  });

  it("filters to the fields a document supports when the URL names it", () => {
    renderLedger("/bids/Bid1?doc=Addendum%202.pdf");
    expect(screen.getByText("Due Date")).toBeInTheDocument();
    expect(screen.queryByText("Term of Bid")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cited in Add\. 2/ })).toBeInTheDocument();
  });

  it("expands a row in place to show its verbatim evidence, change and note", async () => {
    const user = userEvent.setup();
    renderLedger();
    const row = screen.getByText("Due Date").closest("tr")!;
    expect(row).toHaveAttribute("aria-expanded", "false");
    await user.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    const quotes = screen.getAllByText(/“The new due date is July 9, 2024/);
    expect(quotes).toHaveLength(2);
    expect(within(quotes[0]!.closest("figure")!).getByRole("button", { name: /Addendum 2\.pdf/ })).toBeInTheDocument();
    expect(screen.getByText("27-JUN-2024 14:00:00")).toBeInTheDocument();
    expect(screen.getByText(/Extended by Addendum 2/)).toBeInTheDocument();
    expect(screen.getByText("Corroborated")).toBeInTheDocument();
  });

  it("opens the field named in the URL", () => {
    renderLedger("/bids/Bid1?field=bid_bond_requirement");
    const row = screen.getByText("Bid Bond Requirement").closest("tr")!;
    expect(row).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText("Searched 4 queries.").length).toBeGreaterThan(0);
  });
});
