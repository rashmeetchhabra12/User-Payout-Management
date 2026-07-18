# User Payout Management System

This repository contains a Python implementation and low-level design for an affiliate payout management system.

## Submission Checklist

- Low-Level Design included in this README
- Database schema with relationships included
- Class design reflected in Python code
- API/endpoints both designed and implemented
- Edge cases and failure scenarios covered
- Working Python implementation included
- Unit tests included
- Demo runner included

## 1. Problem Statement

We need to manage affiliate sales and payouts with the following rules:

- Every sale enters the system in `pending` state.
- Pending sales are eligible for an `advance payout` equal to `10%` of earning.
- The advance payout must be issued only once per sale, even if the advance payout job runs multiple times.
- Later, an admin reconciles the sale and changes its status to `approved` or `rejected`.
- Final payout must account for the advance already paid.
- A user can initiate only one withdrawal every 24 hours.
- If a withdrawal later becomes `failed`, `cancelled`, or `rejected`, the amount must be credited back.

## 2. Requirements

### Functional Requirements

- Ingest and store sales
- Run advance payout job for eligible pending sales
- Reconcile a sale exactly once
- Maintain user withdrawable balance
- Allow user withdrawals with a 24-hour cooldown
- Recover failed withdrawals
- Keep audit history of money movement

### Non-Functional Requirements

- Idempotent payout processing
- Clear auditability
- Simple and readable implementation
- Extensible design for future database-backed persistence

## 3. Design Approach

The design separates the system into four concepts:

- `Sale`
  Represents the affiliate earning event.
- `Payout`
  Represents a money movement event such as advance payout, final settlement, withdrawal, or recovery.
- `UserWallet`
  Represents the user's current withdrawable balance.
- `LedgerEntry`
  Represents immutable balance history for auditability.

This separation makes payout retries and failure handling safer than directly mutating a single balance table with no history.

## 4. Entity Design

### `Sale`

Fields:

- `sale_id`
- `user_id`
- `brand`
- `earning`
- `status`
- `advance_paid`
- `advance_paid_amount`
- `finalized`
- `created_at`
- `updated_at`

### `UserWallet`

Fields:

- `user_id`
- `withdrawable_balance`
- `last_withdrawal_at`
- `created_at`
- `updated_at`

### `Payout`

Fields:

- `payout_id`
- `user_id`
- `sale_id`
- `amount`
- `payout_type`
- `status`
- `idempotency_key`
- `created_at`
- `updated_at`

### `LedgerEntry`

Fields:

- `entry_id`
- `user_id`
- `sale_id`
- `payout_id`
- `amount`
- `entry_type`
- `note`
- `created_at`

## 5. Enum Design

### Sale Status

- `pending`
- `approved`
- `rejected`

### Payout Type

- `advance`
- `final`
- `withdrawal`
- `recovery`

### Payout Status

- `initiated`
- `success`
- `failed`
- `rejected`
- `cancelled`

## 6. Database Schema Design

The implementation uses in-memory repositories, but this is the relational schema I would use in production.

### `sales`

| Column | Type | Notes |
|---|---|---|
| `sale_id` | `varchar PK` | unique sale id |
| `user_id` | `varchar` | indexed |
| `brand` | `varchar` | indexed |
| `earning` | `decimal(12,2)` | sale earning |
| `status` | `enum` | pending/approved/rejected |
| `advance_paid` | `boolean` | default false |
| `advance_paid_amount` | `decimal(12,2)` | default 0 |
| `finalized` | `boolean` | default false |
| `created_at` | `timestamp` | |
| `updated_at` | `timestamp` | |

Indexes:

- `(status, advance_paid)`
- `(user_id, status)`

### `user_wallets`

| Column | Type | Notes |
|---|---|---|
| `user_id` | `varchar PK` | unique user id |
| `withdrawable_balance` | `decimal(12,2)` | current balance |
| `last_withdrawal_at` | `timestamp null` | cooldown tracking |
| `created_at` | `timestamp` | |
| `updated_at` | `timestamp` | |

### `payouts`

