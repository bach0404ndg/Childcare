"""Match Narrow Cost Survey center-provider responses to the NCA universe."""

from pathlib import Path


# Reuse the established matching rules without running the original script.
LEGACY_SCRIPT = Path(__file__).parent / ".venv" / "center_provider_2.py"
RUN_MARKER = (
    "# ============================================================\n"
    "# RUN\n"
    "# ============================================================"
)

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

# Keep NCA paths, mappings and decisions separate from the MRS workflow.
STANDARD_UNIVERSE_COLUMNS = UNIVERSE_COLUMNS.copy()
PROJECT_DIR = Path(__file__).resolve().parent
MANUAL_DECISIONS = PROJECT_DIR / "manual_match_decisions_nca.json"
MANUAL_EXCLUSIONS = PROJECT_DIR / "manual_exclusions_nca.json"
SUMMARY_CSV = PROJECT_DIR / "response_match_summary_nca.csv"
FCC_UNIVERSE_PATH = Path("/Users/bachnguyen/Downloads/Childcare Qualtrics/Active FCC Providers as of 9-14-2026.xlsx")
MANUAL_MATCH_OVERRIDES = {}
MANUAL_UNMATCHED_RESPONSE_IDS = {
    # Only the generic program name matched a different Goddard facility.
    "R_1DDKuDicwShbxBL",
}


# ============================================================
# NCA PATHS
# ============================================================

DATA_DIR = Path("/Users/bachnguyen/Downloads/Childcare Qualtrics/NCA")

SURVEY_CSV = (
    DATA_DIR /
    "2026 Narrow Cost Survey: Center Providers_October 30, 2026_18.09.csv"
)

UNIVERSE_XLSX = (
    DATA_DIR /
    "Center_NCA_Universe_Reconciled_10.30.2026 (N=421).xlsx"
)

UNIVERSE_FILES = [UNIVERSE_XLSX]

REPORT_DIR = DATA_DIR / "response_report_nca_oct_30"

RESPONDED_XLSX = REPORT_DIR / "responded_universe.xlsx"
UNRESPONDED_XLSX = REPORT_DIR / "non_responded_universe.xlsx"
CLEANED_SURVEY_XLSX = REPORT_DIR / "cleaned_survey.xlsx"
COUNTY_SUMMARY_PDF = REPORT_DIR / "response_rate_by_county.pdf"


# ============================================================
# NCA COLUMN MAPS
# ============================================================

SURVEY_CONTACT_COLUMNS = {
    "Q1_1": "program",
    "Q1_2": "address",
    "Q1_4": "city",
    "Q1_5": "county",
    "Q1_6": "zipcode",
    "Q1_7": "phone",
    "Q1_8": "email",
    "Q1_9": "njccid",
    "Q1_10": "id",
}

UNIVERSE_COLUMNS = {
    "name": "program",
    "address": "address",
    "city": "city",
    "county": "county",
    "zipcode": "zipcode",
    "phone": "phone",
    "email": "email",
    "njccid": "fac_id",
    "licenseid": "id",
    "NCA_Participation": "NCA_Participation",
}


# ============================================================
# NCA LOADERS
# ============================================================

def get_original_survey_columns(path=None):

    if path is None:
        path = SURVEY_CSV

    df_header = pd.read_csv(
        path,
        skiprows=[1, 2],
        nrows=0
    )

    df_header = df_header.rename(
        columns=SURVEY_CONTACT_COLUMNS
    )

    return df_header.columns.tolist()


def get_original_universe_columns(path=None):

    if path is None:
        path = UNIVERSE_XLSX

    return pd.read_excel(
        path,
        nrows=0
    ).columns.tolist()


def get_internal_universe_columns(path=None):

    return [
        UNIVERSE_COLUMNS.get(col, col)
        for col in get_original_universe_columns(path)
    ]


def count_original_survey_responses(path=None):

    if path is None:
        path = SURVEY_CSV

    return len(
        pd.read_csv(
            path,
            skiprows=[1, 2],
            dtype="string"
        )
    )


