# Childcare Matching Notes

This project matches Qualtrics youth camp survey responses to the universe provider list.

Main script:

```text
.venv/working_upgrade.py
```

Input files are read from:

```text
/Users/bachnguyen/Downloads/Childcare Qualtrics
```

Outputs are written to:

```text
/Users/bachnguyen/Downloads/Childcare Qualtrics/response_report_sep_6
```

## Outputs

The script creates:

```text
responded_universe.xlsx
unresponded_universe.xlsx
cleaned_survey.xlsx
response_rate_by_county.pdf
```

`responded_universe.xlsx` contains unique universe rows that matched at least one kept survey response.

`unresponded_universe.xlsx` contains universe rows that did not match any kept survey response.

Both universe report files keep the same columns as the original universe file. Matching helper columns are not exported there.

`cleaned_survey.xlsx` contains only matched, non-duplicate survey responses. For matched rows, the contact fields are replaced with official universe values.

`response_rate_by_county.pdf` summarizes response rates by county.

## Row IDs

The script keeps two row identifiers while matching:

```text
survey_row
universe_row
```

`survey_row` preserves the original Qualtrics row.

`universe_row` preserves the original universe row.

These are safer than relying only on the dataframe index, especially after exploding rows with multiple license IDs.

## Normalization

Basic text normalization lowercases values, strips extra spaces, and turns blanks into `pd.NA`.

Address normalization is handled by `normalize_address()`. It:

```text
lowercases
removes punctuation
collapses spaces
expands n/s/e/w
expands rd/st/ave/blvd/pkwy
handles empty values safely
```

Address matching uses precomputed `new_address` columns. It does not clean again inside `address_match()`.

Email normalization creates lists of extracted emails. This allows cells with multiple emails to match without exploding the dataframe.

Advanced email normalization keeps only the domain after `@`, excluding common personal domains such as:

```text
gmail.com
yahoo.com
hotmail.com
outlook.com
icloud.com
aol.com
```

## Universe Data

`load_universe()` reads the universe Excel file, renames columns, removes blank strings, and creates `universe_row`.

It creates these helper columns:

```text
new_phone
new_email
advanced_email
new_zipcode
new_id
new_address
new_address2
```

Universe license ID handling currently keeps the first extracted 6-digit ID.

## Survey Data

`load_survey()` reads the Qualtrics CSV, renames contact columns, removes blank strings, and drops rows with no contact information.

It also creates:

```text
response_count
survey_row
```

`response_count` counts filled survey response fields. It is used later when choosing which duplicate response to keep.

## Multiple License IDs

Survey responses can contain multiple license IDs.

`clean_survey()` extracts all valid 6-digit IDs into `new_id`, then explodes `new_id`:

```python
df = df.explode(
    "new_id",
    ignore_index=True
)
```

This turns one survey response with multiple IDs into multiple rows, one row per ID.

The script then creates:

```text
split_response_count
multiple_id_response
```

`split_response_count` tells how many exploded rows came from the same original `survey_row`.

`multiple_id_response` is `True` when the original response had more than one ID.

## Match Columns

Each matching function creates two columns:

```text
*_where
*_match
```

Example:

```text
email_where
email_match
```

`email_where` stores the universe rows that matched.

`email_match` stores how many universe rows matched.

The individual match functions are:

```text
match_by_id
match_by_email
match_by_phone
match_by_address
match_by_program
match_by_zipcode
match_by_city
match_by_county
```

`match_by_email()` also creates:

```text
advanced_email_where
advanced_email_match
```

## First-Stage Matching

`match_all()` runs the first matching pass.

Current first-stage priority is:

```text
id
program
address
email
advanced_email
phone
zipcode
city
county
```

For each row, `assign_unique_match()` checks each match type in that order.

If a match type returns exactly one universe row, the script assigns:

```text
matched_row
matched_by
```

Example:

```text
matched_row = 337
matched_by = email
```

## Weak Location Rule

