import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChangeMark, Cite, TierMeter, ValidationBar } from "../components/domain";
import { TooltipProvider } from "../components/ui/overlay";
import { labelFromFile } from "../lib/docLabels";

describe("TierMeter", () => {
  it("names the tier, its meaning and the confidence, with a glyph per tier", () => {
    render(
      <TooltipProvider>
        <TierMeter tier="A" confidence={0.95} />
        <TierMeter tier="NF-2" confidence={0.5} />
        <TierMeter tier="X" />
      </TooltipProvider>,
    );
    expect(screen.getByLabelText("Tier A, corroborated, confidence 0.95")).toBeInTheDocument();
    expect(screen.getByLabelText("Tier NF-2, unverified, confidence 0.50")).toBeInTheDocument();
    const rejected = screen.getByLabelText("Tier X, rejected");
    expect(rejected.querySelector("svg")).toHaveAttribute("data-tier", "X");
    expect(rejected.className).toContain("text-bad");
  });
});

describe("Cite", () => {
  it("shows the short label and page, and keeps the full file name for the title", () => {
    render(<Cite bidId="Bid1" doc={labelFromFile("Addendum 2 RFP JA-207652.pdf")} page={1} />);
    const chip = screen.getByRole("button", { name: "Open Addendum 2 RFP JA-207652.pdf at p. 1" });
    expect(chip).toHaveTextContent("Add. 2");
    expect(chip).toHaveTextContent("p. 1");
    expect(chip.className).toContain("text-accent");
  });

  it("shows a page range when given one", () => {
    render(<Cite bidId="Bid1" doc={labelFromFile("JA-207652 FINAL.pdf")} page={9} pages="pp. 9–11" />);
    expect(screen.getByRole("button", { name: /at pp\. 9–11/ })).toHaveTextContent("pp. 9–11");
  });
});

describe("ChangeMark", () => {
  it("stamps the addendum number and the operation", () => {
    render(<ChangeMark change={{ operation: "add_requirement", addendum_number: 1 }} />);
    expect(screen.getByText("Add. 1 · Added requirement")).toBeInTheDocument();
  });
});

describe("ValidationBar", () => {
  const tally = { passed: 14, failed: 1, not_found: 5, conflicts: 0, fields: 20, passed_first_time: 13, passed_after_retry: 5, retries: 9, checks_failed: {}, consistency_issues: [] };

  it("describes the segments in words and lets each count filter", async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<ValidationBar tally={tally} onPick={onPick} />);
    expect(screen.getByRole("img", { name: "14 passed, 5 not found, 1 failed of 20 fields" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /not found/ }));
    expect(onPick).toHaveBeenCalledWith("not_found");
  });
});
