export const API_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export const TOKEN_KEY = "wdmmg_token";
export const PREVIEW_KEY = "wdmmg_preview";

export const months = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export type Transaction = {
  id?: number;
  merchant: string;
  amount: number;
  category: string;
  transaction_type: string;
  economic_type?: string | null;
  date: string;
  description?: string | null;
  created_at?: string | null;
  transaction_fingerprint?: string;
  confidence?: number;
  reason?: string;
  category_confidence?: number | null;
  category_reason?: string | null;
  source_file?: string | null;
};

export type Summary = {
  year: number;
  month: number;
  selected_month_spending: number;
  previous_month_spending: number;
  category_breakdown: { category: string; amount: number }[];
  top_category: { category: string; amount: number } | null;
  largest_transaction: {
    merchant: string;
    amount: number;
    category: string;
    date: string;
  } | null;
};

export type Insights = {
  summary: string;
  insights: string[];
  recommendation: string;
};

export type CashFlow = {
  year: number;
  month: number;
  money_in: number;
  refunds: number;
  money_out: number;
  transfers_in: number;
  transfers_out: number;
  net_cash_flow: number;
};

export type AuthUser = {
  id: number;
  username: string;
};

export type PreviewBundle = {
  filename: string;
  transactions: Transaction[];
};

export const getCategoryClass = (category: string) => {
  switch (category) {
    case "Food":
      return "border-orange-200 bg-orange-100 text-orange-700";
    case "Shopping":
      return "border-blue-200 bg-blue-100 text-blue-700";
    case "Entertainment":
      return "border-purple-200 bg-purple-100 text-purple-700";
    case "Transport":
      return "border-green-200 bg-green-100 text-green-700";
    case "Travel":
      return "border-cyan-200 bg-cyan-100 text-cyan-700";
    case "Bills":
      return "border-yellow-200 bg-yellow-100 text-yellow-700";
    case "Healthcare":
      return "border-red-200 bg-red-100 text-red-700";
    case "Subscriptions":
      return "border-pink-200 bg-pink-100 text-pink-700";
    default:
      return "border-gray-200 bg-gray-100 text-gray-700";
  }
};

export const formatMoney = (amount: number) =>
  `₹${amount.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
