from pathlib import Path
import re

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

REPORT_DIR = DATA_DIR / "response_report_v2"

RESPONDED_XLSX = REPORT_DIR / "responded_universe_v2.xlsx"
UNRESPONDED_XLSX = REPORT_DIR / "non_responded_universe_v2.xlsx"
CLEANED_SURVEY_XLSX = REPORT_DIR / "cleaned_survey_v2.xlsx"
COUNTY_SUMMARY_XLSX = REPORT_DIR / "response_rate_by_county_v2.xlsx"


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


def normalize_address(value):

    if pd.isna(value):
        return pd.NA

    address = str(value).lower().strip()

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
        df["address"]
        .apply(normalize_address)
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

def match_all():

    df = clean_survey()
    df_universe = load_universe()

    df = match_by_id(df, df_universe)
    df = match_by_njccid(df, df_universe)
    df = match_by_program(df, df_universe)
    df = match_by_address(df, df_universe)
    df = match_by_email(df, df_universe)
    df = match_by_phone(df, df_universe)

    def resolve_match(row):

        # A strong field only "points" at a universe row if it has
        # exactly one exact match. Fields with 0 or 2+ matches are
        # ambiguous and are ignored here.
        pointed_rows = {}

        for field, (match_col, where_col) in STRONG_FIELDS.items():

            if row[match_col] == 1:

                universe_row = row[where_col][0]

                pointed_rows.setdefault(
                    universe_row,
                    []
                ).append(field)

        if len(pointed_rows) == 0:
            return pd.Series([pd.NA, pd.NA, False, pd.NA])

        if len(pointed_rows) > 1:
            # Two different strong fields point at two different rows.
            return pd.Series([pd.NA, pd.NA, True, "different_rows"])

        universe_row, fields = next(iter(pointed_rows.items()))

        # A field with 2+ matches must still include the chosen row,
        # otherwise it disagrees with the unique match.
        for field, (match_col, where_col) in STRONG_FIELDS.items():

            if (
                row[match_col] > 1
                and universe_row not in row[where_col]
            ):
                return pd.Series([pd.NA, pd.NA, True, "ambiguous_excludes"])

        return pd.Series([universe_row, ",".join(fields), False, pd.NA])

    df[
        ["matched_row", "matched_by", "match_conflict", "conflict_type"]
    ] = df.apply(
        resolve_match,
        axis=1
    )

    # Number of strong fields that uniquely point at matched_row
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

    return df


# ============================================================
# DUPLICATE TAGGING
# ============================================================

def tag_duplicates(df):

    df = df.copy()

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

def run_matching():

    original_responses = count_original_survey_responses()
    after_deleting_blank = len(load_survey())

    df = match_all()
    df = tag_duplicates(df)

    print("\n--- MATCH SUMMARY ---")

    print("Original responses:", original_responses)
    print("After deleting blank:", after_deleting_blank)

    print(
        "Matched:",
        df["matched_row"].notna().sum()
    )

    print(
        "Conflicting strong matches (unmatched):",
        df["match_conflict"].sum()
    )

    for conflict_type in ["different_rows", "ambiguous_excludes"]:

        print(
            f"  Conflict - {conflict_type}:",
            (df["conflict_type"] == conflict_type).sum()
        )

    print(
        "No strong match (unmatched):",
        (
            df["matched_row"].isna()
            &
            ~df["match_conflict"]
        ).sum()
    )

    print(
        "Duplicate responses tagged for deletion:",
        df["delete_candidate"].sum()
    )

    print(
        "Unique universe matches:",
        df["matched_row"].nunique()
    )

    matched = df[df["matched_row"].notna()]

    print(
        "Matched by 1 field only:",
        (matched["match_field_count"] == 1).sum()
    )

    print(
        "Matched by 1 field only (no id/njccid):",
        (
            (matched["match_field_count"] == 1)
            &
            ~matched["id_exact_match"]
        ).sum()
    )

    print(
        "Matched by 2+ fields:",
        (matched["match_field_count"] >= 2).sum()
    )

    return df


# ============================================================
# CREATE FINAL DATASETS
# ============================================================

def create_final_datasets(df):

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
    unresponded_universe.to_excel(UNRESPONDED_XLSX, index=False)
    cleaned_survey.to_excel(CLEANED_SURVEY_XLSX, index=False)

    county_summary = create_county_summary(responded_universe)
    county_summary.to_excel(COUNTY_SUMMARY_XLSX)

    print("Responded universe:", RESPONDED_XLSX)
    print("Unresponded universe:", UNRESPONDED_XLSX)
    print("Cleaned survey:", CLEANED_SURVEY_XLSX)
    print("County summary:", COUNTY_SUMMARY_XLSX)

    return (
        responded_universe,
        unresponded_universe,
        cleaned_survey,
        county_summary
    )


# ============================================================
# RUN
# ============================================================

RUN_MAIN = False

if RUN_MAIN:

    df = run_matching()

    responded_universe, unresponded_universe, cleaned_survey, county_summary = (
        export_final_files(df)
    )

