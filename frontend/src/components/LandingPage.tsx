import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Props = {
  mode: "login" | "signup";
  error: string;
  loading: boolean;
  onModeChange: (mode: "login" | "signup") => void;
  onSubmit: (username: string, password: string) => void;
  onContinue: () => void;
};

export function LandingPage({
  mode,
  error,
  loading,
  onModeChange,
  onSubmit,
  onContinue,
}: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 px-6 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight">
            Where Did My Money Go?
          </h1>
          <p className="mt-2 text-muted-foreground">
            See it. Understand it. Improve it.
          </p>
        </div>

        <Card>
          <CardContent className="pt-6">
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                onSubmit(username.trim(), password);
              }}
            >
              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Username
                </label>
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  className="h-10 w-full rounded-md border bg-white px-3 text-sm outline-none focus:ring-2"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete={
                    mode === "signup" ? "new-password" : "current-password"
                  }
                  className="h-10 w-full rounded-md border bg-white px-3 text-sm outline-none focus:ring-2"
                />
              </div>

              {error && (
                <p className="text-sm text-destructive">{error}</p>
              )}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading
                  ? "Please wait..."
                  : mode === "signup"
                    ? "Create account"
                    : "Log in"}
              </Button>
            </form>

            <button
              type="button"
              className="mt-4 w-full text-sm text-muted-foreground underline-offset-4 hover:underline"
              onClick={() =>
                onModeChange(mode === "login" ? "signup" : "login")
              }
            >
              {mode === "login"
                ? "Need an account? Sign up"
                : "Already have an account? Log in"}
            </button>

            <div className="my-5 h-px bg-border" />

            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={onContinue}
            >
              Continue without signing in
            </Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