| Column | Type | Notes |
|---|---|---|
| `payout_id` | `varchar PK` | unique payout id |
| `user_id` | `varchar` | indexed |
| `sale_id` | `varchar null` | nullable for withdrawals |
| `amount` | `decimal(12,2)` | payout amount |
| `payout_type` | `enum` | advance/final/withdrawal/recovery |
| `status` | `enum` | initiated/success/failed/rejected/cancelled |
| `idempotency_key` | `varchar unique` | retry protection |
| `created_at` | `timestamp` | |
| `updated_at` | `timestamp` | |

Indexes:

- `(user_id, payout_type, status)`
- `(sale_id, payout_type)`
- unique `(idempotency_key)`

### `ledger_entries`

| Column | Type | Notes |
|---|---|---|
| `entry_id` | `varchar PK` | unique ledger id |
| `user_id` | `varchar` | indexed |
| `sale_id` | `varchar null` | nullable |
| `payout_id` | `varchar null` | nullable |
| `amount` | `decimal(12,2)` | signed value |
| `entry_type` | `varchar` | domain-specific event type |
| `note` | `varchar` | audit note |
| `created_at` | `timestamp` | |

## 7. Class Design

### Models

- `Sale`
- `UserWallet`
- `Payout`
- `LedgerEntry`

### Repositories

- `SaleRepository`
- `WalletRepository`
- `PayoutRepository`
- `LedgerRepository`

### Services

- `SaleService`
- `AdvancePayoutService`
- `ReconciliationService`
- `WithdrawalService`
- `LedgerService`
- `PayoutSystem`

## 8. Workflow Design

### A. Sale Creation

1. Validate earning amount
2. Force status to `pending`
3. Create sale
4. Ensure wallet exists

### B. Advance Payout Job

1. Fetch all sales where:
   - `status = pending`
   - `advance_paid = false`
2. For each sale:
   - compute `10%` advance
   - create advance payout with `success`
   - mark sale advance as paid
   - credit wallet
   - create ledger entry

### C. Reconciliation

Rules:

- Sale can be reconciled only once
- Allowed statuses are `approved` and `rejected`

Computation:

- If `approved`: `earning - advance_paid_amount`
- If `rejected`: `-advance_paid_amount`

Example from assignment:

| Sale Status | Earning | Advance Paid | Final Adjustment |
|---|---:|---:|---:|
| rejected | 40 | 4 | -4 |
| approved | 40 | 4 | 36 |
| approved | 40 | 4 | 36 |

Total final payout effect: `68`

Note:

- In this implementation, the assignment's `Final Payout = 68` is represented as `final_settlement_total`.
- If the earlier advance payouts have not yet been withdrawn/spent from the wallet, the wallet balance can be higher than `68` because it still includes the already-credited advance amounts.

### D. Withdrawal

1. Validate amount
2. Validate idempotency key
3. Check last withdrawal timestamp
4. Check sufficient withdrawable balance
5. Create withdrawal payout with `initiated`
6. Deduct balance immediately
7. Create ledger entry

### E. Failed Withdrawal Recovery

When provider later reports `failed`, `cancelled`, or `rejected`:

1. Update withdrawal payout status
2. Credit amount back to wallet
3. Create recovery payout
4. Write ledger entry

## 9. API Design

The repo includes a lightweight HTTP API built with Python's standard library in `app/api.py`.

### `POST /sales`

```json
{
  "userId": "john_doe",
  "brand": "brand_1",
  "earning": 40
}
```

### `POST /jobs/advance-payouts`

Runs the advance payout batch job.

### `POST /sales/{sale_id}/reconcile`

```json
{
  "status": "approved"
}
```

### `GET /users/{user_id}/wallet`

Returns wallet, sales, payouts, and ledger data.
It also returns:

- `advance_paid_total`
- `final_settlement_total`

### `POST /withdrawals`

```json
{
  "userId": "john_doe",
  "amount": 20,
  "idempotencyKey": "withdrawal:john_doe:1"
}
```

### `POST /withdrawals/{payout_id}/status`

