"""Weekly quality check for the MRS center-provider matching results."""

import argparse
from datetime import date, datetime
from pathlib import Path
import re


LEGACY_SCRIPT = Path(__file__).parent / ".venv" / "center_provider.py"
RUN_MARKER = (
    "# ============================================================\n"
    "# RUN\n"
    "# ============================================================"
)

# Set this to a specific CSV path only if automatic discovery picks the wrong
# prior export. Otherwise, the script uses the newest survey before SURVEY_CSV.
PREVIOUS_SURVEY_CSV = None
SHOW_CONFIRMED_DUPLICATE_GROUPS = True
MIN_EXACT_SUPPORT = 2
MATCH_REVIEW_BATCH_SIZE = 20

# Manual reviews live in this ledger. A review only counts while the response
# is still matched to the same universe row it was approved against.
LEDGER_CSV = Path(__file__).parent / "reviewed_matches.csv"
# Matches from the last full run, so reviews can be recorded without
# re-running the matching.
LAST_MATCHES_CSV = Path(__file__).parent / "last_audit_matches.csv"
LEDGER_COLUMNS = [
    "ResponseId",
    "matched_row",
    "queue",
    "decision",
    "reviewed_on"
]
LEDGER_QUEUES = {
    "sensible",
    "non_id",
    "potential_majority",
    "duplicate"
}

# SEED ONLY: reviews done before the ledger existed. They are copied into
# reviewed_matches.csv the first time the audit runs; edit the ledger instead.
# These were reviewed manually. Their license ID, program, and address agree
# with the automatic match; only the entered NJCCID belongs to a sister site.
REVIEWED_SENSIBLE_RESPONSE_IDS = {
    "R_6wdUGkH6kJ0lsad",
    "R_7OL22N0kt615kc1",
    "R_32YCfmIs4H4xfvb",
    "R_7dhqIGQbOh6ls0r",
    "R_5HZxlxqFO9glasV",
    "R_3QE4it7x7MvJdgy",
    "R_14ACUdyi32XBuWl",
}

# New non-ID matches already reviewed against their survey and universe rows.
REVIEWED_NON_ID_RESPONSE_IDS = {
    "R_7Np5Og1BiV5sH2F",
    "R_3n3JeNkSxMsm2Qe",
    "R_130WwQuBXstv585",
    "R_5LUunXARfFkCaFz",
    "R_7NHPBfdRGkqBjD6",
    "R_5BpTyN5oPYiJ7iN",
    "R_74OdhEpgpwgi7Xq",
    "R_51oXf7fIGGoqW7l",
    "R_6ig1Q2qVWVfnWe5",
    "R_3uUwkkSUoTxFmeo",
    "R_33fIIWSGgv3KxWi",
    "R_1C7StIDnbZbFnok",
    "R_7yrAdQRbBcXio9g",
    "R_1RlSu3VGcgOs2qd",
    "R_3gqFvOsyavaU0C0",
    "R_71AX62Rc9xjqeEq",
    "R_5oSfP2wLvnsxY4v",
}

REVIEWED_DUPLICATE_RESPONSE_IDS = {
    "R_1cpYp9M7WiTQYm5",
    "R_3Q9FcErjdd4BEBM",
    "R_3SJurND13f4rmLv",
    "R_73qMGdDGJbcFbO1",
    "R_3HjGFGmPXyC7Wp1",
    "R_5ekRxxZoE4uffJS",
}


legacy_source = LEGACY_SCRIPT.read_text()

if RUN_MARKER not in legacy_source:
    raise RuntimeError("Could not find the RUN section in center_provider.py")

exec(
    compile(
        legacy_source.split(RUN_MARKER, 1)[0],
        str(LEGACY_SCRIPT),
        "exec"
    ),
    globals()
)


def survey_export_time(path):

    match = re.search(
        r"_([A-Za-z]+ \d{1,2}, \d{4})_(\d{1,2}\.\d{2})\.csv$",
        path.name
    )

    if match is None:
        return None

    return datetime.strptime(
        f"{match.group(1)} {match.group(2)}",
        "%B %d, %Y %H.%M"
    )


