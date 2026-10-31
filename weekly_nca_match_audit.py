"""NCA audit using the same staged matching and reporting as Provider 2."""
import importlib.util
from pathlib import Path

import narrow_cost_provider as nca

ROOT = Path(__file__).resolve().parent
# A separate audit instance prevents NCA configuration from changing MRS state.
spec = importlib.util.spec_from_file_location('nca_audit_runtime', ROOT / 'weekly_match_audit_v2.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def configure_nca_audit():
    audit.provider = nca
    audit.CACHE = ROOT / 'last_audit_matches_nca.csv'
    audit.LEDGER = ROOT / 'reviewed_matches_nca.csv'
    audit.STATUS_REPORT_CSV = ROOT / 'match_status_report_nca.csv'
    audit.REVIEW_QUEUE_CSV = ROOT / 'manual_review_queue_nca.csv'
    audit.STATUS_SUMMARY_CSV = ROOT / 'match_status_summary_nca.csv'
    audit.FCC_RESULTS_CSV = ROOT / 'fcc_second_stage_results_nca.csv'


def main():
    configure_nca_audit()
    return audit.main()


if __name__ == '__main__':
    df_nca_audit = main()
