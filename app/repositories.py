from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Dict, List, Optional

from app.enums import SaleStatus
from app.models import LedgerEntry, Payout, Sale, UserWallet


class SaleRepository:
    def __init__(self) -> None:
        self._sales: Dict[str, Sale] = {}
        self._sequence = 1

    def next_id(self) -> str:
        sale_id = f"sale_{self._sequence}"
        self._sequence += 1
        return sale_id

    def create(self, sale: Sale) -> Sale:
        self._sales[sale.sale_id] = sale
        return sale

    def get(self, sale_id: str) -> Optional[Sale]:
        return self._sales.get(sale_id)

    def update(self, sale: Sale) -> Sale:
        self._sales[sale.sale_id] = replace(sale, updated_at=datetime.now(sale.updated_at.tzinfo))
        return self._sales[sale.sale_id]

    def list_all(self) -> List[Sale]:
        return list(self._sales.values())

    def list_by_user(self, user_id: str) -> List[Sale]:
        return [sale for sale in self._sales.values() if sale.user_id == user_id]

    def list_pending_without_advance(self) -> List[Sale]:
        return [
            sale
            for sale in self._sales.values()
            if sale.status is SaleStatus.PENDING and not sale.advance_paid
        ]


class WalletRepository:
    def __init__(self) -> None:
        self._wallets: Dict[str, UserWallet] = {}

    def get(self, user_id: str) -> Optional[UserWallet]:
        return self._wallets.get(user_id)

    def create_or_get(self, user_id: str) -> UserWallet:
        wallet = self.get(user_id)
        if wallet is None:
            wallet = UserWallet(user_id=user_id)
            self._wallets[user_id] = wallet
        return wallet

    def update(self, wallet: UserWallet) -> UserWallet:
        self._wallets[wallet.user_id] = replace(
            wallet,
            updated_at=datetime.now(wallet.updated_at.tzinfo),
        )
        return self._wallets[wallet.user_id]


class PayoutRepository:
    def __init__(self) -> None:
        self._payouts: Dict[str, Payout] = {}
        self._idempotency_index: Dict[str, str] = {}
        self._sequence = 1

    def next_id(self) -> str:
        payout_id = f"payout_{self._sequence}"
        self._sequence += 1
        return payout_id

    def create(self, payout: Payout) -> Payout:
        self._payouts[payout.payout_id] = payout
        if payout.idempotency_key:
            self._idempotency_index[payout.idempotency_key] = payout.payout_id
        return payout

    def get(self, payout_id: str) -> Optional[Payout]:
        return self._payouts.get(payout_id)

    def get_by_idempotency_key(self, key: str) -> Optional[Payout]:
        payout_id = self._idempotency_index.get(key)
        return self._payouts.get(payout_id) if payout_id else None

    def update(self, payout: Payout) -> Payout:
        self._payouts[payout.payout_id] = replace(
            payout,
            updated_at=datetime.now(payout.updated_at.tzinfo),
        )
        return self._payouts[payout.payout_id]

    def list_by_user(self, user_id: str) -> List[Payout]:
        return [payout for payout in self._payouts.values() if payout.user_id == user_id]


class LedgerRepository:
    def __init__(self) -> None:
        self._entries: Dict[str, LedgerEntry] = {}
        self._sequence = 1

    def next_id(self) -> str:
        entry_id = f"ledger_{self._sequence}"
        self._sequence += 1
        return entry_id

    def create(self, entry: LedgerEntry) -> LedgerEntry:
        self._entries[entry.entry_id] = entry
        return entry

    def list_by_user(self, user_id: str) -> List[LedgerEntry]:
        return [entry for entry in self._entries.values() if entry.user_id == user_id]
