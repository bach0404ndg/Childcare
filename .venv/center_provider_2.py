from pathlib import Path
import re
import json
import hashlib
import math
import ast

import pandas as pd


pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)
pd.set_option("display.width", None)


# ============================================================
# PATHS
# ============================================================

DATA_DIR = Path("/Users/bachnguyen/Downloads/Childcare Qualtrics")

SURVEY_CSV = (
    DATA_DIR /
    "2026 MRS-Center Providers_October 30, 2026_18.02.csv"
)

UNIVERSE_LICENSED_XLSX = (
    DATA_DIR /
    "Active Licensed Centers as of 9-14-2026.xlsx"
)

UNIVERSE_LICENSE_EXEMPT_XLSX = (
    DATA_DIR /
    "Active License-Exempt Centers as of 9-14-2026.xlsx"
)

UNIVERSE_FILES = [
    UNIVERSE_LICENSED_XLSX,
    UNIVERSE_LICENSE_EXEMPT_XLSX
]

REPORT_DIR = DATA_DIR / "response_report_oct_30_v2"

RESPONDED_XLSX = REPORT_DIR / "responded_universe_v2.xlsx"
UNRESPONDED_XLSX = REPORT_DIR / "non_responded_universe_v2.xlsx"
CLEANED_SURVEY_XLSX = REPORT_DIR / "cleaned_survey_v2.xlsx"
COUNTY_SUMMARY_PDF = REPORT_DIR / "response_rate_by_county_v2.pdf"


# ============================================================
# COLUMN MAPS
# ============================================================

SURVEY_CONTACT_COLUMNS = {
    "Q1_1": "program",
    "Q1_4": "address",
    "Q1_5": "city",
    "Q1_6": "county",
    "Q1_7": "zipcode",
    "Q1_8": "phone",
    "Q1_9": "email",
    "Q1_31": "njccid",
    "Q1_32": "id",
}


UNIVERSE_COLUMNS = {
    "Provider County": "county",
    "License Number": "id",
    "Fac Id": "fac_id",
    "Provider Type ": "type",
    "Provider Name": "program",
    "Provider Address 1": "address",
    "Provider Address 2": "address2",
    "Mailing Address1": "mailing_address",
    "Mailing Address2": "mailing_address2",
    "Provider City": "city",
    "State": "state",
    "Provider Zip Code": "zipcode",
    "Provider Phone Number": "phone",
    "Provider Email Address": "email",
}


# ============================================================
# ORIGINAL COLUMNS (for export)
# ============================================================

def get_original_survey_columns(path=SURVEY_CSV):

    df_header = pd.read_csv(
        path,
        skiprows=[1, 2],
        nrows=0
    )

    df_header = df_header.rename(
        columns=SURVEY_CONTACT_COLUMNS
    )

    return df_header.columns.tolist()


def get_original_universe_columns(path=UNIVERSE_LICENSED_XLSX):

    df_header = pd.read_excel(
        path,
        nrows=0
    )

    return df_header.columns.tolist()


def get_internal_universe_columns(path=UNIVERSE_LICENSED_XLSX):

    return [
        UNIVERSE_COLUMNS.get(
            col,
            col
        )
        for col in get_original_universe_columns(path)
    ]


def count_original_survey_responses(path=SURVEY_CSV):

    df = pd.read_csv(
        path,
        skiprows=[1, 2],
        dtype="string"
    )

    return len(df)


# ============================================================
# NORMALIZATION (preliminary cleaning, no fuzzy logic)
# ============================================================

def normalize_text(value):

    if pd.isna(value):
        return pd.NA

    cleaned = str(value).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned if cleaned else pd.NA


def normalize_email(value):

    if pd.isna(value):
        return []

    value = normalize_text(value)

    if pd.isna(value):
        return []

    emails = re.findall(
        r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}",
        value
    )

    return list(
        dict.fromkeys(emails)
    )


def normalize_phone(value):

    if pd.isna(value):
        return pd.NA

    digits = re.sub(
        r"\D",
        "",
        str(value)
    )

    return digits[-10:] if len(digits) >= 10 else pd.NA


def normalize_zipcode(value):

    if pd.isna(value):
        return pd.NA

    digits = re.sub(
        r"\D",
        "",
        str(value)
    )

    return digits[:5] if digits else pd.NA