def load_universe(paths=None):

    if paths is None:
        paths = UNIVERSE_FILES

    if isinstance(paths, (str, Path)):
        paths = [paths]

    df_universe = pd.concat(
        [
            pd.read_excel(
                path,
                dtype="string"
            )
            for path in paths
        ],
        ignore_index=True
    )

    df_universe = df_universe.rename(
        columns=(STANDARD_UNIVERSE_COLUMNS if "Provider Name" in df_universe.columns else UNIVERSE_COLUMNS)
    )

    df_universe = df_universe.replace(
        r"^\s*$",
        pd.NA,
        regex=True
    )

    # The NCA universe has one address and two identifier columns.
    # Empty compatibility columns let the shared matching functions run unchanged.
    for col in [
        "address2",
        "mailing_address",
        "mailing_address2",
        "type",
        "state"
    ]:
        if col not in df_universe:
            df_universe[col] = pd.NA

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


def load_survey(path=None):

    if path is None:
        path = SURVEY_CSV

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

    df = df[
        df[contact_cols]
        .notna()
        .any(axis=1)
    ].copy()

    survey_start = next(
        index
        for index, col in enumerate(df.columns)
        if col.startswith("Q2_")
    )

    df["response_count"] = (
        df.iloc[:, survey_start:]
        .notna()
        .sum(axis=1)
    )

    df["survey_row"] = df.index

    return df


# Use the NCA output path with the shared PDF exporter.
_shared_export_county_summary_pdf = export_county_summary_pdf


def export_county_summary_pdf(summary, path=None):

    if path is None:
        path = COUNTY_SUMMARY_PDF

    return _shared_export_county_summary_pdf(
        summary,
        path
    )


def export_universe_by_county(df, path, county_col="county"):

    # Keep this function name because the shared final exporter calls it.
    # NCA nonrespondents belong on one worksheet, not one sheet per district.
    return df.to_excel(
        path,
        index=False,
        sheet_name="Nonrespondents"
    )


# ============================================================
# RUN
# ============================================================

RUN_MAIN = True
RUN_MANUAL = False


def validate_results(
    df,
    responded_universe,
    unresponded_universe,
    cleaned_survey
):

    df_universe = load_universe()

    print("\n--- VALIDATION ---")

    print("Universe rows:", len(df_universe))

    print(
        "Universe row unique:",
        df_universe["universe_row"].is_unique
    )

    print(
        "All matched rows exist in universe:",
        df.loc[
            df["matched_row"].notna(),
            "matched_row"
        ].isin(
            df_universe["universe_row"]
        ).all()
    )

    print(
        "Responded universe unique:",
        df.loc[
            ~df["delete_candidate"]
            &
            df["matched_row"].notna(),
            "matched_row"
        ].is_unique
    )

    print(
        "Responded plus unresponded equals universe:",
        (
            len(responded_universe)
            +
            len(unresponded_universe)
        )
        ==
        len(df_universe)
    )

    print(
        "Cleaned survey and responded universe same count:",
        len(cleaned_survey) == len(responded_universe)
    )


def run_main():

    df = run_matching()

    (
        responded_universe,
        unresponded_universe,
        cleaned_survey,
        county_summary
    ) = export_final_files(df)

    validate_results(
        df,
        responded_universe,
        unresponded_universe,
        cleaned_survey
    )

    return df


def run_manual():
    return tag_duplicates(match_all())


def run_matching():
    from fcc_second_stage import match_remaining_to_fcc
    from types import SimpleNamespace
    df = tag_duplicates(match_all())
    fcc_results = match_remaining_to_fcc(df, SimpleNamespace(**globals()))
    df.to_csv(PROJECT_DIR / "last_audit_matches_nca.csv", index=False)
    fcc_results.to_csv(PROJECT_DIR / "fcc_second_stage_results_nca.csv", index=False)
    print_match_summary(df, fcc_results)
    return df


if __name__ == "__main__":

    if RUN_MAIN:
        df = run_main()

    if RUN_MANUAL:
        df_test = run_manual()