Zipcode, city, and county are weaker identifiers.

They still create `*_where` and `*_match` columns, and they still contribute to `potential`.

But a unique zipcode/city/county match is only accepted in first-stage matching if that universe row also appears in `least_match`.

This means weak location fields can confirm stronger clues, but they should not create a match from nothing.

## Least Match

`least_match` looks only at stronger match columns:

```text
id_where
program_where
address_where
email_where
advanced_email_where
phone_where
```

It returns the candidate list from the strongest available clue with the smallest nonzero count.

If there is a tie, it returns multiple lists.

Example:

```python
least_match = [[626, 642], [626, 642]]
```

That means two strong columns tied for the smallest candidate set.

## Potential

`potential` is a broad candidate list.

It combines all rows from:

```text
id_where
program_where
address_where
email_where
advanced_email_where
phone_where
zipcode_where
city_where
county_where
```

Repeated values are kept on purpose.

Example:

```python
potential = [577, 577, 550, 577]
```

This means universe row `577` received three clues, while `550` received one clue.

## Multiple-ID Resolution

`resolve_duplicates(df)` handles responses that were split because they contained multiple IDs.

First, it checks each `*_where` column one at a time. If the number of unique universe candidates equals the number of exploded rows, it assigns those candidates back to the exploded rows.

If that does not work, it combines stronger candidate columns:

```text
id_where
program_where
address_where
email_where
advanced_email_where
```

Then it assigns those unique candidates to the exploded rows it can fill.

Rows resolved here get labels such as:

```text
id multiple ids
city multiple ids
combined multiple ids
```

## Potential Majority Resolution

`resolve_by_potential_count(df)` handles rows that are still unmatched.

It uses weighted voting:

```text
strong columns = 2 votes
weak location columns = 1 vote
```

Strong columns are:

```text
id_where
program_where
address_where
email_where
advanced_email_where
phone_where
```

Weak location columns are:

```text
zipcode_where
city_where
county_where
```

The winning candidate must:

```text
have at least 2 votes
beat the second candidate
appear in at least one strong column
```

That last rule means a potential-majority match does not count if the score comes only from zipcode/city/county.

Rows resolved here get:

```text
matched_by = potential majority
```

## Mapping Results Back

Second-stage functions return smaller dataframes.

`map_df_cont_back(df, df_cont)` copies these columns back into the main dataframe:

```text
matched_row
matched_by
```

This works because `df_cont` keeps the same dataframe index as the main `df`.

## Duplicate Tagging

`tag_duplicates(df)` does not delete duplicate rows immediately.

It marks rows with:

```text
delete_candidate
```

Duplicate priority is based on `matched_by`.

Current order is:

```text
id
program
address
email
advanced_email
phone
zipcode
city
county
multiple ids
potential majority
unmatched
```

After match type, ties are broken by:

```text
response_count
RecordedDate
survey_row
```

So a stronger match type wins first, then the more complete response, then the newer response.

## Main Workflow

`run_matching()` does:

```text
1. Count original survey responses
2. Load survey after deleting preview/blank rows
3. Run match_all()
4. Resolve multiple-ID responses
5. Map those results back
6. Resolve remaining rows by weighted potential majority
7. Map those results back
8. Tag duplicates
9. Print summary
10. Return df
```

The summary prints:

```text
Original responses
After deleting preview/blank
Matched
Unmatched
Duplicates
Unique universe matches
Matched by counts
Duplicates tagged
```

## Final Dataset Creation

`create_final_datasets(df)` creates:

```text
responded_universe
unresponded_universe
cleaned_survey
```

First, it keeps only survey rows that are:

```text
not delete_candidate
matched_row is not empty
```

Then it creates `responded_universe` by keeping universe rows whose `universe_row` appears in the kept matched survey rows.

It also creates `unresponded_universe` by keeping universe rows whose `universe_row` does not appear in the kept matched survey rows.

Before export, both universe report tables are trimmed back to the original universe columns.

