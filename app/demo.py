from pprint import pprint

from app.enums import PayoutStatus, SaleStatus
from app.services import PayoutSystem


def run_demo() -> None:
    system = PayoutSystem()

    system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="40")
    system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="40")
    system.sale_service.create_sale(user_id="john_doe", brand="brand_1", earning="40")

    print("Advance payouts")
    advance_payouts = system.advance_service.run()
    pprint(advance_payouts)

    print("\nReconciliation")
    system.reconciliation_service.reconcile("sale_1", SaleStatus.REJECTED)
    system.reconciliation_service.reconcile("sale_2", SaleStatus.APPROVED)
    system.reconciliation_service.reconcile("sale_3", SaleStatus.APPROVED)
    pprint(system.get_user_summary("john_doe"))

    print("\nWithdrawal and recovery")
    withdrawal = system.withdrawal_service.initiate_withdrawal(
        user_id="john_doe",
        amount="20",
        idempotency_key="withdrawal:john_doe:1",
    )
    system.withdrawal_service.update_withdrawal_status(withdrawal.payout_id, PayoutStatus.FAILED)
    pprint(system.get_user_summary("john_doe"))


if __name__ == "__main__":
    run_demo()
