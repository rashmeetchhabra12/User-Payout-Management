# User Payout Management System

This repository contains the low-level design and Python implementation for a user payout management system for affiliate sales.

## Overview

The system supports the full payout lifecycle for affiliate sales:

- every sale enters the system as `pending`
- eligible pending sales receive a one-time advance payout of `10%`
- an admin later reconciles each sale to `approved` or `rejected`
- final settlement accounts for any advance already paid
- users can withdraw from their available balance, but only once every 24 hours
- failed, cancelled, or rejected withdrawals are credited back automatically

The implementation is intentionally small and dependency-free so that the business logic remains easy to review.

## Assumptions

- All newly created sales must start in `pending` state.
- Advance payout is credited exactly once per sale.
- Reconciliation is a one-time operation per sale.
- Negative wallet balances are allowed after a rejected sale if an advance had already been paid.
- Withdrawable balance is updated immediately when a withdrawal is initiated.
- If a payout gateway later marks that withdrawal as `failed`, `cancelled`, or `rejected`, the amount is restored to the wallet.

## 1. Problem Statement

The goal is to design a payout system that handles:

- sale ingestion
- advance payouts on pending sales
- final settlement after reconciliation
- withdrawal restrictions
- recovery of failed payouts

The assignment also requires a clear database design, class design, APIs, edge-case handling, and a working implementation.

## 2. Requirements

### Functional Requirements

- Store sales for each user and brand
- Process advance payout for eligible pending sales
- Prevent duplicate advance payout for the same sale
- Reconcile a sale to `approved` or `rejected`
- Calculate final settlement after reconciliation
- Maintain a withdrawable balance for each user
- Restrict withdrawals to one per 24 hours
- Recover failed, cancelled, or rejected withdrawals
- Maintain an auditable history of balance changes

### Non-Functional Requirements

- Idempotent payout processing
- Clear separation of responsibilities
- Auditable balance changes
- Easy local execution without external dependencies
- Design that can be extended to a persistent database-backed implementation

## 3. Design Approach

The design separates business state from money movement:

- `Sale`
  Represents the affiliate earning event.
- `Payout`
  Represents a transfer-related event such as advance payout, final settlement, withdrawal, or recovery.
- `UserWallet`
  Represents the user's current withdrawable balance.
- `LedgerEntry`
  Represents an immutable audit record for wallet changes.

This separation makes retries, reconciliation, and payout failure recovery easier to reason about and easier to audit.

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

The current implementation uses in-memory repositories, but the following relational schema maps directly to a production setup.

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
| `amount` | `decimal(12,2)` | signed amount |
| `entry_type` | `varchar` | domain event type |
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
2. Create sale in `pending` state
3. Ensure the user's wallet exists

### B. Advance Payout Job

1. Fetch all sales where:
   - `status = pending`
   - `advance_paid = false`
2. For each sale:
   - calculate `10%` of earning
   - create an advance payout
   - mark the sale as advance-paid
   - credit the wallet
   - write a ledger entry

Idempotency is enforced using the `advance_paid` marker on each sale.

### C. Reconciliation

Rules:

- A sale can be reconciled only once.
- Only `approved` and `rejected` are valid reconciliation states.

Computation:

- If `approved`: `earning - advance_paid_amount`
- If `rejected`: `-advance_paid_amount`

Example from the assignment:

| Sale Status | Earning | Advance Paid | Final Adjustment |
|---|---:|---:|---:|
| rejected | 40 | 4 | -4 |
| approved | 40 | 4 | 36 |
| approved | 40 | 4 | 36 |

Net final settlement after reconciliation: `68`

In the implementation, this value is exposed as `final_settlement_total`.  
The wallet balance may be higher because advance payouts are already credited before reconciliation.

### D. Withdrawal

1. Validate amount
2. Validate idempotency key
3. Enforce the 24-hour withdrawal rule
4. Check available balance
5. Create withdrawal payout with `initiated`
6. Deduct balance immediately
7. Write a ledger entry

### E. Failed Payout Recovery

If a withdrawal later becomes `failed`, `cancelled`, or `rejected`:

1. update the withdrawal status
2. credit the amount back to the wallet
3. create a recovery payout
4. write a recovery ledger entry

Duplicate callbacks with the same terminal state are treated idempotently.

## 9. API Design

A lightweight HTTP API is provided using Python's standard library.

### `POST /sales`

Creates a pending sale.

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

Reconciles a sale.

```json
{
  "status": "approved"
}
```

### `GET /users/{user_id}/wallet`

Returns wallet state, sales, payouts, ledger entries, and aggregates such as:

- `advance_paid_total`
- `final_settlement_total`

### `POST /withdrawals`

Initiates a withdrawal.

```json
{
  "userId": "john_doe",
  "amount": 20,
  "idempotencyKey": "withdrawal:john_doe:1"
}
```

### `POST /withdrawals/{payout_id}/status`

Updates the status of a withdrawal.

```json
{
  "status": "failed"
}
```

### `GET /health`

Simple health-check endpoint.

## 10. Edge Cases and Failure Handling

- Advance payout job runs multiple times: already processed sales are skipped.
- Same sale reconciled twice: blocked using the `finalized` flag.
- Duplicate withdrawal request: blocked using `idempotency_key`.
- Withdrawal within 24 hours: rejected.
- Failed, cancelled, or rejected withdrawal: amount is restored.
- Duplicate callback with same terminal state: treated idempotently.
- Conflicting second callback after terminal state: rejected.
- Rejected sale after advance payout: handled as a clawback adjustment.

## 11. Trade-offs

### Chosen Approach

- `Python`
  Keeps the domain logic concise and easy to read.
- `In-memory repositories`
  Keeps setup simple and makes the business rules the main focus.
- `Negative wallet balances allowed`
  Keeps rejected-sale clawback handling straightforward.

### Alternatives

- `SQLite` or `PostgreSQL`
  Better for persistence and transactional safety.
- separate debt tracking instead of negative balance
  Useful if the product disallows negative wallet balances.

## 12. Testing Strategy

The test suite covers:

- advance payout idempotency
- the assignment reconciliation example
- explicit final settlement total for the assignment example
- 24-hour withdrawal restriction
- failed withdrawal recovery
- duplicate reconciliation prevention
- duplicate withdrawal idempotency key rejection
- duplicate payout status update handling
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

## 14. Running the Project

### Run the API server

```bash
python main.py
```

Server address:

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

This project uses only the Python standard library, so no additional package installation is required.

### Windows Setup

1. Install Python 3.11 or newer from `python.org`.
2. Enable `Add python.exe to PATH` during installation.
3. Open a new terminal and verify:

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

- If `python` opens the Microsoft Store, disable the Python App Execution Alias in Windows settings.
- If the terminal still cannot find Python, reopen the terminal after installation.
- If both `python` and `py` fail, reinstall Python and ensure PATH was enabled.

## 16. Sample API Flow

### 1. Create sales

```bash
curl -X POST http://127.0.0.1:8000/sales ^
  -H "Content-Type: application/json" ^
  -d "{\"userId\":\"john_doe\",\"brand\":\"brand_1\",\"earning\":40}"
```

Repeat the request three times for the sample scenario.

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

### 4. Fetch user summary

```bash
curl http://127.0.0.1:8000/users/john_doe/wallet
```

## 17. Possible Production Improvements

- replace in-memory repositories with database-backed repositories
- wrap payout state changes in transactions
- add a payout provider abstraction
- verify callback authenticity
- add authentication and authorization
- maintain payout status transition history
- add retry handling around external payout operations