For matched survey rows, the script replaces survey-entered contact fields with official universe values:

```text
id
program
address
city
county
zipcode
phone
email
```

Finally, it keeps only the original Qualtrics columns in `cleaned_survey.xlsx`.

Helper columns such as `matched_row`, `matched_by`, `potential`, `least_match`, and `delete_candidate` are not exported to the cleaned survey file.

## County Summary

`create_county_summary(responded_universe)` compares:

```text
total universe providers by county
responded universe providers by county
```

Then it computes:

```text
response_rate = responded / total * 100
```

It also adds a `Total` row.

## Validation

At the end, the script checks:

```text
Universe row unique
All matched rows exist in universe
Responded universe unique
Responded plus unresponded equals universe
Cleaned survey and responded universe same count
```

These checks confirm that:

```text
universe_row is unique
matched_row values point to real universe rows
responded_universe does not contain duplicate universe rows
responded_universe plus unresponded_universe covers the full universe list
cleaned_survey and responded_universe have matching row counts
```

## Current Run Summary

Current in-memory check:

```text
Original responses: 1613
After deleting preview/blank: 1560
Matched: 1496
Unmatched: 64
Duplicates: 110
Unique universe matches: 1386
```

Current matched-by counts:

```text
program: 85
address: 79
email: 29
phone: 7
id: 5
advanced_email: 5
combined multiple ids: 9
city multiple ids: 2
potential majority: 3
city: 1
```

## Helpful Check Functions

Use these for manual review:

```text
check_potential(df, count=None)
check_potential_universe(df_cont)
check_universe(universe_row)
check_duplicates(df)
check_resolve_duplicate(df, survey_row=None)
```

`check_universe()` can take either one universe row or a list of universe rows.

## Weekly Match Audit

Run:

```text
weekly_match_audit.py
```

The audit automatically finds the newest center-provider survey export before
the current `SURVEY_CSV`. It reports:

```text
original and usable response counts
matched and unmatched usable responses
duplicate responses
unique universe matches
new usable responses since the prior export
newly represented universe rows
new responses dropped as duplicates
matched_by totals
exact matches with fewer than two unique supporting identifiers
exact matches with any unique conflicting identifier
matches whose ID-type evidence points to another universe row
advanced and other weak-method matches requiring manual review
potential-majority matches requiring manual review
duplicate groups touched by new responses, including kept/dropped reasons
```

An exact match passes automatically only when at least two unique exact
identifiers point to its matched universe row and no unique exact identifier
points elsewhere. The exact identifiers are ID, NJCCID, program, address, email,
and phone. Shared or nonunique values do not count. Every conflicting exact
identifier causes manual review at the two-support threshold. ID, NJCCID, and
advanced-ID evidence is stricter: with exactly two supporting identifiers, the
match is flagged if any ID-type field identifies another universe row, even
when that identifier is ambiguous or the selected row also appears among its
candidates. Three or more exact supporting identifiers may override an ID-type
conflict, but they do not override a conflicting non-ID exact field.

Advanced matching, multiple-ID resolution, location-only matching, and
potential majority always require manual review. The audit checks matched rows
that may later be dropped as duplicates because an incorrect match must not be
allowed to create a false duplicate. Review output is shown in batches, with
conflicts first, followed by zero-support and then one-support matches.

Reviewed corrections are stored by Qualtrics `ResponseId` and official universe
license number in `MANUAL_MATCH_OVERRIDES`. Reviewed cases where the license ID,
program, and address are correct but the submitted NJCCID belongs to a sister
site are stored in `REVIEWED_SENSIBLE_RESPONSE_IDS`, so the audit does not report
the same resolved warning every week.

Reviewed responses that must not be matched are stored in
`MANUAL_UNMATCHED_RESPONSE_IDS`. They are cleared after all automatic and
fallback matching stages, before duplicate tagging, so a later rule cannot
restore the rejected match.

