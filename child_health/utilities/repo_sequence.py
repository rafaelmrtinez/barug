from typing import Any


class RepoSequence:
    """Simple sequence wrapper around a repository search API that exposes
    __len__ and __getitem__ so Django's Paginator can paginate without
    materializing all rows.

    Usage:
        seq = RepoSequence.create(repo, q, total)
        paginator = Paginator(seq, per_page)
    """

    MAX_LIMIT = 50  # maximum rows to fetch per repository call

    def __init__(self, repo: Any, q: str, total_count: int):
        self.repo = repo
        self.q = q
        # defensive: ensure integer and non-negative
        try:
            self._total = max(0, int(total_count or 0))
        except Exception:
            self._total = 0

    @staticmethod
    def create(repo: Any, q: str, total_count: int) -> "RepoSequence":
        return RepoSequence(repo, q, total_count)

    def __len__(self) -> int:
        return self._total

    def __getitem__(self, slc):
        # Expect slices like [start:stop]
        start = slc.start or 0
        stop = slc.stop or start
        # Defensive: ensure non-negative start/stop
        try:
            start = max(0, int(start))
        except Exception:
            start = 0
        try:
            stop = max(start, int(stop))
        except Exception:
            stop = start
        requested = max(0, stop - start)
        # Cap limit to avoid overly large single-page fetches
        limit = min(self.MAX_LIMIT, requested if requested > 0 else self.MAX_LIMIT)
        # Delegate to repository method that supports limit/offset
        try:
            return self.repo.fetch_basic_chr_record_search(self.q, limit, start)
        except Exception:
            # On repository failure return empty list so paginator remains stable
            return []