```json
{
  "status": "failed"
}
```

### `GET /health`

Returns a simple health response.

## 10. Edge Cases and Failure Handling

- Advance payout job runs multiple times and already-paid sales are skipped
- Same sale cannot be reconciled twice
- Duplicate withdrawal request is blocked by `idempotency_key`
- Withdrawal within 24 hours is rejected
- Failed/cancelled/rejected withdrawal restores balance
- Duplicate status update with the same terminal state is treated idempotently
- Conflicting second status update is blocked because only `initiated` withdrawals can transition
- Rejected sales can push wallet balance negative due to clawback

## 11. Trade-offs and Decisions

### Chosen

- `Python` for readable domain logic
- `In-memory repositories` for simple review and execution
- `Negative wallet balances allowed` for direct clawback modeling

### Alternatives

- `SQLite/PostgreSQL` for persistence
- `Separate debt table` if negative balances are not allowed

## 12. Testing Strategy

Current tests cover:

- advance payout idempotency
- assignment reconciliation example
- explicit final settlement total for the assignment example
- 24-hour withdrawal restriction
- failed withdrawal recovery
- duplicate reconciliation prevention
- duplicate withdrawal idempotency key rejection
- duplicate payout status update prevention
- duplicate failed callback idempotency
- JSON-safe summary serialization

## 13. Project Structure

```text
app/
  api.py
  __init__.py
  demo.py
  enums.py
  exceptions.py
  models.py
  repositories.py
  serializers.py
  services.py
tests/
  test_payout_system.py
.gitignore
main.py
README.md
```

## 14. How to Run

### Run the API server

```bash
python main.py
```

Server runs at:

```text
http://127.0.0.1:8000
```

### Run the tests

```bash
python -m unittest discover -s tests -v
```

### Run the demo script

```bash
python -m app.demo
```

## 15. Python Setup

This project uses only the Python standard library, so setup is straightforward.

### Windows Setup

1. Install Python 3.11 or newer from `python.org`.
2. During installation, enable `Add python.exe to PATH`.
3. After installation, open a new terminal and verify:

```powershell
python --version
```

If `python` does not work, try:

```powershell
py --version
```

If the `py` launcher works but `python` does not, you can run the project with:

```powershell
py -m unittest discover -s tests -v
py main.py
```

### Optional Virtual Environment

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m unittest discover -s tests -v
```

### Common Windows Fixes

- If `python` opens the Microsoft Store, disable the App Execution Alias for Python in Windows settings.
- If terminal still cannot find Python, reopen the terminal after installation.
- If both `python` and `py` fail, reinstall Python and ensure PATH is enabled during setup.

## 16. Sample API Flow

### 1. Create sales

```bash
curl -X POST http://127.0.0.1:8000/sales ^
  -H "Content-Type: application/json" ^
  -d "{\"userId\":\"john_doe\",\"brand\":\"brand_1\",\"earning\":40}"
```

Repeat it three times for the assignment example.

### 2. Run advance payout job

```bash
curl -X POST http://127.0.0.1:8000/jobs/advance-payouts
```

### 3. Reconcile sales

```bash
curl -X POST http://127.0.0.1:8000/sales/sale_1/reconcile ^
  -H "Content-Type: application/json" ^
  -d "{\"status\":\"rejected\"}"
```

```bash
curl -X POST http://127.0.0.1:8000/sales/sale_2/reconcile ^
  -H "Content-Type: application/json" ^
  -d "{\"status\":\"approved\"}"
```

```bash
curl -X POST http://127.0.0.1:8000/sales/sale_3/reconcile ^
  -H "Content-Type: application/json" ^
  -d "{\"status\":\"approved\"}"
```

### 4. Fetch final wallet summary

```bash
curl http://127.0.0.1:8000/users/john_doe/wallet
```

## 17. Production Improvements

- Replace in-memory repositories with PostgreSQL/MySQL repositories
- Add transactional guarantees for payout jobs
- Add payout provider abstraction and webhook verification
- Add admin/user authentication and authorization
- Add payout status transition history
- Add retry queue for external transfer failures