def find_previous_survey():

    if PREVIOUS_SURVEY_CSV is not None:
        return Path(PREVIOUS_SURVEY_CSV)

    current_time = survey_export_time(SURVEY_CSV)

    if current_time is None:
        return None

    candidates = []

    for path in DATA_DIR.glob("2026 MRS-Center Providers_*.csv"):

        export_time = survey_export_time(path)

        if export_time is not None and export_time < current_time:
            candidates.append((export_time, path))

    if len(candidates) == 0:
        return None

    return max(candidates)[1]


def run_current_matching():

    df = match_all()

    df_cont = resolve_duplicates(df)
    df = map_df_cont_back(df, df_cont)

    df_cont = resolve_by_potential_count(df)
    df = map_df_cont_back(df, df_cont)

    df = apply_manual_unmatched(df)

    return tag_duplicates(df)


def as_list(value):
    return value if isinstance(value, list) else []


STRONG_METHODS = {
    "id",
    "njccid",
    "program",
    "address",
    "email",
    "phone"
}


def row_key(value):
    return None if pd.isna(value) else int(value)


def load_ledger():

    if not LEDGER_CSV.exists():
        return pd.DataFrame(columns=LEDGER_COLUMNS)

    return pd.read_csv(LEDGER_CSV, dtype={"ResponseId": str})


def reviewed_pairs(queues=None, exclude_queues=()):
    """(ResponseId, matched_row) pairs approved in the ledger."""

    ledger = load_ledger()
    ledger = ledger[~ledger["queue"].isin(exclude_queues)]

    if queues is not None:
        ledger = ledger[ledger["queue"].isin(queues)]

    return {
        (response_id, int(matched_row))
        for response_id, matched_row in zip(
            ledger["ResponseId"],
            ledger["matched_row"]
        )
    }


def reviewed_mask(df):
    """Rows whose current match was already reviewed (or manually set)."""

    pairs = reviewed_pairs()

    in_ledger = pd.Series(
        [
            (str(response_id), row_key(matched_row)) in pairs
            for response_id, matched_row in zip(
                df["ResponseId"],
                df["matched_row"]
            )
        ],
        index=df.index
    )

    return in_ledger | df["ResponseId"].astype(str).isin(
        MANUAL_MATCH_OVERRIDES
    )


def append_to_ledger(entries):

    ledger = load_ledger()
    existing = {
        (row.ResponseId, int(row.matched_row), row.queue)
        for row in ledger.itertuples()
    }
    new_rows = [
        entry for entry in entries
        if (entry["ResponseId"], entry["matched_row"], entry["queue"])
        not in existing
    ]

    if len(new_rows) > 0:
        pd.concat(
            [ledger, pd.DataFrame(new_rows, columns=LEDGER_COLUMNS)],
            ignore_index=True
        ).to_csv(LEDGER_CSV, index=False)

    return len(new_rows)


def ledger_entries(df, response_ids, queue, decision="approved"):

    entries = []

    for response_id in dict.fromkeys(map(str, response_ids)):

        rows = df.loc[
            df["ResponseId"].astype(str).eq(response_id)
            & df["matched_row"].notna(),
            "matched_row"
        ]

        if len(rows) == 0:
            print(f"Not reviewed (no current match): {response_id}")
            continue

        entries.append({
            "ResponseId": response_id,
            "matched_row": row_key(rows.iloc[0]),
            "queue": queue,
            "decision": decision,
            "reviewed_on": date.today().isoformat()
        })

    return entries


def seed_ledger(df):

    entries = []

    for queue, response_ids in [
        ("sensible", REVIEWED_SENSIBLE_RESPONSE_IDS),
        ("non_id", REVIEWED_NON_ID_RESPONSE_IDS),
        ("duplicate", REVIEWED_DUPLICATE_RESPONSE_IDS),
    ]:
        entries += ledger_entries(
            df,
            sorted(response_ids),
            queue,
            decision="seeded"
        )

    added = append_to_ledger(entries)
    print(f"Seeded {LEDGER_CSV.name} with {added} prior reviews.")


def week_label(response_id, new_response_ids):
    return "new" if str(response_id) in new_response_ids else "existing"