Reviewed weekly non-ID matches are stored in `REVIEWED_NON_ID_RESPONSE_IDS`, so
rerunning the audit only shows new non-ID cases that still need inspection.

The duplicate review queue compares each newly affected duplicate group with its
universe row. It distinguishes duplicates supported by exact IDs, duplicates
supported by at least two exact facility details, and groups still requiring
manual review. Every response in a duplicate group must first be either manually
reviewed or supported by at least two unique exact identifiers. An unsafe or
unreviewed match blocks duplicate confirmation. The queue also shows which
response is kept or dropped and the existing `delete_reason`.

When choosing which duplicate response to keep, exact license-ID evidence has
highest priority, followed by exact NJCCID/facility-ID evidence, then the normal
`matched_by` hierarchy, response count, response date, and survey row. This
prevents a weaker manual or descriptive match from displacing a response with
an exact ID for the same universe facility.

Match conflicts are checked before duplicate confirmation. If any response in a
duplicate group has an unresolved conflicting match, that group is labeled
`match conflict - review first` and is not counted as a confirmed duplicate.
Correct the match first, then rerun the audit so the duplicate decision is based
on the correct universe row.

The duplicate queue is the final audit stage. The audit first reviews suspicious
matches, then direct non-ID matches, then potential-majority matches. Each queue
must be cleared before the next stage opens. Matches that would later be dropped
as duplicates are still included in these earlier reviews. Manually rejected
responses are excluded from potential majority. After all match queues are
cleared, rerun the audit to open the new duplicate queue. Duplicate groups are
then categorized as supported by exact IDs, supported by facility details, or
needing manual review.

Every new duplicate group is printed for manual review after all match queues
are clear. Set `SHOW_CONFIRMED_DUPLICATE_GROUPS = False` only when confirmed
groups should be counted without printing every kept/dropped pair.

Manually confirmed duplicate pairs can be stored in
`REVIEWED_DUPLICATE_RESPONSE_IDS` so they do not return to the weekly manual
queue.

### Weekly Procedure

1. Add the new survey CSV to the Childcare Qualtrics folder.
2. Update `SURVEY_CSV` and the dated `REPORT_DIR` in `center_provider.py`.
3. Ask Codex to run and audit the updated survey. Codex runs
   `center_provider.py` to create preliminary results, then runs
   `weekly_match_audit.py`.
4. Review exact, weak, potential-majority, and duplicate cases in that order.
   Codex records approved corrections and intentional unmatched responses, then
   reruns the audit until every review queue is clear.
5. Codex runs `center_provider.py` again to regenerate the final Excel and PDF
   reports.
6. Codex relays the summary already printed by `center_provider.py`, including
   original responses, preview/blank removals, usable responses, matched and
   unmatched responses, duplicate responses dropped, unique universe matches,
   the full `matched_by` breakdown, and the final validation results. Final
   reconciliation compares facility-ID sets: responded must equal the kept
   audited matches, nonrespondent must equal the exact universe remainder, and
   the cleaned survey identifiers must equal the responded identifiers.

## NCA Weekly Match Audit

Run:

```text
weekly_nca_match_audit.py
```

The NCA audit uses the same conservative sequence as the MRS center-provider
audit: exact-match conflict review, weak-method review, potential-majority
review, and duplicate review last. It automatically compares the current NCA
survey with the newest earlier NCA survey in the same folder.

NCA review decisions are stored separately in `weekly_nca_match_audit.py`.
Manual match overrides and intentional unmatched responses belong in
`narrow_cost_provider.py`, so no NCA decision can affect the MRS workflow.

For each NCA update:

1. Update the survey, reconciled universe, and report paths in
   `narrow_cost_provider.py`.
2. Run `narrow_cost_provider.py` to produce preliminary reports.
3. Run `weekly_nca_match_audit.py` and review each queue in order.
4. Record approved matches, rejected matches, and reviewed duplicate response
   IDs in the NCA files.
5. Rerun the audit until all queues are clear, then rerun
   `narrow_cost_provider.py` for the final reports.