def normalize_address(value, city=None, zipcode=None):

    if pd.isna(value):
        return pd.NA

    address = str(value).lower().strip()

    # Strip a full locality suffix only when it agrees with the separate
    # survey city and ZIP fields. Preserve unit/suite text in the street part.
    if city is not None and zipcode is not None and not pd.isna(city) and not pd.isna(zipcode):
        city_pattern = re.escape(str(city).lower().strip())
        zip_match = re.fullmatch(r"(\d{5})(?:-\d{4})?", str(zipcode).strip())
        if city_pattern and zip_match:
            address = re.sub(
                rf",\s*{city_pattern}\s*,?\s+(?:nj|new jersey)\s+{zip_match.group(1)}(?:-\d{{4}})?\s*$",
                "", address
            )

    address = re.sub(
        r"[^\w\s]",
        " ",
        address
    )

    address = re.sub(
        r"\s+",
        " ",
        address
    ).strip()

    if not address:
        return pd.NA

    address = re.sub(r"\bn\b", "north", address)
    address = re.sub(r"\bs\b", "south", address)
    address = re.sub(r"\be\b", "east", address)
    address = re.sub(r"\bw\b", "west", address)

    address = re.sub(r"\bmt\b", "mount", address)
    address = re.sub(r"\bdr\b", "drive", address)
    address = re.sub(r"\brd\b", "road", address)
    address = re.sub(r"\bst\b", "street", address)
    address = re.sub(r"\bave\b", "avenue", address)
    address = re.sub(r"\baveune\b", "avenue", address)
    address = re.sub(r"\bblvd\b", "boulevard", address)
    address = re.sub(r"\bpkwy\b", "parkway", address)

    address = re.sub(
        r"\s+",
        " ",
        address
    ).strip()

    if city is not None and not pd.isna(city):
        locality = str(city).strip().lower()
        if locality == "willingboro" and address == "110 twin hill drive":
            address = "110 twin hills drive"
        if locality in {"sicklerville", "erial"} and address == "1275 williamstown erial road":
            address = "1275 williamstown road"
    return address if address else pd.NA


def valid_address(value):

    if pd.isna(value):
        return False

    value = str(value).strip()

    if not re.search(r"\d", value):
        return False

    if not re.search(r"[a-z]", value):
        return False

    unit_words = {
        "apt",
        "apartment",
        "unit",
        "suite",
        "ste",
        "floor",
        "fl",
        "room",
        "rm",
        "building",
        "bldg"
    }

    tokens = re.findall(
        r"[a-z0-9]+",
        value
    )

    meaningful_tokens = [
        token
        for token in tokens
        if token not in unit_words
    ]

    return len(meaningful_tokens) >= 2


def exact_address_match(value_1, value_2):

    if pd.isna(value_1) or pd.isna(value_2):
        return False

    value_1 = str(value_1).strip()
    value_2 = str(value_2).strip()

    if not valid_address(value_1) or not valid_address(value_2):
        return False

    return value_1 == value_2


def normalize_id(value):

    if pd.isna(value):
        return pd.NA

    return [
        re.sub(r"[^A-Za-z0-9]", "", x).lower()
        for x in re.split(r"[;,/]+", str(value))
        if re.sub(r"[^A-Za-z0-9]", "", x)
    ]


def normalize_universe_id(value):

    ids = normalize_id(value)

    if isinstance(ids, list) and len(ids) > 0:
        return ids[0]

    return pd.NA


# ============================================================
# LOAD UNIVERSE
# ============================================================

def load_universe(paths=UNIVERSE_FILES):

    universe_parts = []

    for path in paths:

        universe_parts.append(
            pd.read_excel(
                path,
                dtype="string"
            )
        )

    df_universe = pd.concat(
        universe_parts,
        ignore_index=True
    )

    df_universe = df_universe.rename(
        columns=UNIVERSE_COLUMNS
    )

    df_universe = df_universe.replace(
        r"^\s*$",
        pd.NA,
        regex=True
    )

    # Permanent identifier for each universe provider
    df_universe["universe_row"] = df_universe.index

    for col in [
        "program",
        "address",
        "address2",
        "mailing_address",
        "mailing_address2",
        "city",
        "county",
        "email"
    ]:

        df_universe[col] = (
            df_universe[col]
            .map(normalize_text)
        )

    df_universe["new_phone"] = (
        df_universe["phone"]
        .apply(normalize_phone)
    )

    df_universe["new_email"] = (
        df_universe["email"]
        .apply(normalize_email)
    )

    df_universe["new_zipcode"] = (
        df_universe["zipcode"]
        .apply(normalize_zipcode)
    )

    df_universe["new_id"] = (
        df_universe["id"]
        .apply(normalize_universe_id)
    )

    df_universe["new_fac_id"] = (
        df_universe["fac_id"]
        .apply(normalize_universe_id)
    )

    df_universe["new_address"] = (
        df_universe["address"]
        .apply(normalize_address)
    )

    df_universe["new_address2"] = (
        df_universe["address2"]
        .apply(normalize_address)
    )

    df_universe["new_mailing_address"] = (
        df_universe["mailing_address"]
        .apply(normalize_address)
    )

    df_universe["new_mailing_address2"] = (
        df_universe["mailing_address2"]
        .apply(normalize_address)
    )

    return df_universe


# ============================================================
# LOAD SURVEY
# ============================================================

