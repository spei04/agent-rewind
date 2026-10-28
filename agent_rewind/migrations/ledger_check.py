"""Cooperative checks shared by bounded ledger validation kernels."""

from typing import Protocol


class LedgerCheck(Protocol):
    """Check the caller's bound; this grants no transaction or inspection rights."""

    def check(self) -> None: ...
