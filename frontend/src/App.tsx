import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { ChangeEvent } from "react";
import { createPortal } from "react-dom";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  IndianRupee,
  Search,
  ShoppingBag,
  Upload,
  Wallet,
  TrendingUp,
  TrendingDown,
} from "lucide-react";

import { LandingPage } from "@/components/LandingPage";
import { AnalyzingScreen, ANALYSIS_STEPS } from "@/components/AnalyzingScreen";
import { LockedPreview } from "@/components/LockedPreview";
import { AssistantPage } from "@/components/AssistantPage";
import { apiFetch, clearToken, getToken, loginRequest, setToken, signupRequest } from "@/lib/api";
import { PREVIEW_KEY, formatMoney, getCategoryClass, months } from "@/lib/types";
import type {
  AuthUser,
  CashFlow,
  Insights,
  PreviewBundle,
  Summary,
  Transaction,
} from "@/lib/types";
import {
  buildLocalCashflow,
  buildLocalSummary,
  mostActivePeriod,
} from "@/lib/finance";

type Screen = "landing" | "guest-upload" | "analyzing" | "locked" | "app";
type AppTab = "dashboard" | "assistant" | "import";

function AppModal({
  children,
  onClose,
  labelledBy,
  className = "max-w-sm",
}: {
  children: ReactNode;
  onClose: () => void;
  labelledBy: string;
  className?: string;
}) {
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-6"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={`w-full rounded-xl border border-neutral-200 bg-white p-6 text-neutral-950 shadow-2xl ${className}`}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}

function readPreview(): PreviewBundle | null {
  const raw = sessionStorage.getItem(PREVIEW_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as PreviewBundle;
  } catch {
    return null;
  }
}

function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [tab, setTab] = useState<AppTab>("dashboard");
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [importReady, setImportReady] = useState(false);
  const [analysisStep, setAnalysisStep] = useState(0);
  const [analysisWaiting, setAnalysisWaiting] = useState(true);

  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [cashFlow, setCashFlow] = useState<CashFlow | null>(null);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedMonth, setSelectedMonth] = useState(8);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [sortBy, setSortBy] = useState("DATE_DESC");
  const [currentPage, setCurrentPage] = useState(1);
  const ITEMS_PER_PAGE = 10;

  const logout = () => {
    clearToken();
    sessionStorage.removeItem(PREVIEW_KEY);
    setUser(null);
    setTransactions([]);
    setSummary(null);
    setCashFlow(null);
    setInsights(null);
    setMessage("");
    setError("");
    setImportReady(false);
    setMenuOpen(false);
    setScreen("landing");
  };

  const handleAuthError = (err: unknown) => {
    if (err && typeof err === "object" && "status" in err && err.status === 401) {
      logout();
      return;
    }
    setError(err instanceof Error ? err.message : "Request failed.");
  };

  const fetchTransactions = async () => {
    const data = (await apiFetch("/transactions")) as Transaction[];
    setTransactions(data);
    return data;
  };

  const fetchSummary = async (year: number, month: number) => {
    setSummary((await apiFetch(`/summary?year=${year}&month=${month}`)) as Summary);
  };

  const fetchCashFlow = async (year: number, month: number) => {
    setCashFlow((await apiFetch(`/cashflow?year=${year}&month=${month}`)) as CashFlow);
  };

  const fetchInsights = async (year: number, month: number) => {
    try {
      setInsightsLoading(true);
      setInsights((await apiFetch(`/insights?year=${year}&month=${month}`)) as Insights);
    } catch (err) {
      console.error(err);
      setInsights(null);
    } finally {
      setInsightsLoading(false);
    }
  };

  const loadDashboard = async (year?: number, month?: number) => {
    try {
      setLoading(true);
      setError("");
      const rows = await fetchTransactions();
      if (rows.length === 0) {
        setSummary(null);
        setCashFlow(null);
        setInsights(null);
        return;
      }
      const latest = mostActivePeriod(rows);
      const nextYear = year ?? latest.year;
      const nextMonth = month ?? latest.month;
      setSelectedYear(nextYear);
      setSelectedMonth(nextMonth);
      await Promise.all([
        fetchSummary(nextYear, nextMonth),
        fetchInsights(nextYear, nextMonth),
        fetchCashFlow(nextYear, nextMonth),
      ]);
    } catch (err) {
      handleAuthError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const boot = async () => {
      const token = getToken();
      if (!token) {
        setScreen("landing");
        return;
      }
      try {
        const me = (await apiFetch("/auth/me")) as AuthUser;
        setUser(me);
        setScreen("app");
        await loadDashboard();
        if (readPreview()) {
          setImportReady(true);
        }
      } catch {
        clearToken();
        setScreen("landing");
      }
    };
    void boot();
  }, []);

  const completeAuth = async (
    username: string,
    password: string,
    mode: "login" | "signup",
  ) => {
    setAuthLoading(true);
    setAuthError("");
    try {
      const result =
        mode === "signup"
          ? await signupRequest(username, password)
          : await loginRequest(username, password);
      setToken(result.token);
      setUser(result.user);
      setScreen("app");
      setTab("dashboard");
      await loadDashboard();
      if (readPreview()) {
        setImportReady(true);
      }
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setAuthLoading(false);
    }
  };

  const importPreview = async () => {
    const preview = readPreview();
    if (!preview) {
      return;
    }
    try {
      setUploading(true);
      const payload = {
        source_file: preview.filename,
        transactions: preview.transactions.map((row) => ({
          merchant: row.merchant,
          amount: row.amount,
          category: row.category,
          transaction_type: row.transaction_type,
          date: String(row.date).slice(0, 10),
          description: row.description,
          economic_type: row.economic_type,
          transaction_fingerprint: row.transaction_fingerprint,
          category_confidence: row.confidence ?? row.category_confidence,
          category_reason: row.reason ?? row.category_reason,
          source_file: preview.filename,
        })),
      };
      const data = await apiFetch("/transactions/import-preview", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      sessionStorage.removeItem(PREVIEW_KEY);
      setImportReady(false);
      setMessage(
        `${data.imported} imported. ${data.duplicates} duplicates skipped.`,
      );
      await loadDashboard();
    } catch (err) {
      handleAuthError(err);
    } finally {
      setUploading(false);
    }
  };

  const runAnalysis = async (file: File) => {
    setScreen("analyzing");
    setAnalysisStep(0);
    setAnalysisWaiting(true);
    setError("");

    const formData = new FormData();
    formData.append("file", file);

    const animation = (async () => {
      for (let index = 0; index < ANALYSIS_STEPS - 1; index += 1) {
        setAnalysisStep(index);
        await new Promise((resolve) => setTimeout(resolve, 650));
      }
      setAnalysisStep(ANALYSIS_STEPS - 1);
    })();

    try {
      const request = user
        ? apiFetch("/documents/import", { method: "POST", body: formData })
        : apiFetch("/documents/preview", { method: "POST", body: formData });

      const [data] = await Promise.all([request, animation]);

      setAnalysisStep(ANALYSIS_STEPS);
      setAnalysisWaiting(false);
      await new Promise((resolve) => setTimeout(resolve, 450));

      if (user) {
        const imported = Number(data.imported ?? data.count ?? 0);
        const duplicates = Number(data.duplicates ?? 0);
        setMessage(
          imported === 0 && duplicates > 0
            ? `No new transactions added. ${duplicates} were already saved.`
            : `${imported} transactions imported. ${duplicates} duplicates skipped.`,
        );
        setScreen("app");
        setTab("dashboard");
        await loadDashboard();
        return;
      }

      const preview: PreviewBundle = {
        filename: file.name,
        transactions: data.transactions || [],
      };

      try {
        sessionStorage.setItem(PREVIEW_KEY, JSON.stringify(preview));
      } catch {
        // Preview still works in memory if storage is full.
      }

      try {
        applyPreview(preview);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not display preview.");
      }
      setScreen("locked");
    } catch (err) {
      setAnalysisWaiting(false);
      setError(err instanceof Error ? err.message : "File upload failed.");
      setScreen(user ? "app" : "guest-upload");
    }
  };

  const applyPreview = (preview: PreviewBundle) => {
    const rows = preview.transactions.map((row, index) => ({
      ...row,
      id: row.id ?? index + 1,
      date: String(row.date).slice(0, 10),
    }));
    setTransactions(rows);
    if (rows.length === 0) {
      setSummary(null);
      setCashFlow(null);
      return;
    }
    const period = mostActivePeriod(rows);
    setSelectedYear(period.year);
    setSelectedMonth(period.month);
    setSummary(buildLocalSummary(rows, period.year, period.month));
    setCashFlow(buildLocalCashflow(rows, period.year, period.month));
    setInsights(null);
  };

  const handleFileUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    const allowed = [".csv", ".pdf", ".xlsx", ".docx"];
    const extension = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!allowed.includes(extension)) {
      setError("Please select a CSV, PDF, XLSX, or DOCX file.");
      return;
    }
    setUploading(true);
    try {
      await runAnalysis(file);
    } finally {
      setUploading(false);
    }
  };

  const handleMonthChange = async (value: string) => {
    const month = Number(value);
    setSelectedMonth(month);
    setSearch("");
    setCategoryFilter("ALL");
    setTypeFilter("ALL");
    setSortBy("DATE_DESC");
    setCurrentPage(1);
    if (user && screen === "app") {
      await loadDashboard(selectedYear, month);
      return;
    }
    setSummary(buildLocalSummary(transactions, selectedYear, month));
    setCashFlow(buildLocalCashflow(transactions, selectedYear, month));
  };

  const deleteAllData = async () => {
    try {
      await apiFetch("/transactions", { method: "DELETE" });
      setConfirmDelete(false);
      setMessage("Your financial data has been deleted.");
      await loadDashboard();
    } catch (err) {
      handleAuthError(err);
    }
  };

  const categories = useMemo(
    () => Array.from(new Set(transactions.map((row) => row.category))).sort(),
    [transactions],
  );

  const filteredTransactions = useMemo(() => {
    let result = transactions.filter((transaction) => {
      const searchText = search.toLowerCase();
      const matchesSearch =
        transaction.merchant.toLowerCase().includes(searchText) ||
        (transaction.description || "").toLowerCase().includes(searchText);
      const matchesCategory =
        categoryFilter === "ALL" || transaction.category === categoryFilter;
      const matchesType =
        typeFilter === "ALL" || transaction.transaction_type === typeFilter;
      return matchesSearch && matchesCategory && matchesType;
    });

    result = [...result].sort((a, b) => {
      if (sortBy === "DATE_ASC") return a.date.localeCompare(b.date);
      if (sortBy === "AMOUNT_DESC") return b.amount - a.amount;
      if (sortBy === "AMOUNT_ASC") return a.amount - b.amount;
      return b.date.localeCompare(a.date);
    });
    return result;
  }, [transactions, search, categoryFilter, typeFilter, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filteredTransactions.length / ITEMS_PER_PAGE));
  const paginatedTransactions = filteredTransactions.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE,
  );

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const difference =
    summary && summary.previous_month_spending > 0
      ? ((summary.selected_month_spending - summary.previous_month_spending) /
          summary.previous_month_spending) *
        100
      : 0;
  const isSpendingDown = difference < 0;
  const hasTransactions = transactions.length > 0;

  const uploadCard = (
    <Card className={hasTransactions ? "mt-6" : "mt-2"}>
      <CardHeader>
        <CardTitle>Import Statement</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center">
          <Upload className="mb-3 h-8 w-8 text-muted-foreground" />
          <p className="font-medium">Upload your statement</p>
          <p className="mt-1 text-sm text-muted-foreground">
            PDF, CSV, XLSX or DOCX
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Your data stays private.
          </p>
          <input
            id="statement-upload"
            type="file"
            accept=".csv,.pdf,.xlsx,.docx"
            onChange={handleFileUpload}
            disabled={uploading}
            className="hidden"
          />
          <Button
            type="button"
            disabled={uploading}
            className="mt-4"
            onClick={() => document.getElementById("statement-upload")?.click()}
          >
            <Upload className="mr-2 h-4 w-4" />
            {uploading ? "Processing..." : "Choose Statement"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );

  const dashboardBody = (
    <>
      {error && (
        <Card className="mb-6 border-destructive">
          <CardContent className="pt-6 text-destructive">{error}</CardContent>
        </Card>
      )}
      {message && (
        <Card className="mb-6">
          <CardContent className="pt-6">{message}</CardContent>
        </Card>
      )}

      {hasTransactions && summary && (
        <>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">This Month</CardTitle>
                <Wallet className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {formatMoney(summary.selected_month_spending)}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {months[summary.month - 1]} {summary.year}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Previous Month</CardTitle>
                <IndianRupee className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {formatMoney(summary.previous_month_spending)}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Month-over-Month</CardTitle>
                {isSpendingDown ? <ArrowDownRight className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {difference > 0 ? "+" : ""}
                  {difference.toFixed(1)}%
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium">Top Category</CardTitle>
                <ShoppingBag className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                {summary.top_category ? (
                  <>
                    <div className="text-2xl font-bold">
                      {formatMoney(summary.top_category.amount)}
                    </div>
                    <Badge
                      variant="outline"
                      className={`mt-2 ${getCategoryClass(summary.top_category.category)}`}
                    >
                      {summary.top_category.category}
                    </Badge>
                  </>
                ) : (
                  <p>No data</p>
                )}
              </CardContent>
            </Card>
          </div>

          {cashFlow && (
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium">Money In</CardTitle>
                  <TrendingUp className="h-4 w-4 text-green-600" />
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold text-green-600">
                    +{formatMoney(cashFlow.money_in)}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium">Money Out</CardTitle>
                  <TrendingDown className="h-4 w-4 text-red-600" />
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-bold">-{formatMoney(cashFlow.money_out)}</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-sm font-medium">Net Cash Flow</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className={`text-2xl font-bold ${cashFlow.net_cash_flow >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {cashFlow.net_cash_flow >= 0 ? "+" : "-"}
                    {formatMoney(Math.abs(cashFlow.net_cash_flow))}
                  </p>
                </CardContent>
              </Card>
            </div>
          )}

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Spending by Category</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={summary.category_breakdown}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="category" />
                    <YAxis />
                    <Tooltip formatter={(value) => formatMoney(Number(value))} />
                    <Bar dataKey="amount" name="Spending" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Largest Purchase</CardTitle>
              </CardHeader>
              <CardContent>
                {summary.largest_transaction ? (
                  <div className="space-y-4">
                    <p className="text-3xl font-bold">
                      {formatMoney(summary.largest_transaction.amount)}
                    </p>
                    <p className="text-lg font-medium">
                      {summary.largest_transaction.merchant}
                    </p>
                    <Separator />
                    <div className="flex items-center justify-between">
                      <Badge
                        variant="outline"
                        className={getCategoryClass(summary.largest_transaction.category)}
                      >
                        {summary.largest_transaction.category}
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {summary.largest_transaction.date}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p>No transaction data.</p>
                )}
              </CardContent>
            </Card>
          </div>

          {user && screen === "app" && (
            <Card className="mt-6 overflow-hidden">
              <CardHeader className="border-b bg-muted/30">
                <CardTitle>AI Spending Insights</CardTitle>
              </CardHeader>
              <CardContent className="p-6">
                {insightsLoading ? (
                  <p className="text-sm text-muted-foreground">Analyzing your spending...</p>
                ) : insights ? (
                  <div className="space-y-6">
                    <p className="text-sm leading-6 text-muted-foreground">{insights.summary}</p>
                    <Separator />
                    <div className="space-y-3">
                      {insights.insights.map((insight) => (
                        <div key={insight} className="rounded-lg border bg-background p-4 shadow-sm">
                          <p className="text-sm">{insight}</p>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border bg-muted/30 p-5">
                      <p className="text-sm leading-6 text-muted-foreground">
                        {insights.recommendation}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No AI insights available.</p>
                )}
              </CardContent>
            </Card>
          )}

          <Card className="mt-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Transactions</CardTitle>
                <Badge variant="secondary">{filteredTransactions.length} transactions</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="mb-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                      setCurrentPage(1);
                    }}
                    placeholder="Search merchant..."
                    className="h-10 w-full rounded-md border bg-white pl-9 pr-3 text-sm outline-none focus:ring-2"
                  />
                </div>
                <Select value={categoryFilter} onValueChange={(value) => { setCategoryFilter(value); setCurrentPage(1); }}>
                  <SelectTrigger className="w-full bg-white"><SelectValue /></SelectTrigger>
                  <SelectContent className="z-[9999] min-w-[200px] bg-white text-black shadow-lg">
                    <SelectItem value="ALL">All Categories</SelectItem>
                    {categories.map((category) => (
                      <SelectItem key={category} value={category}>{category}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={typeFilter} onValueChange={(value) => { setTypeFilter(value); setCurrentPage(1); }}>
                  <SelectTrigger className="w-full bg-white"><SelectValue /></SelectTrigger>
                  <SelectContent className="z-[9999] min-w-[180px] bg-white text-black shadow-lg">
                    <SelectItem value="ALL">All Types</SelectItem>
                    <SelectItem value="DEBIT">Debit</SelectItem>
                    <SelectItem value="CREDIT">Credit</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={sortBy} onValueChange={(value) => { setSortBy(value); setCurrentPage(1); }}>
                  <SelectTrigger className="w-full bg-white"><SelectValue /></SelectTrigger>
                  <SelectContent className="z-[9999] min-w-[200px] bg-white text-black shadow-lg">
                    <SelectItem value="DATE_DESC">Newest First</SelectItem>
                    <SelectItem value="DATE_ASC">Oldest First</SelectItem>
                    <SelectItem value="AMOUNT_DESC">Highest Amount</SelectItem>
                    <SelectItem value="AMOUNT_ASC">Lowest Amount</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {paginatedTransactions.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  No transactions match your filters.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Merchant</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead className="text-right">Amount</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedTransactions.map((transaction) => (
                        <TableRow key={transaction.id ?? `${transaction.date}-${transaction.merchant}`}>
                          <TableCell>{transaction.date}</TableCell>
                          <TableCell className="font-medium">{transaction.merchant}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className={getCategoryClass(transaction.category)}>
                              {transaction.category}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={transaction.transaction_type === "DEBIT" ? "outline" : "secondary"}>
                              {transaction.transaction_type}
                            </Badge>
                          </TableCell>
                          <TableCell className={`text-right font-semibold ${transaction.transaction_type === "CREDIT" ? "text-green-600" : ""}`}>
                            {transaction.transaction_type === "CREDIT" ? "+" : "-"}
                            {formatMoney(transaction.amount)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {filteredTransactions.length > 0 && (
                <div className="mt-6 flex items-center justify-between border-t pt-4">
                  <p className="text-sm text-muted-foreground">
                    Showing {(currentPage - 1) * ITEMS_PER_PAGE + 1}–
                    {Math.min(currentPage * ITEMS_PER_PAGE, filteredTransactions.length)} of {filteredTransactions.length}
                  </p>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={currentPage === 1} onClick={() => setCurrentPage((page) => page - 1)}>
                      Previous
                    </Button>
                    <Button variant="outline" size="sm" disabled={currentPage === totalPages} onClick={() => setCurrentPage((page) => page + 1)}>
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </>
  );

  if (screen === "landing") {
    return (
      <LandingPage
        mode={authMode}
        error={authError}
        loading={authLoading}
        onModeChange={(mode) => {
          setAuthMode(mode);
          setAuthError("");
        }}
        onSubmit={(username, password) => {
          void completeAuth(username, password, authMode);
        }}
        onContinue={() => {
          setTransactions([]);
          setSummary(null);
          setCashFlow(null);
          setScreen("guest-upload");
        }}
      />
    );
  }

  if (screen === "analyzing") {
    return <AnalyzingScreen currentStep={analysisStep} waiting={analysisWaiting} />;
  }

  const shell = (
    <main className="min-h-screen bg-muted/30">
      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Where Did My Money Go?</h1>
            <p className="mt-1 text-muted-foreground">
              See it. Understand it. Improve it.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {hasTransactions && (
              <Select value={String(selectedMonth)} onValueChange={handleMonthChange}>
                <SelectTrigger className="w-[180px] bg-white">
                  <SelectValue>
                    {months[selectedMonth - 1]} {selectedYear}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="z-[9999] min-w-[180px] bg-white text-black shadow-lg">
                  {months.map((month, index) => (
                    <SelectItem key={month} value={String(index + 1)}>
                      {month} {selectedYear}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {user && (
              <div className="relative">
                <Button variant="outline" onClick={() => setMenuOpen((open) => !open)}>
                  {user.username}
                  <ChevronDown className="ml-1 h-4 w-4" />
                </Button>
                {menuOpen && (
                  <div className="absolute right-0 z-40 mt-2 w-48 rounded-lg border bg-white p-1 shadow-lg">
                    <button className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted" onClick={() => { setAccountOpen(true); setMenuOpen(false); }}>
                      My Account
                    </button>
                    <button className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted" onClick={() => { setConfirmDelete(true); setMenuOpen(false); }}>
                      Delete All Data
                    </button>
                    <button className="w-full rounded-md px-3 py-2 text-left text-sm hover:bg-muted" onClick={logout}>
                      Logout
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {user && (
          <div
            className="mb-6 inline-flex w-full max-w-md rounded-lg border bg-muted p-1"
            role="tablist"
            aria-label="Main sections"
          >
            {(
              [
                ["dashboard", "Dashboard"],
                ["assistant", "AI Assistant"],
                ["import", "Import"],
              ] as const
            ).map(([id, label]) => {
              const selected = tab === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => setTab(id)}
                  className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                    selected
                      ? "bg-neutral-950 text-white shadow-sm"
                      : "text-muted-foreground hover:bg-white/70 hover:text-foreground"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}

        {importReady && user && (
          <Card className="mb-6">
            <CardContent className="flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="font-medium">Your statement is ready.</p>
                <p className="text-sm text-muted-foreground">
                  Import the preview into your account.
                </p>
              </div>
              <Button onClick={() => void importPreview()} disabled={uploading}>
                Import to my account
              </Button>
            </CardContent>
          </Card>
        )}

        {screen === "guest-upload" && uploadCard}

        {screen === "app" && tab === "assistant" && (
          <AssistantPage
            onAsk={async (question) => {
              const data = await apiFetch("/assistant/ask", {
                method: "POST",
                body: JSON.stringify({ question }),
              });
              return data.answer as string;
            }}
          />
        )}

        {screen === "app" && tab === "import" && uploadCard}

        {((screen === "app" && tab === "dashboard") || screen === "locked") && (
          <>
            {loading && <p className="mb-6 text-muted-foreground">Loading dashboard...</p>}
            {!loading && !hasTransactions && user && tab === "dashboard" && (
              <Card>
                <CardContent className="py-16 text-center">
                  <p className="text-lg font-medium">No financial data yet.</p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Upload your first statement to understand where your money goes.
                  </p>
                  <Button className="mt-6" onClick={() => setTab("import")}>
                    Upload Statement
                  </Button>
                </CardContent>
              </Card>
            )}
            {dashboardBody}
            {screen === "app" && tab === "dashboard" && hasTransactions && uploadCard}
          </>
        )}
      </div>

      {accountOpen && (
        <AppModal labelledBy="account-title" onClose={() => setAccountOpen(false)}>
          <h2 id="account-title" className="text-lg font-semibold">
            My Account
          </h2>
          <p className="mt-3 text-sm text-neutral-700">
            Signed in as <strong>{user?.username}</strong>
          </p>
          <Button className="mt-6" variant="outline" onClick={() => setAccountOpen(false)}>
            Close
          </Button>
        </AppModal>
      )}

      {confirmDelete && (
        <AppModal
          labelledBy="delete-title"
          className="max-w-md"
          onClose={() => setConfirmDelete(false)}
        >
          <h2 id="delete-title" className="text-lg font-semibold">
            Delete all your financial data?
          </h2>
          <p className="mt-3 text-sm leading-6 text-neutral-600">
            This will permanently delete all transactions associated with your account. This action cannot be undone.
          </p>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void deleteAllData()}>
              Delete Everything
            </Button>
          </div>
        </AppModal>
      )}
    </main>
  );

  if (screen === "locked") {
    return (
      <LockedPreview
        onSignUp={() => {
          setAuthMode("signup");
          setScreen("landing");
        }}
        onLogIn={() => {
          setAuthMode("login");
          setScreen("landing");
        }}
      >
        {shell}
      </LockedPreview>
    );
  }

  return shell;
}

export default App;
