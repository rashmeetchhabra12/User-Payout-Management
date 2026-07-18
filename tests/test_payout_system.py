import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.enums import PayoutStatus, SaleStatus
from app.exceptions import ConflictError
from app.serializers import to_primitive
from app.services import PayoutSystem


class PayoutSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.system = PayoutSystem()

    def test_advance_payout_is_idempotent_per_sale(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="40")

        first_run = self.system.advance_service.run()
        second_run = self.system.advance_service.run()

        self.assertEqual(1, len(first_run))
        self.assertEqual(0, len(second_run))
        wallet = self.system.wallet_repo.get("john_doe")
        self.assertEqual(Decimal("4.00"), wallet.withdrawable_balance)

    def test_final_payout_matches_assignment_example(self) -> None:
        for _ in range(3):
            self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="40")

        self.system.advance_service.run()
        self.system.reconciliation_service.reconcile("sale_1", SaleStatus.REJECTED)
        self.system.reconciliation_service.reconcile("sale_2", SaleStatus.APPROVED)
        self.system.reconciliation_service.reconcile("sale_3", SaleStatus.APPROVED)

        summary = self.system.get_user_summary("john_doe")
        self.assertEqual(Decimal("68.00"), summary["aggregates"]["final_settlement_total"])
        self.assertEqual(Decimal("80.00"), summary["wallet"]["withdrawable_balance"])

    def test_withdrawal_is_limited_to_one_per_24_hours(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="100")
        self.system.advance_service.run()

        now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)
        self.system.withdrawal_service.initiate_withdrawal(
            user_id="john_doe",
            amount="10",
            idempotency_key="withdrawal-1",
            now=now,
        )

        with self.assertRaises(ConflictError):
            self.system.withdrawal_service.initiate_withdrawal(
                user_id="john_doe",
                amount="1",
                idempotency_key="withdrawal-2",
                now=now + timedelta(hours=23, minutes=59),
            )

    def test_failed_withdrawal_is_credited_back(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="100")
        self.system.advance_service.run()

        withdrawal = self.system.withdrawal_service.initiate_withdrawal(
            user_id="john_doe",
            amount="10",
            idempotency_key="withdrawal-1",
        )
        self.system.withdrawal_service.update_withdrawal_status(
            withdrawal.payout_id,
            PayoutStatus.FAILED,
        )

        wallet = self.system.wallet_repo.get("john_doe")
        self.assertEqual(Decimal("10.00"), wallet.withdrawable_balance)

    def test_sale_cannot_be_reconciled_twice(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="50")
        self.system.advance_service.run()
        self.system.reconciliation_service.reconcile("sale_1", SaleStatus.APPROVED)

        with self.assertRaises(ConflictError):
            self.system.reconciliation_service.reconcile("sale_1", SaleStatus.REJECTED)

    def test_duplicate_withdrawal_idempotency_key_is_rejected(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="100")
        self.system.advance_service.run()
        now = datetime(2026, 7, 18, 10, 0, tzinfo=timezone.utc)

        self.system.withdrawal_service.initiate_withdrawal(
            user_id="john_doe",
            amount="5",
            idempotency_key="withdrawal-1",
            now=now,
        )

        with self.assertRaises(ConflictError):
            self.system.withdrawal_service.initiate_withdrawal(
                user_id="john_doe",
                amount="5",
                idempotency_key="withdrawal-1",
                now=now + timedelta(days=1),
            )

    def test_only_initiated_withdrawal_can_be_updated_once(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="100")
        self.system.advance_service.run()

        withdrawal = self.system.withdrawal_service.initiate_withdrawal(
            user_id="john_doe",
            amount="5",
            idempotency_key="withdrawal-1",
        )
        self.system.withdrawal_service.update_withdrawal_status(
            withdrawal.payout_id,
            PayoutStatus.SUCCESS,
        )

        with self.assertRaises(ConflictError):
            self.system.withdrawal_service.update_withdrawal_status(
                withdrawal.payout_id,
                PayoutStatus.FAILED,
            )

    def test_duplicate_failed_callback_is_idempotent(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="100")
        self.system.advance_service.run()

        withdrawal = self.system.withdrawal_service.initiate_withdrawal(
            user_id="john_doe",
            amount="5",
            idempotency_key="withdrawal-1",
        )

        first_result = self.system.withdrawal_service.update_withdrawal_status(
            withdrawal.payout_id,
            PayoutStatus.FAILED,
        )
        second_result = self.system.withdrawal_service.update_withdrawal_status(
            withdrawal.payout_id,
            PayoutStatus.FAILED,
        )

        wallet = self.system.wallet_repo.get("john_doe")
        self.assertEqual(Decimal("10.00"), wallet.withdrawable_balance)
        self.assertIsNotNone(first_result["recovery_payout"])
        self.assertEqual(
            first_result["recovery_payout"].payout_id,
            second_result["recovery_payout"].payout_id,
        )

    def test_user_summary_is_serializable(self) -> None:
        self.system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="40")
        self.system.advance_service.run()

        summary = self.system.get_user_summary("john_doe")
        primitive_summary = to_primitive(summary)

        self.assertEqual("4.00", primitive_summary["wallet"]["withdrawable_balance"])
        self.assertEqual("pending", primitive_summary["sales"][0]["status"])
        self.assertEqual("0.00", primitive_summary["aggregates"]["final_settlement_total"])


if __name__ == "__main__":
    unittest.main()