def valid_survey_rows(df):
    return ~df.get(
        "split_extra_row",
        pd.Series(False, index=df.index)
    )


def suspicious_automatic_matches(df):

    exact_where_columns = {
        "id": "id_where",
        "njccid": "njccid_where",
        "program": "program_where",
        "address": "address_where",
        "email": "email_where",
        "phone": "phone_where",
    }
    id_where_columns = {
        "id": "id_where",
        "njccid": "njccid_where",
        "advanced_id": "advanced_id_where",
    }

    findings = []
    df = df.assign(already_reviewed=reviewed_mask(df))

    for _, row in df.iterrows():

        response_id = str(row["ResponseId"])
        matched_row = row.get("matched_row")
        matched_by = row.get("matched_by")

        if (
            pd.isna(matched_row)
            or matched_by not in STRONG_METHODS
            or row["already_reviewed"]
        ):
            continue

        support = []
        conflicts = {}

        for label, where_column in exact_where_columns.items():

            candidates = as_list(row.get(where_column))

            if len(candidates) == 1:
                candidate = candidates[0]

                if candidate == matched_row:
                    support.append(label)
                else:
                    conflicts[label] = [candidate]

        # ID-type evidence is a hard warning whenever it identifies any
        # universe row other than the selected match, even when ambiguous.
        for label, where_column in id_where_columns.items():

            alternate_rows = [
                candidate
                for candidate in dict.fromkeys(
                    as_list(row.get(where_column))
                )
                if candidate != matched_row
            ]

            if len(alternate_rows) > 0:
                conflicts[label] = list(dict.fromkeys(
                    conflicts.get(label, []) + alternate_rows
                ))

        id_conflict_labels = set(id_where_columns).intersection(conflicts)
        non_id_conflicts = {
            label: candidates
            for label, candidates in conflicts.items()
            if label not in id_where_columns
        }

        # Two exact supports pass only with no conflicts. Three or more exact
        # supports may override an ID-type conflict, but not another exact
        # field that uniquely identifies a different universe row.
        if (
            len(support) >= 3
            and len(non_id_conflicts) == 0
        ) or (
            len(support) >= MIN_EXACT_SUPPORT
            and len(conflicts) == 0
        ):
            continue

        alternate_counts = {}

        for candidates in conflicts.values():
            for candidate in candidates:
                alternate_counts[candidate] = (
                    alternate_counts.get(candidate, 0) + 1
                )

        suggested_row = (
            max(alternate_counts, key=alternate_counts.get)
            if len(alternate_counts) > 0
            else pd.NA
        )
        issue = (
            "conflicting ID-type identifier"
            if len(id_conflict_labels) > 0
            else "conflicting exact identifier"
            if len(conflicts) > 0
            else f"only {len(support)} unique exact identifiers"
        )

        findings.append({
            "survey_row": row["survey_row"],
            "ResponseId": row["ResponseId"],
            "automatic_by": matched_by,
            "automatic_row": matched_row,
            "current_row": matched_row,
            "suggested_row": suggested_row,
            "issue": issue,
            "evidence": ", ".join(support) or "none",
            "support_count": len(support),
            "conflicts": ", ".join(
                f"{label}->{candidates}"
                for label, candidates in conflicts.items()
            ) or "none",
            "has_conflict": len(conflicts) > 0,
            "resolved": False,
            "program": row["program"],
            "address": row["address"],
            "id": row["id"],
            "njccid": row["njccid"],
        })

    return pd.DataFrame(findings)


def print_rate(label, numerator, denominator):

    rate = 0 if denominator == 0 else numerator / denominator * 100

    print(
        f"{label}: {numerator}/{denominator} ({rate:.1f}%)"
    )


