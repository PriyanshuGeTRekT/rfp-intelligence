// The 20 fields arrive flat; the ledger shows them in the groups the extraction agents work in.
import type { FieldResult } from "./types";

export interface FieldGroup {
  id: string;
  name: string;
  keys: string[];
}

export const FIELD_GROUPS: FieldGroup[] = [
  { id: "identity", name: "Identity & dates", keys: ["bid_number", "title", "due_date", "pre_bid_meeting", "bid_submission_type"] },
  {
    id: "commercial",
    name: "Commercial & legal",
    keys: ["term_of_bid", "bid_bond_requirement", "payment_terms", "contract_or_cooperative", "additional_documentation"],
  },
  { id: "product", name: "Product & specs", keys: ["product", "model_no", "part_no", "mfg_for_registration", "product_specification"] },
  { id: "parties", name: "Parties & logistics", keys: ["company_name", "contact_info", "installation", "delivery_date"] },
  { id: "summary", name: "Summary", keys: ["bid_summary"] },
];

const OTHER: FieldGroup = { id: "other", name: "Other", keys: [] };

export type FieldEntry = [name: string, field: FieldResult];

export interface GroupedFields {
  group: FieldGroup;
  entries: FieldEntry[];
}

/** Fields in group order; keys the groups do not know go to a trailing "Other" group. */
export function groupFields(fields: Record<string, FieldResult>): GroupedFields[] {
  const byKey = new Map<string, FieldEntry>();
  for (const entry of Object.entries(fields)) byKey.set(entry[1].key, entry);
  const groups: GroupedFields[] = [];
  for (const group of FIELD_GROUPS) {
    const entries = group.keys.flatMap((k) => {
      const entry = byKey.get(k);
      if (!entry) return [];
      byKey.delete(k);
      return [entry];
    });
    if (entries.length) groups.push({ group, entries });
  }
  if (byKey.size) groups.push({ group: OTHER, entries: [...byKey.values()] });
  return groups;
}

/** Group name for a field key, for jump lists and attention summaries. */
export function groupOf(key: string): FieldGroup {
  return FIELD_GROUPS.find((g) => g.keys.includes(key)) ?? OTHER;
}
