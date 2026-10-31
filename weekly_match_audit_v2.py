"""Review queue for center_provider_2; isolated from the legacy MRS/NCA audits."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("center_provider_2", ROOT / ".venv/center_provider_2.py")
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)
LEDGER = ROOT / "reviewed_matches_v2.csv"
CACHE = ROOT / "last_audit_matches_v2.csv"

STATUS_REPORT_CSV = ROOT / "match_status_report_v2.csv"
REVIEW_QUEUE_CSV = ROOT / "manual_review_queue_v2.csv"
STATUS_SUMMARY_CSV = ROOT / "match_status_summary_v2.csv"
FCC_RESULTS_CSV = ROOT / "fcc_second_stage_results_v2.csv"


def fingerprint(row, universe):
    # Include all response evidence and the entire selected facility record.
    evidence = {str(k): str(v) for k, v in row.items()
                if k not in {"needs_manual_review", "review_reason"}}
    target = row["matched_row"]
    evidence["facility"] = (universe.loc[universe.universe_row.eq(target)]
                            .astype(str).to_dict("records"))
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


def report_review_categories(df, fcc_results):
    """Report unmatched evidence without putting it in the manual queue."""
    report = df.copy()
    unmatched = report.matched_row.isna()
    report["review_category"] = "matched_center"
    report.loc[unmatched, "review_category"] = "other_review"
    reasons = {
        "reviewed excluded": "reviewed_excluded",
        "no ID match": "insufficient_evidence",
        "ID without second field": "id_without_support",
        "conflicting IDs": "conflicting_ids",
        "multiple fallback facilities": "multiple_candidates",
        "multiple advanced program facilities": "multiple_candidates",
        "multiple eligible facilities": "multiple_candidates",
    }
    for reason, category in reasons.items():
        report.loc[unmatched & report.review_reason.eq(reason), "review_category"] = category
    report["center_review_category"] = report["review_category"]
    fcc_matches = fcc_results[fcc_results.fcc_matched_row.notna()]
    if fcc_matches.ResponseId.duplicated().any():
        raise ValueError("Multiple FCC results for a response require review")
    lookup = fcc_matches.set_index("ResponseId")
    for field in ["fcc_matched_row", "fcc_matched_by", "fcc_id", "fcc_fac_id", "fcc_program"]:
        report[field] = report.ResponseId.map(lookup[field])
    report.loc[unmatched & report.fcc_matched_row.notna() & ~report.review_category.eq("reviewed_excluded"), "review_category"] = "excluded_family_provider"
    # Family-provider matches stay separate from center rows and denominators.
    report["manual_review_required"] = report.review_category.isin([
        "id_without_support", "multiple_candidates", "conflicting_ids", "other_review"])
    report.to_csv(STATUS_REPORT_CSV, index=False)
    report[report.manual_review_required].to_csv(REVIEW_QUEUE_CSV, index=False)
    summary = report.review_category.value_counts().rename_axis("category").reset_index(name="responses")
    summary.to_csv(STATUS_SUMMARY_CSV, index=False)
    print(summary.to_string(index=False))
    print("Family-provider responses excluded:", int(report.review_category.eq("excluded_family_provider").sum()))
    print("Insufficient matching evidence:", int(report.review_category.eq("insufficient_evidence").sum()))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", nargs="+", default=[])
    parser.add_argument("--ledger-only", action="store_true")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    ledger = (pd.read_csv(LEDGER, dtype=str) if LEDGER.exists()
              else pd.DataFrame(columns=["ResponseId", "fingerprint"]))
    if args.ledger_only:
        if not args.approve or args.export:
            parser.error("--ledger-only requires --approve and cannot export")
        df = pd.read_csv(CACHE, dtype=str)
    else:
        df = provider.tag_duplicates(provider.match_all())
        universe = provider.load_universe()
        df["fingerprint"] = df.apply(lambda row: fingerprint(row, universe), axis=1)
        df.to_csv(CACHE, index=False)
    if args.approve:
        selected = df[df.ResponseId.isin(args.approve)]
        missing = set(args.approve) - set(selected.ResponseId)
        if missing:
            parser.error(f"Unknown response IDs: {sorted(missing)}")
        if selected.matched_row.isna().any():
            parser.error("Unmatched/conflicting responses require correcting the source evidence first")
        ledger = pd.concat([ledger, selected[["ResponseId", "fingerprint"]]]).drop_duplicates()
        ledger.to_csv(LEDGER, index=False)
    if args.ledger_only:
        print("Reviews recorded from the cached run; next full run validates current evidence.")
        return
    approved = set(map(tuple, ledger[["ResponseId", "fingerprint"]].values))
    df["needs_manual_review"] &= ~pd.Series(
        [(r.ResponseId, r.fingerprint) in approved for r in df.itertuples()], index=df.index)
    from fcc_second_stage import match_remaining_to_fcc
    fcc_results = match_remaining_to_fcc(df, provider)
    fcc_results.to_csv(FCC_RESULTS_CSV, index=False)
    provider.print_match_summary(df, fcc_results)
    status_report = report_review_categories(df, fcc_results)
    pending = status_report[status_report.manual_review_required]
    print(f"Pending manual reviews: {len(pending)}")
    print(pending[["ResponseId", "program", "matched_row", "review_reason"]].head(20).to_string(index=False))
    if args.export:
        provider.export_final_files(df)
    return df


if __name__ == "__main__":
    main()
