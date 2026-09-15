import { Check, LoaderCircle } from "lucide-react";

const STEPS = [
  "Analyzing statement",
  "Extracting transactions",
  "Understanding merchants",
  "Categorizing spending",
  "Analyzing patterns",
  "Building your dashboard",
];

type Props = {
  currentStep: number;
  waiting: boolean;
};

export function AnalyzingScreen({ currentStep, waiting }: Props) {
  const visibleStep = Math.min(currentStep, STEPS.length - 1);

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 px-6">
      <div className="w-full max-w-md">
        <p className="mb-2 text-sm font-medium text-muted-foreground">
          Where Did My Money Go?
        </p>
        <h1 className="text-2xl font-bold">Reading your statement</h1>
        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full bg-foreground ${
              waiting ? "w-1/3 animate-progress-slide" : "w-full"
            }`}
          />
        </div>

        <ol className="mt-8 space-y-3">
          {STEPS.map((label, index) => {
            const done = index < visibleStep || (index === visibleStep && !waiting && currentStep >= STEPS.length);
            const active = !done && index === visibleStep;

            return (
              <li
                key={label}
                className={`flex items-center gap-3 rounded-lg border bg-card px-4 py-3 text-sm transition-colors ${
                  active ? "ring-1 ring-foreground/15" : ""
                }`}
              >
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full ${
                    done
                      ? "bg-green-600 text-white"
                      : active
                        ? "border border-foreground/30"
                        : "border border-muted-foreground/30 text-muted-foreground"
                  }`}
                >
                  {done ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : active ? (
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    index + 1
                  )}
                </span>
                <span className={done || active ? "font-medium" : "text-muted-foreground"}>
                  {label}
                </span>
              </li>
            );
          })}
        </ol>

        {waiting && (
          <p className="mt-6 animate-pulse text-sm text-muted-foreground">
            Still working — this can take a moment for longer statements.
          </p>
        )}
      </div>
    </main>
  );
}

export const ANALYSIS_STEPS = STEPS.length;
