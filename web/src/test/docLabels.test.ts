import { buildDocLabels, labelFor, labelFromFile, labelFromMeta } from "../lib/docLabels";

const bid1 = [
  { file: "Addendum 1 RFP JA-207652 Student and Staff Computing Devices.pdf", doc_type: "addendum", addendum_number: 1 },
  { file: "Addendum 2 RFP JA-207652 Student and Staff Computing Devices.pdf", doc_type: "addendum", addendum_number: 2 },
  { file: "JA-207652 Student and Staff Computing Devices FINAL.pdf", doc_type: "rfp", addendum_number: null },
  { file: "Student and Staff Computing Devices __SOURCING #168884__ - Bid Information - {3} _ BidNet Direct.html", doc_type: "bid_page", addendum_number: null },
];

const bid2 = [
  { file: "Contract_Affidavit.pdf", doc_type: "affidavit", addendum_number: null },
  { file: "Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html", doc_type: "bid_page", addendum_number: null },
  { file: "Dell_Laptop_Specs.pdf", doc_type: "specs", addendum_number: null },
  { file: "Mercury_Affidavit.pdf", doc_type: "affidavit", addendum_number: null },
  { file: "PORFP_-_Dell_Laptop_Final.pdf", doc_type: "rfp", addendum_number: null },
];

describe("document labels", () => {
  it("labels a bid's documents by kind and addendum number", () => {
    const labels = buildDocLabels(bid1);
    expect([...labels.values()].map((l) => l.label)).toEqual(["Add. 1", "Add. 2", "RFP", "Portal"]);
    expect(labels.get(bid1[3]!.file)?.kind).toBe("portal");
  });

  it("tells two documents of the same kind apart with a word from the file name", () => {
    const labels = buildDocLabels(bid2);
    expect(labels.get("Contract_Affidavit.pdf")?.label).toBe("Affidavit (Contract)");
    expect(labels.get("Mercury_Affidavit.pdf")?.label).toBe("Affidavit (Mercury)");
    expect(labels.get("Dell_Laptop_Specs.pdf")?.label).toBe("Specs");
    expect(labels.get("PORFP_-_Dell_Laptop_Final.pdf")?.label).toBe("RFP");
  });

  it("reads a label from the file name when no document list is at hand", () => {
    expect(labelFromFile("RFP 2025-003 Computer Equipment Addendum 1.pdf").label).toBe("Add. 1");
    expect(labelFromFile("RFP 2025-003 Computer Equipment.pdf").label).toBe("RFP");
    expect(labelFromFile("PORFP_-_Dell_Laptop_Final.pdf").label).toBe("RFP");
    expect(labelFromFile("Dell Laptops w_Extended Warranty - Bid Information - {3} _ BidNet Direct.html").kind).toBe("portal");
    expect(labelFromFile("Mercury_Affidavit.pdf").label).toBe("Affidavit");
    expect(labelFromFile("notes.pdf").label).toBe("notes");
  });

  it("uses search-hit metadata and falls back to the file name for unlisted files", () => {
    expect(labelFromMeta("x.pdf", "addendum", 3).label).toBe("Add. 3");
    expect(labelFromMeta("x.pdf", "specs", null).label).toBe("Specs");
    const labels = buildDocLabels(bid1);
    expect(labelFor(labels, bid1[2]!.file).label).toBe("RFP");
    expect(labelFor(labels, "Addendum 3 late.pdf").label).toBe("Add. 3");
    expect(labelFor(undefined, "Contract_Affidavit.pdf").label).toBe("Affidavit");
  });
});