def load_survey(path=SURVEY_CSV):

    df = pd.read_csv(
        path,
        skiprows=[1, 2],
        dtype="string"
    )

    df = df.rename(
        columns=SURVEY_CONTACT_COLUMNS
    )

    df = df.replace(
        r"^\s*$",
        pd.NA,
        regex=True
    )

    contact_cols = list(
        SURVEY_CONTACT_COLUMNS.values()
    )

    # Remove rows with no useful contact information
    df = df[
        df[contact_cols]
        .notna()
        .any(axis=1)
    ].copy()

    # Count completed survey responses before helper columns
    df["response_count"] = (
        df.iloc[:, 27:]
        .notna()
        .sum(axis=1)
    )

    # Preserve original survey row
    df["survey_row"] = df.index

    return df


# ============================================================
# CLEAN SURVEY
# ============================================================

def clean_survey():

    df = load_survey()

    for col in [
        "program",
        "address",
        "email",
        "city",
        "county"
    ]:

        df[col] = (
            df[col]
            .apply(normalize_text)
        )

    df["new_phone"] = (
        df["phone"]
        .apply(normalize_phone)
    )

    df["new_email"] = (
        df["email"]
        .apply(normalize_email)
    )

    df["new_zipcode"] = (
        df["zipcode"]
        .apply(normalize_zipcode)
    )

    df["new_address"] = (
        df.apply(
            lambda row: normalize_address(row["address"], row["city"], row["zipcode"]),
            axis=1
        )
    )

    df["new_id"] = (
        df["id"]
        .apply(normalize_id)
    )

    df["new_njccid"] = (
        df["njccid"]
        .apply(normalize_id)
    )

    # A response can list more than one id (e.g. "123, 456").
    # Explode so each id gets its own matching attempt.
    df = df.explode(
        "new_id",
        ignore_index=True
    )

    return df


# ============================================================
# GENERIC UNIVERSE LOOKUP
# ============================================================

def find_universe_rows(
    value,
    df_universe,
    universe_column
):

    if pd.isna(value):
        return []

    mask = (
        df_universe[universe_column]
        .eq(value)
        .fillna(False)
    )

    return df_universe.loc[
        mask,
        "universe_row"
    ].tolist()


def find_list_rows(values, universe_series, df_universe):

    if not values:
        return []

    values = set(values)

    mask = universe_series.apply(
        lambda x: len(values & set(x)) > 0
    )

    return df_universe.loc[
        mask,
        "universe_row"
    ].tolist()


# ============================================================
# STRONG FIELD MATCH FUNCTIONS (exact match only)
# ============================================================

def match_by_id(df, df_universe):

    def find_matches(x):

        return list(set(
            find_universe_rows(x, df_universe, "new_id")
            +
            find_universe_rows(x, df_universe, "new_fac_id")
        ))

    df["id_where"] = (
        df["new_id"]
        .apply(find_matches)
    )

    df["id_match"] = (
        df["id_where"]
        .apply(len)
    )

    return df


def match_by_njccid(df, df_universe):

    def find_matches(values):

        if not isinstance(values, list):
            return []

        matches = []

        for value in values:

            matches += find_universe_rows(value, df_universe, "new_id")
            matches += find_universe_rows(value, df_universe, "new_fac_id")

        return list(
            dict.fromkeys(matches)
        )

    df["njccid_where"] = (
        df["new_njccid"]
        .apply(find_matches)
    )

    df["njccid_match"] = (
        df["njccid_where"]
        .apply(len)
    )

    return df


def match_by_program(df, df_universe):

    df["program_where"] = (
        df["program"]
        .apply(
            lambda x: find_universe_rows(x, df_universe, "program")
        )
    )

    df["program_match"] = (
        df["program_where"]
        .apply(len)
    )

    return df


def match_by_address(df, df_universe):

    def find_exact_address_rows(value):

        if pd.isna(value):
            return []

        mask = df_universe.apply(
            lambda row:
            exact_address_match(value, row["new_address"])
            or
            exact_address_match(value, row["new_address2"])
            or
            exact_address_match(value, row["new_mailing_address"])
            or
            exact_address_match(value, row["new_mailing_address2"]),
            axis=1
        )

        return df_universe.loc[
            mask,
            "universe_row"
        ].tolist()

    df["address_where"] = (
        df["new_address"]
        .apply(find_exact_address_rows)
    )

    df["address_match"] = (
        df["address_where"]
        .apply(len)
    )

    return df


def match_by_email(df, df_universe):

    df["email_where"] = (
        df["new_email"]
        .apply(
            lambda x: find_list_rows(
                x,
                df_universe["new_email"],
                df_universe
            )
        )
    )

    df["email_match"] = (
        df["email_where"]
        .apply(len)
    )

    return df


def match_by_phone(df, df_universe):

    df["phone_where"] = (
        df["new_phone"]
        .apply(
            lambda x: find_universe_rows(x, df_universe, "new_phone")
        )
    )

    df["phone_match"] = (
        df["phone_where"]
        .apply(len)
    )

    return df