def print_weekly_summary(df, previous_path):

    original_count = count_original_survey_responses()
    usable = load_survey()
    usable_count = len(usable)

    valid_rows = valid_survey_rows(df)

    matched_count = (
        df["matched_row"].notna()
        & valid_rows
    ).sum()

    unmatched_count = (
        df["matched_row"].isna()
        & valid_rows
    ).sum()

    print("\n--- WEEKLY MATCH AUDIT ---")
    print("Current survey:", SURVEY_CSV.name)
    print("Previous survey:", previous_path.name if previous_path else "not found")
    print("Original responses:", original_count)
    print_rate("Usable responses", usable_count, original_count)
    print_rate("Matched usable rows", matched_count, usable_count)
    print("Unmatched usable rows:", unmatched_count)
    print("Dropped duplicate rows:", int(df["delete_candidate"].sum()))
    print_rate(
        "Unique universe matches",
        df["matched_row"].nunique(),
        usable_count
    )

    new_response_ids = set()

    if previous_path is not None:

        previous_ids = set(
            load_survey(previous_path)["ResponseId"]
            .dropna()
            .astype(str)
        )

        current_ids = set(
            usable["ResponseId"]
            .dropna()
            .astype(str)
        )

        new_response_ids = current_ids - previous_ids
        new_mask = df["ResponseId"].astype(str).isin(new_response_ids)
        old_matched_rows = set(
            df.loc[
                ~new_mask & df["matched_row"].notna(),
                "matched_row"
            ]
        )
        new_matched_rows = set(
            df.loc[
                new_mask & df["matched_row"].notna(),
                "matched_row"
            ]
        )

        print("New usable responses:", len(new_response_ids))
        print(
            "Newly represented universe rows:",
            len(new_matched_rows - old_matched_rows)
        )
        print(
            "New responses dropped as duplicates:",
            df.loc[
                new_mask & df["delete_candidate"],
                "ResponseId"
            ].nunique()
        )

    print("\n--- MATCHED BY ---")
    print(
        df.loc[df["matched_row"].notna(), "matched_by"]
        .value_counts()
        .to_string()
    )

    return new_response_ids


def print_suspicious_matches(df, findings, new_response_ids):

    print("\n--- CONSERVATIVE EXACT-MATCH REVIEW ---")
    print("Required unique exact identifiers:", MIN_EXACT_SUPPORT)
    print("Matches needing manual review:", len(findings))

    if len(findings) == 0:
        print("None.")
        return

    findings = findings.copy()
    findings["new_this_week"] = (
        findings["ResponseId"]
        .astype(str)
        .isin(new_response_ids)
    )
    findings = findings.sort_values(
        [
            "has_conflict",
            "support_count",
            "survey_row"
        ],
        ascending=[False, True, True]
    )

    universe = load_universe().set_index(
        "universe_row",
        drop=False
    )

    print(
        "Showing next review batch:",
        min(MATCH_REVIEW_BATCH_SIZE, len(findings))
    )

    for _, finding in findings.head(MATCH_REVIEW_BATCH_SIZE).iterrows():

        week = "new" if finding["new_this_week"] else "existing"
        matched = universe.loc[finding["current_row"]]

        print(
            f"\nSurvey {finding['survey_row']} "
            f"({week}, {finding['ResponseId']}): "
            f"{finding['automatic_by']} -> {finding['current_row']} | "
            f"{finding['support_count']}/{MIN_EXACT_SUPPORT} exact "
            f"[{finding['evidence']}] | conflicts [{finding['conflicts']}]"
        )
        print(
            f"  Survey: {finding['program']} | {finding['address']} | "
            f"ID {finding['id']} | NJCCID {finding['njccid']}"
        )
        print(
            f"  Matched universe: {matched['program']} | "
            f"{matched['address']} | ID {matched['id']} | "
            f"Fac ID {matched['fac_id']}"
        )

        if pd.notna(finding["suggested_row"]):
            suggested = universe.loc[finding["suggested_row"]]
            print(
                f"  Conflicting universe {finding['suggested_row']}: "
                f"{suggested['program']} | {suggested['address']} | "
                f"ID {suggested['id']} | Fac ID {suggested['fac_id']}"
            )


