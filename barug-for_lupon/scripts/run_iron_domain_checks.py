"""Simple runner for IronIntakeDomainService checks without pytest.

This script runs the same test scenarios added under tests/ but without pytest
so it can run in environments without pytest installed.
"""
import sys
import os
# ensure workspace root is on path so `src` package is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.domain.services.iron_intake_domain_service import IronIntakeDomainService
from src.domain.exceptions.iron_intake_domain_exception import IronIntakeDomainException
from src.infra.utilities.custom_date_time_util import DateAndTimeUtility


class DummyRepo:
    def __init__(self, existing=None):
        self._existing = existing

    def fetch_iron_supplement_completion_by_chr_id(self, chr_id):
        return self._existing


def run_case(name, fn):
    try:
        fn()
        print(f"PASS: {name}")
    except Exception as e:
        print(f"FAIL: {name} -> {e}")


def main():
    # fix today
    DateAndTimeUtility.get_current_date = staticmethod(lambda: '2025-11-22')

    svc = IronIntakeDomainService(ch_repo=DummyRepo())

    run_case("future_date_started_rejected", lambda: svc.validate_and_prepare(1, {'date_started': '2025-11-23'}) )

    svc2 = IronIntakeDomainService(ch_repo=DummyRepo(existing=None))
    run_case("date_completed_without_started_rejected", lambda: svc2.validate_and_prepare(1, {'date_completed': '2025-11-21'}) )

    existing = {'date_started': '2025-11-20', 'date_completed': None}
    svc3 = IronIntakeDomainService(ch_repo=DummyRepo(existing=existing))
    run_case("cannot_add_started_if_existing_started_exists", lambda: svc3.validate_and_prepare(1, {'date_started': '2025-11-21'}) )

    existing2 = {'date_started': '2025-11-10', 'date_completed': '2025-11-20'}
    svc4 = IronIntakeDomainService(ch_repo=DummyRepo(existing=existing2))
    run_case("existing_both_completed_blocks", lambda: svc4.validate_and_prepare(1, {'date_started': '2025-11-21'}) )

    svc5 = IronIntakeDomainService(ch_repo=DummyRepo())
    run_case("date_completed_before_started_rejected", lambda: svc5.validate_and_prepare(1, {'date_started': '2025-11-21', 'date_completed': '2025-11-20'}) )

    svc6 = IronIntakeDomainService(ch_repo=DummyRepo())
    try:
        normalized = svc6.validate_and_prepare(1, {'date_started': '2025-11-20', 'date_completed': '2025-11-21'})
        print("PASS: valid_payload_normalizes ->", normalized)
    except Exception as e:
        print("FAIL: valid_payload_normalizes ->", e)


if __name__ == '__main__':
    main()