# Strong fields = everything except zipcode / city / county.
STRONG_FIELDS = {
    "id": ("id_match", "id_where"),
    "njccid": ("njccid_match", "njccid_where"),
    "program": ("program_match", "program_where"),
    "address": ("address_match", "address_where"),
    "email": ("email_match", "email_where"),
    "phone": ("phone_match", "phone_where"),
}


# ============================================================
# MATCHING
# ============================================================

def advanced_program_tokens(value):
    if pd.isna(value):
        return set()
    value = re.sub(r"\bchild\s+care\b", "childcare", str(value).lower())
    stop_words = {"the", "and", "of", "at", "in", "for", "llc", "inc",
                  "corp", "corporation", "company"}
    return {token for token in re.findall(r"[a-z0-9]+", value)
            if len(token) > 1 and token not in stop_words}


def id_supported_program_agrees(survey_name, facility_name):
    """Advanced program evidence, used only with an exact identifier."""
    tokens = advanced_program_tokens(survey_name)
    other = advanced_program_tokens(facility_name)
    if len(tokens) >= 2 and len(other) >= 2:
        required = max(2, math.ceil(min(len(tokens), len(other)) * 2 / 3))
        if len(tokens & other) >= required:
            return True
    # WFC @ <school> explicitly names a school; require that school name
    # in the ID-selected facility, rather than treating WFC as evidence.
    match = re.fullmatch(r"wfc\s*@\s*(.+)", str(survey_name).strip().lower())
    if match:
        school = advanced_program_tokens(match.group(1)) - {"school", "elementary", "annex", "nj"}
        return bool(school) and school <= other
    return False


def resolve_advanced_program(row, universe):
    """Second-stage fallback: advanced name plus any exact middle field."""
    tokens = advanced_program_tokens(row.get("program"))
    eligible = {}
    if len(tokens) >= 2:
        # Tokenize the universe once; the column is reused for every response.
        if "_program_tokens" not in universe.columns:
            universe["_program_tokens"] = universe["program"].apply(advanced_program_tokens)
        for target, other in zip(universe["universe_row"], universe["_program_tokens"]):
            if len(other) < 2:
                continue
            required = max(2, math.ceil(min(len(tokens), len(other)) * 2 / 3))
            if len(tokens & other) < required:
                continue
            support = [field for field in ("address", "email", "phone")
                       if target in row[field + "_where"]]
            if support:
                eligible[target] = support
    if len(eligible) == 1:
        target, support = next(iter(eligible.items()))
        return pd.Series([target, ",".join(["advanced_program"] + support), False, pd.NA])
    reason = "multiple advanced program facilities" if eligible else "no ID match"
    return pd.Series([pd.NA, pd.NA, bool(eligible), reason])


def resolve_without_id(row, universe):
    """Require physical address, locality, and another middle field."""
    address = normalize_address(row.get("address"), row.get("city"), row.get("zipcode"))
    city = normalize_text(row.get("city"))
    zipcode = normalize_zipcode(row.get("zipcode"))
    if pd.isna(address) or pd.isna(city) or pd.isna(zipcode):
        return resolve_advanced_program(row, universe)
    eligible = {}
    same_locality = universe[
        universe["city"].eq(city) & universe["new_zipcode"].eq(zipcode)
    ]
    for _, facility in same_locality.iterrows():
        # Mailing and secondary-address lines cannot establish a physical site.
        if not exact_address_match(address, facility["new_address"]):
            continue
        target = facility["universe_row"]
        support = [f for f in ("program", "email", "phone") if target in row[f + "_where"]]
        if support:
            eligible[target] = ["address"] + support
    if len(eligible) == 1:
        target, fields = next(iter(eligible.items()))
        return pd.Series([target, ",".join(fields), False, pd.NA])
    if eligible:
        return pd.Series([pd.NA, pd.NA, True, "multiple fallback facilities"])
    return resolve_advanced_program(row, universe)