def print_new_non_id_review_queue(df, new_response_ids):

    review_mask = (
        df["matched_row"].notna()
        & ~df["matched_by"].isin(STRONG_METHODS)
        & ~df["matched_by"].isin({"manual review", "manual rejected"})
        & ~df["matched_by"].eq("potential majority")
        & ~reviewed_mask(df)
    )

    review = df.loc[
        review_mask,
        [
            "survey_row",
            "ResponseId",
            "matched_row",
            "matched_by",
            "program",
            "address",
            "id",
            "njccid"
        ]
    ].drop_duplicates(
        subset=["ResponseId", "matched_row"]
    )

    print("\n--- WEAK-METHOD MANUAL REVIEW QUEUE ---")
    print("Unreviewed weak-method matches:", len(review))

    if len(review) == 0:
        print("None.")
        return review

    print("\nBy method:")
    print(
        review["matched_by"]
        .value_counts()
        .to_string()
    )

    for _, row in review.sort_values("survey_row").iterrows():
        week = week_label(row["ResponseId"], new_response_ids)
        print(
            f"Survey {row['survey_row']} ({week}, {row['ResponseId']}): "
            f"{row['matched_by']} -> "
            f"{row['matched_row']} | {row['program']} | {row['address']} | "
            f"ID {row['id']} | NJCCID {row['njccid']}"
        )

    return review


def print_potential_majority_review_queue(df, new_response_ids):

    review_mask = (
        df["matched_row"].notna()
        & df["matched_by"].eq("potential majority")
        & ~reviewed_mask(df)
    )
    review = df.loc[
        review_mask,
        [
            "survey_row",
            "ResponseId",
            "matched_row",
            "program",
            "address",
            "id",
            "njccid",
            "potential",
            "narrower_least_match"
        ]
    ].drop_duplicates(
        subset=["ResponseId", "matched_row"]
    )

    print("\n--- POTENTIAL MAJORITY MANUAL REVIEW QUEUE ---")
    print("Unreviewed potential-majority matches:", len(review))

    if len(review) == 0:
        print("None.")
        return review

    for _, row in review.sort_values("survey_row").iterrows():
        week = week_label(row["ResponseId"], new_response_ids)
        print(
            f"Survey {row['survey_row']} ({week}, {row['ResponseId']}): "
            f"potential majority -> "
            f"{row['matched_row']} | {row['program']} | {row['address']} | "
            f"ID {row['id']} | NJCCID {row['njccid']} | "
            f"potential {row['potential']} | narrowed "
            f"{row['narrower_least_match']}"
        )

    return review


def duplicate_row_evidence(row, matched_row):

    evidence = []

    if matched_row in as_list(row.get("id_where")):
        evidence.append("id")

    if matched_row in as_list(row.get("njccid_where")):
        evidence.append("njccid")

    for label in [
        "program",
        "address",
        "email",
        "phone"
    ]:

        if matched_row in as_list(row.get(f"{label}_where")):
            evidence.append(label)

    return evidence


