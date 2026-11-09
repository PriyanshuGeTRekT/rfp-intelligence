// Short labels for a bid's documents, so a citation reads "Add. 2 · p. 1" and the full file
// name stays one hover away. Labels are derived on the client from the bid's document list;
// when no list is at hand (answers across bids, comparison cells) the file name is read instead.

export type DocKind = "rfp" | "addendum" | "portal" | "specs" | "affidavit" | "form" | "other";

export interface DocLabel {
  file: string;
  label: string;
  kind: DocKind;
  addendumNumber: number | null;
}

export type DocLabels = Map<string, DocLabel>;

interface DocMeta {
  file: string;
  doc_type: string;
  addendum_number: number | null;
}

const KIND_BY_TYPE: Record<string, DocKind> = {
  rfp: "rfp",
  addendum: "addendum",
  bid_page: "portal",
  specs: "specs",
  affidavit: "affidavit",
  form: "form",
};

const BASE_LABEL: Record<DocKind, string> = {
  rfp: "RFP",
  addendum: "Addendum",
  portal: "Portal",
  specs: "Specs",
  affidavit: "Affidavit",
  form: "Form",
  other: "Document",
};

const stem = (file: string) => file.replace(/^.*[\\/]/, "").replace(/\.[^.]+$/, "");

function baseLabel(kind: DocKind, addendumNumber: number | null, file: string): string {
  if (kind === "addendum" && addendumNumber) return `Add. ${addendumNumber}`;
  if (kind === "other") {
    const s = stem(file).replace(/[_-]+/g, " ").trim();
    return s.length > 18 ? `${s.slice(0, 17)}…` : s || BASE_LABEL.other;
  }
  return BASE_LABEL[kind];
}

/** A word from the file name that tells two same-kind documents apart ("Contract", "Mercury"). */
function distinguisher(file: string, label: string): string {
  const words = stem(file)
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .filter((w) => w && w.toLowerCase() !== label.toLowerCase() && !/^\d+$/.test(w));
  return words[0] ?? stem(file).slice(0, 12);
}

/** Labels for every document of a bid, made unique when two share a kind. */
export function buildDocLabels(documents: DocMeta[]): DocLabels {
  const kinds = documents.map((d) => KIND_BY_TYPE[d.doc_type] ?? "other");
  const bases = documents.map((d, i) => baseLabel(kinds[i] ?? "other", d.addendum_number, d.file));
  const counts = new Map<string, number>();
  for (const b of bases) counts.set(b, (counts.get(b) ?? 0) + 1);
  const labels: DocLabels = new Map();
  documents.forEach((d, i) => {
    const base = bases[i] ?? BASE_LABEL.other;
    const label = (counts.get(base) ?? 0) > 1 ? `${base} (${distinguisher(d.file, base)})` : base;
    labels.set(d.file, { file: d.file, label, kind: kinds[i] ?? "other", addendumNumber: d.addendum_number });
  });
  return labels;
}

/** A label read from the file name alone, for citations that arrive without a document list. */
export function labelFromFile(file: string): DocLabel {
  const name = stem(file);
  const addendum = /addendum\s*(?:no\.?\s*)?(\d+)/i.exec(name);
  if (addendum) return { file, label: `Add. ${addendum[1]}`, kind: "addendum", addendumNumber: Number(addendum[1]) };
  if (/addendum/i.test(name)) return { file, label: "Addendum", kind: "addendum", addendumNumber: null };
  if (/\.html?$/i.test(file)) return { file, label: "Portal", kind: "portal", addendumNumber: null };
  if (/spec/i.test(name)) return { file, label: "Specs", kind: "specs", addendumNumber: null };
  if (/affidavit/i.test(name)) return { file, label: "Affidavit", kind: "affidavit", addendumNumber: null };
  if (/\b(rfp|rfq|ifb|solicitation)\b|porfp/i.test(name)) return { file, label: "RFP", kind: "rfp", addendumNumber: null };
  return { file, label: baseLabel("other", null, file), kind: "other", addendumNumber: null };
}

/** A label from the metadata a search hit carries (doc type and addendum number). */
export function labelFromMeta(file: string, docType: string, addendumNumber: number | null): DocLabel {
  const kind = KIND_BY_TYPE[docType] ?? "other";
  return { file, label: baseLabel(kind, addendumNumber, file), kind, addendumNumber };
}

/** The bid's label for a file, falling back to the file name when the file is not listed. */
export function labelFor(labels: DocLabels | undefined, file: string): DocLabel {
  return labels?.get(file) ?? labelFromFile(file);
}