def resolve_match(row, universe=None):
    """Require two agreeing fields including an ID; shared fields count."""
    candidates = {field: set(row[where])
                  for field, (_, where) in STRONG_FIELDS.items()}
    id_sets = [candidates[f] for f in ("id", "njccid") if candidates[f]]
    if not id_sets:
        if universe is not None:
            return resolve_without_id(row, universe)
        return pd.Series([pd.NA, pd.NA, False, "no ID match"])
    eligible = set.intersection(*id_sets)
    if not eligible:
        return pd.Series([pd.NA, pd.NA, True, "conflicting IDs"])
    survey_id = normalize_id(row.get("id"))
    survey_njccid = normalize_id(row.get("njccid"))
    repeated_id = (
        isinstance(survey_id, list) and isinstance(survey_njccid, list)
        and bool(survey_id) and set(survey_id) == set(survey_njccid)
    )
    supported = {}
    for target in eligible:
        fields = [f for f, matches in candidates.items() if target in matches]
        # Preserve cross-column matching, but repeated survey IDs supply one vote.
        if repeated_id and "id" in fields and "njccid" in fields:
            fields.remove("njccid")
        if len(fields) >= 2:
            supported[target] = fields
    if len(supported) == 1:
        target, fields = next(iter(supported.items()))
        return pd.Series([target, ",".join(fields), False, pd.NA])
    # Second stage only: exact ID plus compatible advanced program evidence.
    if not supported and universe is not None:
        for target in eligible:
            facility = universe.loc[universe["universe_row"].eq(target)]
            if len(facility) == 1 and id_supported_program_agrees(
                row.get("program"), facility.iloc[0]["program"]
            ):
                fields = [field for field in ("id", "njccid") if target in candidates[field]]
                if repeated_id and "id" in fields and "njccid" in fields:
                    fields.remove("njccid")
                supported[target] = fields + ["advanced_program"]
        if len(supported) == 1:
            target, fields = next(iter(supported.items()))
            return pd.Series([target, ",".join(fields), False, pd.NA])
    reason = "multiple eligible facilities" if supported else "ID without second field"
    return pd.Series([pd.NA, pd.NA, bool(supported), reason])


MANUAL_DECISIONS = Path(__file__).resolve().parent.parent / "manual_match_decisions_v2.json"


def decision_evidence(response, facility):
    fields = ["program", "address", "city", "county", "zipcode", "phone", "email", "id"]
    evidence = {
        "survey": {f: str(response.get(f)) for f in fields + ["njccid"]},
        "facility": {f: str(facility.get(f)) for f in fields + ["fac_id"]},
    }
    return hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()


def apply_manual_decisions(df, universe):
    if not MANUAL_DECISIONS.exists():
        return df
    decisions = json.loads(MANUAL_DECISIONS.read_text())
    df["automatic_matched_row"] = df["matched_row"]
    df["automatic_conflict_type"] = df["conflict_type"]
    for index, response in df.iterrows():
        decision = decisions.get(str(response["ResponseId"]))
        if decision is None:
            continue
        targets = universe[
            universe["id"].eq(decision["license_id"])
            & universe["fac_id"].eq(decision["fac_id"])
        ]
        if len(targets) != 1 or decision_evidence(response, targets.iloc[0]) != decision["evidence"]:
            df.loc[index, "needs_manual_review"] = True
            df.loc[index, "review_reason"] = "manual decision evidence changed"
            continue
        df.loc[index, "matched_row"] = targets.iloc[0]["universe_row"]
        df.loc[index, "matched_by"] = "manual review"
        df.loc[index, "needs_manual_review"] = False
        df.loc[index, "review_reason"] = ""
    return df


MANUAL_EXCLUSIONS = Path(__file__).resolve().parent.parent / "manual_exclusions_v2.json"


def apply_manual_exclusions(df):
    if not MANUAL_EXCLUSIONS.exists():
        return df
    exclusions = json.loads(MANUAL_EXCLUSIONS.read_text())
    for index, response in df.iterrows():
        decision = exclusions.get(str(response["ResponseId"]))
        if decision is None:
            continue
        if decision_evidence(response, {}) != decision["evidence"]:
            df.loc[index, "needs_manual_review"] = True
            df.loc[index, "review_reason"] = "manual exclusion evidence changed"
            continue
        df.loc[index, "matched_row"] = pd.NA
        df.loc[index, "matched_by"] = "manual excluded"
        df.loc[index, "needs_manual_review"] = False
        df.loc[index, "review_reason"] = "reviewed excluded"
    return df