def print_new_duplicate_review_queue(
    df,
    new_response_ids,
    suspicious_findings
):

    reviewed_match_pairs = reviewed_pairs(exclude_queues=["duplicate"])
    reviewed_duplicate_pairs = reviewed_pairs(queues=["duplicate"])

    unresolved_conflict_ids = set()

    if len(suspicious_findings) > 0:
        unresolved_conflict_ids = set(
            suspicious_findings.loc[
                ~suspicious_findings["resolved"].astype(bool),
                "ResponseId"
            ]
            .dropna()
            .astype(str)
        )

    valid_rows = valid_survey_rows(df)
    matched = df.loc[
        valid_rows & df["matched_row"].notna()
    ].copy()

    response_counts = (
        matched.groupby("matched_row")["ResponseId"]
        .nunique()
    )
    duplicate_rows = set(
        response_counts[response_counts > 1].index
    )
    duplicate_groups = matched[
        matched["matched_row"].isin(duplicate_rows)
    ]

    new_duplicate_rows = []

    for matched_row, group in duplicate_groups.groupby("matched_row"):

        response_ids = set(
            group["ResponseId"]
            .dropna()
            .astype(str)
        )

        if {
            (response_id, row_key(matched_row))
            for response_id in response_ids
        }.issubset(reviewed_duplicate_pairs):
            continue

        if group["ResponseId"].astype(str).isin(new_response_ids).any():
            new_duplicate_rows.append((matched_row, group))

    universe = load_universe().set_index(
        "universe_row",
        drop=False
    )
    reviewed_groups = []

    for matched_row, group in new_duplicate_rows:

        responses = group.drop_duplicates(
            subset="ResponseId"
        ).copy()
        conflict_response_ids = set(
            responses["ResponseId"]
            .dropna()
            .astype(str)
        ) & unresolved_conflict_ids
        unsafe_response_ids = set()
        response_evidence = []

        for _, row in responses.iterrows():

            evidence = duplicate_row_evidence(
                row,
                matched_row
            )
            exact_identifier = (
                "id" in evidence
                or "njccid" in evidence
            )
            detail_count = len(
                set(evidence)
                & {
                    "program",
                    "address",
                    "email",
                    "phone"
                }
            )
            exact_support_count = sum(
                len(as_list(row.get(f"{label}_where"))) == 1
                and as_list(row.get(f"{label}_where"))[0] == matched_row
                for label in [
                    "id",
                    "njccid",
                    "program",
                    "address",
                    "email",
                    "phone"
                ]
            )
            response_id = str(row["ResponseId"])
            reviewed_match = (
                row["matched_by"] == "manual review"
                or (response_id, row_key(matched_row))
                in reviewed_match_pairs
                or response_id in MANUAL_MATCH_OVERRIDES
            )
            safe_match = (
                reviewed_match
                or exact_support_count >= MIN_EXACT_SUPPORT
            )

            if not safe_match:
                unsafe_response_ids.add(response_id)

            response_evidence.append({
                "row": row,
                "evidence": evidence,
                "exact_identifier": exact_identifier,
                "has_facility_detail": detail_count >= 1,
                "exact_support_count": exact_support_count,
                "reviewed_match": reviewed_match,
                "safe_match": safe_match,
                "supported": (
                    exact_identifier and detail_count >= 1
                ) or detail_count >= 2
            })

        if len(conflict_response_ids) > 0:
            status = "match conflict - review first"
        elif len(unsafe_response_ids) > 0:
            status = "unsafe match - review first"
        elif all(
            x["exact_identifier"] and x["has_facility_detail"]
            for x in response_evidence
        ):
            status = "same facility from IDs"
        elif all(
            x["supported"]
            for x in response_evidence
        ):
            status = "same facility from details"
        else:
            status = "needs manual review"

        reviewed_groups.append({
            "matched_row": matched_row,
            "status": status,
            "conflict_response_ids": conflict_response_ids,
            "unsafe_response_ids": unsafe_response_ids,
            "responses": response_evidence
        })

    print("\n--- NEW DUPLICATE REVIEW QUEUE ---")
    print(
        "Duplicate groups touched by new responses:",
        len(reviewed_groups)
    )
    print(
        "Confirmed from IDs:",
        sum(
            group["status"] == "same facility from IDs"
            for group in reviewed_groups
        )
    )
    print(
        "Supported by facility details:",
        sum(
            group["status"] == "same facility from details"
            for group in reviewed_groups
        )
    )
    print(
        "Needs manual review:",
        sum(
            group["status"] == "needs manual review"
            for group in reviewed_groups
        )
    )
    print(
        "Blocked by unresolved match conflicts:",
        sum(
            group["status"] == "match conflict - review first"
            for group in reviewed_groups
        )
    )
    print(
        "Blocked by unsafe/unreviewed matches:",
        sum(
            group["status"] == "unsafe match - review first"
            for group in reviewed_groups
        )
    )

    for group in reviewed_groups:

        if (
            group["status"] not in {
                "needs manual review",
                "match conflict - review first",
                "unsafe match - review first"
            }
            and not SHOW_CONFIRMED_DUPLICATE_GROUPS
        ):
            continue

        universe_row = universe.loc[group["matched_row"]]

        print(
            f"\nUniverse {group['matched_row']} "
            f"({group['status']}): {universe_row['program']} | "
            f"ID {universe_row['id']} | Fac ID {universe_row['fac_id']} | "
            f"{universe_row['address']}"
        )

        for item in sorted(
            group["responses"],
            key=lambda value: bool(value["row"]["delete_candidate"])
        ):

            row = item["row"]
            week = week_label(row["ResponseId"], new_response_ids)
            decision = (
                "drop"
                if row["delete_candidate"]
                else "keep"
            )

            print(
                f"  Survey {row['survey_row']} "
                f"({week}, {decision}, {row['ResponseId']}): "
                f"{row['matched_by']} | evidence "
                f"{', '.join(item['evidence']) or 'none'} | "
                f"reason {row['delete_reason']}"
            )
            print(
                f"    {row['program']} | {row['address']} | "
                f"ID {row['id']} | NJCCID {row['njccid']} | "
                f"{row['email']} | {row['phone']}"
            )


