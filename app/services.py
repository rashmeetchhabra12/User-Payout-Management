from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from app.enums import PayoutStatus, PayoutType, SaleStatus
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.models import LedgerEntry, Payout, Sale, UserWallet
from app.repositories import LedgerRepository, PayoutRepository, SaleRepository, WalletRepository

TWOPLACES = Decimal("0.01")
ADVANCE_RATE = Decimal("0.10")
WITHDRAWAL_COOLDOWN = timedelta(hours=24)


def to_money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


class SaleService:
    def __init__(self, sales: SaleRepository, wallets: WalletRepository) -> None:
        self.sales = sales
        self.wallets = wallets

    def create_sale(
        self,
        user_id: str,
        brand: str,
        earning: Decimal | int | str,
        status: SaleStatus = SaleStatus.PENDING,
    ) -> Sale:
        amount = to_money(earning)
        if amount <= Decimal("0.00"):
            raise ValidationError("Earning must be greater than zero.")
        if status is not SaleStatus.PENDING:
            raise ValidationError("New sales must start in pending status.")

        self.wallets.create_or_get(user_id)
        sale = Sale(
            sale_id=self.sales.next_id(),
            user_id=user_id,
            brand=brand,
            earning=amount,
            status=status,
        )
        return self.sales.create(sale)


class LedgerService:
    def __init__(self, ledger: LedgerRepository) -> None:
        self.ledger = ledger

    def record(
        self,
        user_id: str,
        amount: Decimal,
        entry_type: str,
        note: str,
        sale_id: Optional[str] = None,
        payout_id: Optional[str] = None,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            entry_id=self.ledger.next_id(),
            user_id=user_id,
            amount=to_money(amount),
            entry_type=entry_type,
            note=note,
            sale_id=sale_id,
            payout_id=payout_id,
        )
        return self.ledger.create(entry)


class AdvancePayoutService:
    def __init__(
        self,
        sales: SaleRepository,
        wallets: WalletRepository,
        payouts: PayoutRepository,
        ledger_service: LedgerService,
    ) -> None:
        self.sales = sales
        self.wallets = wallets
        self.payouts = payouts
        self.ledger_service = ledger_service

    def run(self) -> List[Payout]:
        created_payouts: List[Payout] = []

        for sale in self.sales.list_pending_without_advance():
            advance_amount = to_money(sale.earning * ADVANCE_RATE)
            payout = Payout(
                payout_id=self.payouts.next_id(),
                user_id=sale.user_id,
                sale_id=sale.sale_id,
                amount=advance_amount,
                payout_type=PayoutType.ADVANCE,
                status=PayoutStatus.SUCCESS,
                idempotency_key=f"advance:{sale.sale_id}",
            )
            self.payouts.create(payout)

            sale.advance_paid = True
            sale.advance_paid_amount = advance_amount
            self.sales.update(sale)

            wallet = self.wallets.create_or_get(sale.user_id)
            wallet.withdrawable_balance = to_money(wallet.withdrawable_balance + advance_amount)
            self.wallets.update(wallet)

            self.ledger_service.record(
                user_id=sale.user_id,
                amount=advance_amount,
                entry_type="advance_credit",
                note=f"Advance payout credited for {sale.sale_id}",
                sale_id=sale.sale_id,
                payout_id=payout.payout_id,
            )

            created_payouts.append(payout)

        return created_payouts


class ReconciliationService:
    def __init__(
        self,
        sales: SaleRepository,
        wallets: WalletRepository,
        payouts: PayoutRepository,
        ledger_service: LedgerService,
    ) -> None:
        self.sales = sales
        self.wallets = wallets
        self.payouts = payouts
        self.ledger_service = ledger_service

    def reconcile(self, sale_id: str, new_status: SaleStatus) -> Payout:
        if new_status not in {SaleStatus.APPROVED, SaleStatus.REJECTED}:
            raise ValidationError("Sale can only be reconciled to approved or rejected.")

        sale = self.sales.get(sale_id)
        if sale is None:
            raise NotFoundError("Sale not found.")
        if sale.finalized:
            raise ConflictError("Sale has already been finalized.")

        sale.status = new_status
        sale.finalized = True
        self.sales.update(sale)

        if new_status is SaleStatus.APPROVED:
            adjustment = to_money(sale.earning - sale.advance_paid_amount)
            entry_type = "final_credit"
        else:
            adjustment = to_money(Decimal("0.00") - sale.advance_paid_amount)
            entry_type = "rejected_adjustment"

        payout = Payout(
            payout_id=self.payouts.next_id(),
            user_id=sale.user_id,
            sale_id=sale.sale_id,
            amount=adjustment,
            payout_type=PayoutType.FINAL,
            status=PayoutStatus.SUCCESS,
            idempotency_key=f"final:{sale.sale_id}",
        )
        self.payouts.create(payout)

        wallet = self.wallets.create_or_get(sale.user_id)
        wallet.withdrawable_balance = to_money(wallet.withdrawable_balance + adjustment)
        self.wallets.update(wallet)

        self.ledger_service.record(
            user_id=sale.user_id,
            amount=adjustment,
            entry_type=entry_type,
            note=f"Final settlement for {sale.sale_id}",
            sale_id=sale.sale_id,
            payout_id=payout.payout_id,
        )

        return payout