def match_all():

    df = clean_survey()
    df_universe = load_universe()

    df = match_by_id(df, df_universe)
    df = match_by_njccid(df, df_universe)
    df = match_by_program(df, df_universe)
    df = match_by_address(df, df_universe)
    df = match_by_email(df, df_universe)
    df = match_by_phone(df, df_universe)

    df[
        ["matched_row", "matched_by", "match_conflict", "conflict_type"]
    ] = df.apply(
        lambda row: resolve_match(row, df_universe),
        axis=1
    )

    df["match_warning"] = ""
    for index, response in df.iterrows():
        method = str(response["matched_by"])
        if "advanced_program" not in method or not ({"id", "njccid"} & set(method.split(","))):
            continue
        facility = df_universe.loc[df_universe["universe_row"].eq(response["matched_row"])].iloc[0]
        if not exact_address_match(response["new_address"], facility["new_address"]):
            df.loc[index, "match_warning"] = "ID + advanced program accepted; physical address differs or is incomplete"

    # Number of fields supporting matched_row, including shared fields
    df["match_field_count"] = (
        df["matched_by"]
        .fillna("")
        .apply(
            lambda value:
            len(value.split(",")) if value else 0
        )
    )

    df["id_exact_match"] = (
        df["matched_by"]
        .fillna("")
        .apply(
            lambda value:
            "id" in value.split(",")
            or "njccid" in value.split(",")
        )
    )

    df["needs_manual_review"] = (
        df["matched_row"].isna()
        | ((df["match_field_count"] < 2) & ~df["id_exact_match"])
    )
    df["review_reason"] = ""
    df.loc[df["matched_row"].isna(), "review_reason"] = df.loc[
        df["matched_row"].isna(), "conflict_type"
    ]
    df.loc[df["match_conflict"], "review_reason"] = df.loc[
        df["match_conflict"], "conflict_type"
    ]
    df.loc[
        df["matched_row"].notna() & df["needs_manual_review"],
        "review_reason"
    ] = "single non-ID field"
    df = apply_manual_decisions(df, df_universe)
    df = apply_manual_exclusions(df)
    df["review_category"] = "matched_center"
    unmatched = df["matched_row"].isna()
    df.loc[unmatched, "review_category"] = "other_review"
    df.loc[unmatched & df["review_reason"].eq("no ID match"), "review_category"] = "insufficient_evidence"
    df.loc[unmatched & df["review_reason"].eq("ID without second field"), "review_category"] = "id_without_support"
    df.loc[unmatched & df["review_reason"].isin([
        "multiple fallback facilities", "multiple advanced program facilities",
        "multiple eligible facilities"
    ]), "review_category"] = "multiple_candidates"
    df.loc[unmatched & df["review_reason"].eq("conflicting IDs"), "review_category"] = "conflicting_ids"
    df.loc[unmatched & df["review_reason"].eq("reviewed excluded"), "review_category"] = "reviewed_excluded"
    df.loc[df["review_category"].eq("insufficient_evidence"), "needs_manual_review"] = False
    return df


# ============================================================
# DUPLICATE TAGGING
# ============================================================

def tag_duplicates(df):

    df = df.copy()

    def exact_id_support(row):
        target = row["matched_row"]
        if pd.isna(target):
            return False
        for field in ("id_where", "njccid_where"):
            candidates = row[field]
            # Cached results serialize lists; accept the same evidence on reload.
            if isinstance(candidates, str):
                candidates = ast.literal_eval(candidates)
            if target in candidates:
                return True
        return False

    # Manual decisions can change the facility after the original ID flag was
    # computed. Rank only ID evidence supporting the final selected facility.
    df["id_exact_match"] = df.apply(exact_id_support, axis=1)

    sorted_df = df.sort_values(
        [
            "id_exact_match",
            "response_count",
            "survey_row"
        ],
        ascending=[
            False,
            False,
            True
        ]
    )

    sorted_df["delete_candidate"] = (
        sorted_df["matched_row"].notna()
        &
        sorted_df["matched_row"].duplicated()
    )

    df["delete_candidate"] = sorted_df["delete_candidate"]

    return df


# ============================================================
# CHECKING HELPERS
# ============================================================

def check_unmatched(df):

    df_cont = df[
        df["matched_row"].isna()
        &
        ~df["match_conflict"]
    ]

    print(
        df_cont[
            [
                "survey_row",
                "id",
                "njccid",
                "email",
                "phone",
                "address",
                "program",
                "response_count"
            ]
        ]
    )

    return df_cont


def check_conflicts(df):

    df_cont = df[
        df["match_conflict"]
    ]

    print(
        df_cont[
            [
                "survey_row",
                "id_where",
                "njccid_where",
                "program_where",
                "address_where",
                "email_where",
                "phone_where",
                "response_count"
            ]
        ]
    )

    return df_cont


def check_duplicates(df):

    duplicate_rows = df[
        df["delete_candidate"]
        |
        df["matched_row"].isin(
            df.loc[
                df["delete_candidate"],
                "matched_row"
            ]
        )
    ]

    print(
        duplicate_rows[
            [
                "matched_row",
                "survey_row",
                "id",
                "njccid",
                "matched_by",
                "id_exact_match",
                "response_count",
                "delete_candidate"
            ]
        ].sort_values(
            [
                "matched_row",
                "response_count"
            ],
            ascending=[
                True,
                False
            ]
        )
    )

    return duplicate_rows


def check_universe(universe_row):

    df_universe = load_universe()

    if not isinstance(universe_row, list):
        universe_row = [universe_row]

    result = df_universe[
        df_universe["universe_row"].isin(universe_row)
    ].copy()

    print(
        result[
            [
                "universe_row",
                "id",
                "new_id",
                "fac_id",
                "new_fac_id",
                "program",
                "address",
                "new_address",
                "city",
                "county",
                "new_zipcode",
                "new_phone",
                "email",
                "new_email"
            ]
        ]
    )

    return result


# ============================================================
# MAIN MATCHING WORKFLOW
# ============================================================

