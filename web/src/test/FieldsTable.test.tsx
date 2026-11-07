import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "../components/ui/overlay";
import { FieldsTable } from "../features/FieldsTable";
import type { FieldResult } from "../lib/types";

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
};

const renderTable = () =>
  render(
    <TooltipProvider>
      <FieldsTable fields={fields} bidId="Bid1" />
    </TooltipProvider>,
  );

describe("FieldsTable", () => {
  it("shows values, absent fields and readable dates", () => {
    renderTable();
    expect(screen.getByText("2024-07-09 14:00 CDT")).toBeInTheDocument();
    expect(screen.getByText("July 9, 2024, 2:00 PM CDT")).toBeInTheDocument();
    expect(screen.getByText("Not found in documents")).toBeInTheDocument();
  });

  it("filters by status and by text", async () => {
    const user = userEvent.setup();
    renderTable();
    const filters = within(screen.getByRole("group", { name: "Filter by status" }));
    await user.click(filters.getByRole("button", { name: /Not found/ }));
    expect(screen.queryByText("Due Date")).not.toBeInTheDocument();
    await user.click(filters.getByRole("button", { name: /All/ }));
    await user.type(screen.getByLabelText("Filter fields"), "due");
    expect(screen.getByText("Due Date")).toBeInTheDocument();
    expect(screen.queryByText("Bid Bond Requirement")).not.toBeInTheDocument();
  });

  it("expands a row to show its verbatim evidence and notes", async () => {
    const user = userEvent.setup();
    renderTable();
    const toggle = screen.getAllByRole("button", { expanded: false })[0]!;
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const quote = screen.getByText(/The new due date is July 9, 2024/);
    expect(within(quote.closest("figure")!).getByText("Addendum 2")).toBeInTheDocument();
    expect(screen.getByText(/Extended by Addendum 2/)).toBeInTheDocument();
  });
});