class WithdrawalService:
    def __init__(
        self,
        wallets: WalletRepository,
        payouts: PayoutRepository,
        ledger_service: LedgerService,
    ) -> None:
        self.wallets = wallets
        self.payouts = payouts
        self.ledger_service = ledger_service

    def initiate_withdrawal(
        self,
        user_id: str,
        amount: Decimal | int | str,
        idempotency_key: str,
        now: Optional[datetime] = None,
    ) -> Payout:
        requested_amount = to_money(amount)
        current_time = now or datetime.now(timezone.utc)

        if requested_amount <= Decimal("0.00"):
            raise ValidationError("Withdrawal amount must be greater than zero.")

        existing = self.payouts.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            raise ConflictError("Duplicate withdrawal request.")

        wallet = self.wallets.create_or_get(user_id)
        if wallet.last_withdrawal_at and current_time - wallet.last_withdrawal_at < WITHDRAWAL_COOLDOWN:
            raise ConflictError("User can make only one withdrawal every 24 hours.")
        if wallet.withdrawable_balance < requested_amount:
            raise ConflictError("Insufficient withdrawable balance.")

        payout = Payout(
            payout_id=self.payouts.next_id(),
            user_id=user_id,
            sale_id=None,
            amount=requested_amount,
            payout_type=PayoutType.WITHDRAWAL,
            status=PayoutStatus.INITIATED,
            idempotency_key=idempotency_key,
        )
        self.payouts.create(payout)

        wallet.withdrawable_balance = to_money(wallet.withdrawable_balance - requested_amount)
        wallet.last_withdrawal_at = current_time
        self.wallets.update(wallet)

        self.ledger_service.record(
            user_id=user_id,
            amount=Decimal("0.00") - requested_amount,
            entry_type="withdrawal_debit",
            note="Withdrawal initiated",
            payout_id=payout.payout_id,
        )

        return payout

    def update_withdrawal_status(self, payout_id: str, new_status: PayoutStatus) -> Dict[str, Optional[Payout]]:
        payout = self.payouts.get(payout_id)
        if payout is None:
            raise NotFoundError("Payout not found.")
        if payout.payout_type is not PayoutType.WITHDRAWAL:
            raise ValidationError("Only withdrawal payouts can be updated here.")

        if new_status not in {
            PayoutStatus.SUCCESS,
            PayoutStatus.FAILED,
            PayoutStatus.REJECTED,
            PayoutStatus.CANCELLED,
        }:
            raise ValidationError("Invalid withdrawal status transition.")

        if payout.status is not PayoutStatus.INITIATED:
            if payout.status is new_status:
                recovery_payout = None
                if new_status in {PayoutStatus.FAILED, PayoutStatus.REJECTED, PayoutStatus.CANCELLED}:
                    recovery_payout = self.payouts.get_by_idempotency_key(f"recovery:{payout.payout_id}")
                return {"payout": payout, "recovery_payout": recovery_payout}
            raise ConflictError("Only initiated withdrawals can be updated.")

        payout.status = new_status
        self.payouts.update(payout)

        recovery_payout: Optional[Payout] = None
        if new_status in {PayoutStatus.FAILED, PayoutStatus.REJECTED, PayoutStatus.CANCELLED}:
            wallet = self.wallets.create_or_get(payout.user_id)
            wallet.withdrawable_balance = to_money(wallet.withdrawable_balance + payout.amount)
            self.wallets.update(wallet)

            recovery_payout = Payout(
                payout_id=self.payouts.next_id(),
                user_id=payout.user_id,
                sale_id=None,
                amount=payout.amount,
                payout_type=PayoutType.RECOVERY,
                status=PayoutStatus.SUCCESS,
                idempotency_key=f"recovery:{payout.payout_id}",
            )
            self.payouts.create(recovery_payout)

            self.ledger_service.record(
                user_id=payout.user_id,
                amount=payout.amount,
                entry_type="withdrawal_recovery",
                note=f"Recovery for failed withdrawal {payout.payout_id}",
                payout_id=recovery_payout.payout_id,
            )

        return {"payout": payout, "recovery_payout": recovery_payout}


class PayoutSystem:
    def __init__(self) -> None:
        self.sales_repo = SaleRepository()
        self.wallet_repo = WalletRepository()
        self.payout_repo = PayoutRepository()
        self.ledger_repo = LedgerRepository()

        self.ledger_service = LedgerService(self.ledger_repo)
        self.sale_service = SaleService(self.sales_repo, self.wallet_repo)
        self.advance_service = AdvancePayoutService(
            self.sales_repo,
            self.wallet_repo,
            self.payout_repo,
            self.ledger_service,
        )
        self.reconciliation_service = ReconciliationService(
            self.sales_repo,
            self.wallet_repo,
            self.payout_repo,
            self.ledger_service,
        )
        self.withdrawal_service = WithdrawalService(
            self.wallet_repo,
            self.payout_repo,
            self.ledger_service,
        )

    def get_user_summary(self, user_id: str) -> Dict[str, object]:
        wallet = self.wallet_repo.create_or_get(user_id)
        user_payouts = self.payout_repo.list_by_user(user_id)
        advance_total = sum(
            (payout.amount for payout in user_payouts if payout.payout_type is PayoutType.ADVANCE),
            Decimal("0.00"),
        )
        final_settlement_total = sum(
            (payout.amount for payout in user_payouts if payout.payout_type is PayoutType.FINAL),
            Decimal("0.00"),
        )
        return {
            "wallet": asdict(wallet),
            "sales": [asdict(sale) for sale in self.sales_repo.list_by_user(user_id)],
            "payouts": [asdict(payout) for payout in user_payouts],
            "ledger_entries": [asdict(entry) for entry in self.ledger_repo.list_by_user(user_id)],
            "aggregates": {
                "advance_paid_total": advance_total,
                "final_settlement_total": final_settlement_total,
            },
        }