def print_match_summary(df, fcc_results):
    """Reconcile response counts before deduplication and facilities afterward."""
    center = df["matched_row"].notna()
    excluded = df["matched_by"].eq("manual excluded")
    family_rows = fcc_results.loc[fcc_results["fcc_matched_row"].notna()]
    family = ~center & ~excluded & df["ResponseId"].isin(family_rows["ResponseId"])
    matched = center
    manual = center & df["matched_by"].eq("manual review")
    unmatched = ~center & ~family
    insufficient = unmatched & df["review_reason"].eq("no ID match")
    pending = unmatched & ~excluded & ~insufficient
    center_duplicates = int((center & df["delete_candidate"]).sum())
    unique_center = df.loc[center, "matched_row"].nunique()
    values = [
        ("Total survey responses", count_original_survey_responses()),
        ("After deleting blank responses", len(load_survey())),
        ("Family-provider responses excluded", int(family.sum())),
        ("After deleting blanks and family-provider responses", len(df) - int(family.sum())),
        ("Matched with center providers", int(center.sum())),
        ("Unmatched total", int(unmatched.sum())),
        ("  Insufficient matching evidence", int(insufficient.sum())),
        ("  Reviewed exclusions", int((unmatched & excluded).sum())),
        ("  Pending manual review", int(pending.sum())),
        ("Algorithm matches", int((matched & ~manual).sum())),
        ("Manual matches", int(manual.sum())),
        ("Duplicate center responses", center_duplicates),
        ("Total uniquely matched centers", unique_center),
    ]
    assert int(center.sum() + family.sum() + unmatched.sum()) == len(df)
    assert int(center.sum()) - center_duplicates == unique_center
    assert int(manual.sum()) + int((center & ~manual).sum()) == int(center.sum())
    print("\n--- MATCH SUMMARY ---")
    for label, count in values:
        print(f"{label}: {count}")
    summary = pd.DataFrame(values, columns=["metric", "count"])
    summary.to_csv(globals().get("SUMMARY_CSV", Path(__file__).resolve().parent.parent / "response_match_summary_v2.csv"), index=False)
    return summary


def run_matching():
    df = tag_duplicates(match_all())
    # The provider entry point and audit use the same FCC second stage and summary.
    import sys
    project_dir = str(Path(__file__).resolve().parent.parent)
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    from fcc_second_stage import match_remaining_to_fcc
    from types import SimpleNamespace
    fcc_results = match_remaining_to_fcc(df, SimpleNamespace(**globals()))
    fcc_results.to_csv(Path(project_dir) / "fcc_second_stage_results_v2.csv", index=False)
    print_match_summary(df, fcc_results)
    return df


# ============================================================
# CREATE FINAL DATASETS
# ============================================================

def create_final_datasets(df):

    # Unmatched insufficient-evidence rows are report-only, including older
    # cached runs whose review flags predate that policy.
    report_only = df["matched_row"].isna() & df["review_reason"].eq("no ID match")
    if (df["needs_manual_review"] & ~report_only).any():
        raise ValueError("Pending manual reviews: run weekly_match_audit_v2.py before exporting")

    df_universe = load_universe()

    cleaned_survey = df[
        ~df["delete_candidate"]
        &
        df["matched_row"].notna()
    ].copy()

    matched_rows = (
        cleaned_survey["matched_row"]
        .drop_duplicates()
    )

    responded_universe = (
        df_universe[
            df_universe["universe_row"].isin(matched_rows)
        ]
        .copy()
    )

    unresponded_universe = (
        df_universe[
            ~df_universe["universe_row"].isin(matched_rows)
        ]
        .copy()
    )

    replace_columns = [
        "id",
        "program",
        "address",
        "city",
        "county",
        "zipcode",
        "phone",
        "email"
    ]

    universe_lookup = df_universe.set_index("universe_row")

    for col in replace_columns:

        cleaned_survey[col] = (
            cleaned_survey["matched_row"]
            .map(universe_lookup[col])
        )

    cleaned_survey["njccid"] = (
        cleaned_survey["matched_row"]
        .map(universe_lookup["fac_id"])
    )

    cleaned_survey = (
        cleaned_survey[
            get_original_survey_columns()
        ]
        .copy()
    )

    original_universe_columns = get_original_universe_columns()
    internal_universe_columns = get_internal_universe_columns()

    universe_column_names = {
        new: old
        for old, new in UNIVERSE_COLUMNS.items()
    }

    responded_universe = (
        responded_universe[internal_universe_columns]
        .rename(columns=universe_column_names)
        [original_universe_columns]
        .copy()
    )

    unresponded_universe = (
        unresponded_universe[internal_universe_columns]
        .rename(columns=universe_column_names)
        [original_universe_columns]
        .copy()
    )

    return (
        responded_universe,
        unresponded_universe,
        cleaned_survey
    )


# ============================================================
# COUNTY SUMMARY
# ============================================================