def parse_args():

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approve",
        nargs="+",
        metavar=("QUEUE", "RESPONSE_ID"),
        help=(
            "record reviews in the ledger: queue name ("
            + ", ".join(sorted(LEDGER_QUEUES))
            + ") followed by one or more ResponseIds"
        )
    )

    parser.add_argument(
        "--ledger-only",
        action="store_true",
        help=(
            "with --approve: record reviews against the matches saved by the "
            "last full run, without re-running the matching"
        )
    )

    return parser.parse_args()


def main():

    args = parse_args()

    if args.approve and (
        args.approve[0] not in LEDGER_QUEUES or len(args.approve) < 2
    ):
        raise SystemExit(
            f"--approve needs a queue from {sorted(LEDGER_QUEUES)} "
            "and at least one ResponseId"
        )

    if args.ledger_only:

        if not args.approve:
            raise SystemExit("--ledger-only needs --approve")

        if not LAST_MATCHES_CSV.exists():
            raise SystemExit(
                f"{LAST_MATCHES_CSV.name} not found; run the full audit once"
            )

        saved = pd.read_csv(LAST_MATCHES_CSV, dtype={"ResponseId": str})
        saved_at = datetime.fromtimestamp(LAST_MATCHES_CSV.stat().st_mtime)
        added = append_to_ledger(
            ledger_entries(saved, args.approve[1:], args.approve[0])
        )
        print(
            f"Recorded {added} reviews in {LEDGER_CSV.name} "
            f"(matches from {saved_at:%Y-%m-%d %H:%M})."
        )
        return None, None

    previous_path = find_previous_survey()
    df = run_current_matching()

    df[["ResponseId", "matched_row"]].to_csv(LAST_MATCHES_CSV, index=False)

    if not LEDGER_CSV.exists():
        seed_ledger(df)

    if args.approve:
        added = append_to_ledger(
            ledger_entries(df, args.approve[1:], args.approve[0])
        )
        print(f"Recorded {added} reviews in {LEDGER_CSV.name}.")

    new_response_ids = print_weekly_summary(
        df,
        previous_path
    )
    findings = suspicious_automatic_matches(df)
    print_suspicious_matches(
        df,
        findings,
        new_response_ids
    )
    non_id_review = print_new_non_id_review_queue(
        df,
        new_response_ids
    )
    unresolved_findings = findings[
        ~findings["resolved"].astype(bool)
    ] if len(findings) > 0 else findings

    if len(unresolved_findings) > 0 or len(non_id_review) > 0:
        print("\n--- POTENTIAL MAJORITY MANUAL REVIEW QUEUE ---")
        print(
            "Paused until suspicious and direct non-ID matches are reviewed."
        )
        print("\n--- NEW DUPLICATE REVIEW QUEUE ---")
        print(
            "Paused until all match warnings are reviewed: "
            f"{len(unresolved_findings)} suspicious matches and "
            f"{len(non_id_review)} new non-ID matches remain."
        )
    else:
        potential_review = print_potential_majority_review_queue(
            df,
            new_response_ids
        )

        if len(potential_review) > 0:
            print("\n--- NEW DUPLICATE REVIEW QUEUE ---")
            print(
                "Paused until all potential-majority matches are reviewed: "
                f"{len(potential_review)} remain."
            )
        else:
            print_new_duplicate_review_queue(
                df,
                new_response_ids,
                findings
            )

    return df, findings


if __name__ == "__main__":
    df_audit, suspicious_matches = main()
