import type { CashFlow, Summary, Transaction } from "@/lib/types";

const NOT_SPENDING = new Set(["PAYMENT", "TRANSFER", "REFUND"]);

export function isSpending(row: Transaction) {
  return (
    row.transaction_type === "DEBIT" &&
    !NOT_SPENDING.has(row.economic_type || "OTHER")
  );
}

export function mostActivePeriod(rows: Transaction[]) {
  const counts = new Map<string, number>();

  for (const row of rows) {
    const key = String(row.date).slice(0, 7);
    counts.set(key, (counts.get(key) || 0) + 1);
  }

  let best = "";
  let bestCount = -1;

  for (const [key, count] of counts) {
    if (count > bestCount || (count === bestCount && key > best)) {
      best = key;
      bestCount = count;
    }
  }

  const [year, month] = best.split("-").map(Number);
  return { year, month };
}

function inMonth(row: Transaction, year: number, month: number) {
  const stamp = String(row.date).slice(0, 7);
  return stamp === `${year}-${String(month).padStart(2, "0")}`;
}

function previousMonth(year: number, month: number) {
  if (month === 1) {
    return { year: year - 1, month: 12 };
  }
  return { year, month: month - 1 };
}

export function buildLocalSummary(
  rows: Transaction[],
  year: number,
  month: number,
): Summary {
  const current = rows.filter((row) => inMonth(row, year, month) && isSpending(row));
  const previous = previousMonth(year, month);
  const prior = rows.filter(
    (row) => inMonth(row, previous.year, previous.month) && isSpending(row),
  );

  const categoryMap = new Map<string, number>();
  for (const row of current) {
    categoryMap.set(row.category, (categoryMap.get(row.category) || 0) + Number(row.amount));
  }

  const category_breakdown = [...categoryMap.entries()]
    .map(([category, amount]) => ({ category, amount }))
    .sort((a, b) => b.amount - a.amount);

  const largest = [...current].sort((a, b) => b.amount - a.amount)[0];

  return {
    year,
    month,
    selected_month_spending: current.reduce((sum, row) => sum + Number(row.amount), 0),
    previous_month_spending: prior.reduce((sum, row) => sum + Number(row.amount), 0),
    category_breakdown,
    top_category: category_breakdown[0] || null,
    largest_transaction: largest
      ? {
          merchant: largest.merchant,
          amount: Number(largest.amount),
          category: largest.category,
          date: String(largest.date).slice(0, 10),
        }
      : null,
  };
}

export function buildLocalCashflow(
  rows: Transaction[],
  year: number,
  month: number,
): CashFlow {
  const current = rows.filter((row) => inMonth(row, year, month));
  const spending = current.filter(isSpending).reduce((sum, row) => sum + Number(row.amount), 0);
  const income = current
    .filter((row) => row.transaction_type === "CREDIT" && row.economic_type === "INCOME")
    .reduce((sum, row) => sum + Number(row.amount), 0);
  const refunds = current
    .filter((row) => row.transaction_type === "CREDIT" && row.economic_type === "REFUND")
    .reduce((sum, row) => sum + Number(row.amount), 0);
  const transfers_in = current
    .filter((row) => row.transaction_type === "CREDIT" && row.economic_type === "TRANSFER")
    .reduce((sum, row) => sum + Number(row.amount), 0);
  const transfers_out = current
    .filter((row) => row.transaction_type === "DEBIT" && row.economic_type === "TRANSFER")
    .reduce((sum, row) => sum + Number(row.amount), 0);

  return {
    year,
    month,
    money_in: income,
    refunds,
    money_out: spending,
    transfers_in,
    transfers_out,
    net_cash_flow: income + refunds - spending,
  };
}