def create_county_summary(responded_universe):

    df_universe = load_universe()

    responded_county_col = "county"

    if responded_county_col not in responded_universe.columns:
        responded_county_col = "Provider County"

    total = (
        df_universe["county"]
        .value_counts()
        .rename("total")
    )

    responded = (
        responded_universe[responded_county_col]
        .value_counts()
        .rename("responded")
    )

    summary = pd.concat(
        [total, responded],
        axis=1
    ).fillna(0)

    summary["total"] = summary["total"].astype(int)
    summary["responded"] = summary["responded"].astype(int)

    summary["response_rate"] = (
        summary["responded"] / summary["total"] * 100
    ).round(2)

    summary = summary.sort_index()

    summary.loc["Total"] = [
        summary["total"].sum(),
        summary["responded"].sum(),
        round(
            summary["responded"].sum() / summary["total"].sum() * 100,
            2
        )
    ]

    return summary


def export_county_summary_pdf(
    summary,
    path=COUNTY_SUMMARY_PDF
):

    import matplotlib.pyplot as plt

    display_df = (
        summary
        .reset_index()
    )

    display_df.columns = [
        "County",
        "Total",
        "Responded",
        "Response Rate"
    ]

    # Remove .0 from counts
    display_df["Total"] = (
        display_df["Total"]
        .astype(int)
    )

    display_df["Responded"] = (
        display_df["Responded"]
        .astype(int)
    )

    display_df["Response Rate"] = (
        display_df["Response Rate"]
        .astype(str)
        +
        "%"
    )

    fig, ax = plt.subplots(
        figsize=(8.5, 11)
    )

    ax.axis("off")

    # ========================================================
    # TITLE
    # ========================================================

    ax.text(
        0.5,
        0.95,
        "Center Providers Response Rate by County",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold"
    )

    # ========================================================
    # SOURCE FILE
    # ========================================================

    ax.text(
        0.5,
        0.91,
        f"Source: {SURVEY_CSV.name}",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=9
    )

    # ========================================================
    # TABLE
    # ========================================================

    table = ax.table(
        cellText=display_df.values,
        colLabels=display_df.columns,
        cellLoc="center",
        loc="center"
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.4)

    # Highlight header
    for col in range(
        len(display_df.columns)
    ):

        cell = table[(0, col)]

        cell.set_facecolor(
            "lightgray"
        )

        cell.set_text_props(
            weight="bold"
        )

    # Highlight Total row
    last_row = len(display_df)

    for col in range(
        len(display_df.columns)
    ):

        cell = table[
            (last_row, col)
        ]

        cell.set_facecolor(
            "lightgray"
        )

        cell.set_text_props(
            weight="bold"
        )

    plt.savefig(
        path,
        format="pdf",
        bbox_inches="tight"
    )

    plt.close()


def clean_excel_sheet_name(value, used_names):

    if pd.isna(value):
        name = "Unknown County"
    else:
        name = str(value).strip()

    name = re.sub(
        r"[\[\]\:\*\?\/\\]",
        " ",
        name
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    ).strip()

    if not name:
        name = "Unknown County"

    name = name[:31]
    base_name = name
    count = 1

    while name in used_names:

        suffix = f" {count}"
        name = (
            base_name[
                :31 - len(suffix)
            ]
            +
            suffix
        )
        count += 1

    used_names.add(name)

    return name


def export_universe_by_county(
    df,
    path,
    county_col="Provider County"
):

    county_values = (
        df[county_col]
        .fillna("Unknown County")
        .astype(str)
    )

    used_names = set()

    with pd.ExcelWriter(
        path,
        engine="openpyxl"
    ) as writer:

        for county in sorted(
            county_values.unique()
        ):

            sheet_name = clean_excel_sheet_name(
                county,
                used_names
            )

            county_df = (
                df[
                    county_values == county
                ]
                .copy()
            )

            county_df.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False
            )




# ============================================================
# EXPORT FINAL FILES
# ============================================================

def export_final_files(df):

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    responded_universe, unresponded_universe, cleaned_survey = (
        create_final_datasets(df)
    )

    responded_universe.to_excel(RESPONDED_XLSX, index=False)
    export_universe_by_county(unresponded_universe, UNRESPONDED_XLSX)
    cleaned_survey.to_excel(CLEANED_SURVEY_XLSX, index=False)

    county_summary = create_county_summary(responded_universe)
    export_county_summary_pdf(county_summary)

    print("Responded universe:", RESPONDED_XLSX)
    print("Unresponded universe:", UNRESPONDED_XLSX)
    print("Cleaned survey:", CLEANED_SURVEY_XLSX)
    print("County summary:", COUNTY_SUMMARY_PDF)

    return (
        responded_universe,
        unresponded_universe,
        cleaned_survey,
        county_summary
    )


# ============================================================
# RUN
# ============================================================

RUN_MAIN = True

if __name__ == "__main__" and RUN_MAIN:

    df = run_matching()

    responded_universe, unresponded_universe, cleaned_survey, county_summary = (
        export_final_files(df)
    )

