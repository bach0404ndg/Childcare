"""Try the FCC universe only after center matching leaves a response unresolved.

FCC row numbers are kept separate from center row numbers and reports.
"""
import pandas as pd


def match_remaining_to_fcc(center_results, provider_module=None):
    if provider_module is None:
        import weekly_match_audit_v2 as audit
        provider_module = audit.provider
    provider = provider_module
    fcc_universe = getattr(provider, 'FCC_UNIVERSE_PATH', provider.DATA_DIR / 'Active FCC Providers as of 9-14-2026.xlsx') 
    remaining_ids = set(center_results.loc[
        center_results.matched_row.isna() & ~center_results.matched_by.eq('manual excluded'), 'ResponseId'])
    responses = provider.clean_survey()
    responses = responses[responses.ResponseId.isin(remaining_ids)].copy()
    universe = provider.load_universe([fcc_universe])
    for matcher in (provider.match_by_id, provider.match_by_njccid,
                    provider.match_by_program, provider.match_by_address,
                    provider.match_by_email, provider.match_by_phone):
        responses = matcher(responses, universe)
    responses[['fcc_matched_row', 'fcc_matched_by', 'fcc_conflict', 'fcc_review_reason']] = responses.apply(
        lambda row: provider.resolve_match(row, universe), axis=1)
    ranked = responses.copy()
    ranked['matched_row'] = ranked['fcc_matched_row']
    ranked = provider.tag_duplicates(ranked)
    responses['fcc_id_exact_match'] = ranked['id_exact_match']
    responses['fcc_delete_candidate'] = ranked['delete_candidate']
    lookup = universe.set_index('universe_row')
    for field in ['id', 'fac_id', 'program', 'address', 'city', 'zipcode', 'phone', 'email']:
        responses['fcc_' + field] = responses.fcc_matched_row.map(lookup[field])
    responses['fcc_universe_source'] = str(fcc_universe)
    responses['fcc_needs_review'] = responses.fcc_matched_row.isna()
    responses['matched_provider_type'] = responses.fcc_matched_row.map(
        lambda value: 'Family Child Care' if pd.notna(value) else pd.NA)
    return responses


if __name__ == '__main__':
    import weekly_match_audit_v2 as audit
    result = match_remaining_to_fcc(pd.read_csv(audit.CACHE))
    result.to_csv('fcc_second_stage_results_v2.csv', index=False)
    print('Unresolved center responses checked:', len(result))
    print('Matched to FCC universe:', int(result.fcc_matched_row.notna().sum()))
    print('Unique FCC providers:', result.fcc_matched_row.nunique())
    print('Still unresolved:', int(result.fcc_matched_row.isna().sum()))
    print(result[result.fcc_matched_row.notna()][[
        'ResponseId', 'program', 'fcc_program', 'fcc_matched_by', 'fcc_id',
        'fcc_address']].to_string(index=False))
