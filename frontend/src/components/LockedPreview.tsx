import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type Props = {
  children: ReactNode;
  onSignUp: () => void;
  onLogIn: () => void;
};

export function LockedPreview({ children, onSignUp, onLogIn }: Props) {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="pointer-events-none select-none blur-xl">
        {children}
      </div>

      <div className="absolute inset-0 flex items-center justify-center bg-background/55 px-6">
        <Card className="w-full max-w-md shadow-lg">
          <CardContent className="pt-6 text-center">
            <h2 className="text-2xl font-bold">See where your money went</h2>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Create an account or log in to unlock your full financial
              dashboard. Your statement is not saved until you sign in.
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <Button onClick={onSignUp}>Sign Up</Button>
              <Button variant="outline" onClick={onLogIn}>
                Log In
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
