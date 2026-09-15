import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sparkles } from "lucide-react";

type Message = {
  role: "user" | "assistant";
  text: string;
};

type Props = {
  onAsk: (question: string) => Promise<string>;
};

const EXAMPLES = [
  "How much did I spend on food?",
  "What was my biggest purchase?",
  "Compare July vs August.",
];

export function AssistantPage({ onAsk }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || loading) {
      return;
    }

    setInput("");
    setMessages((current) => [...current, { role: "user", text: trimmed }]);
    setLoading(true);

    try {
      const answer = await onAsk(trimmed);
      setMessages((current) => [
        ...current,
        { role: "assistant", text: answer },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          text:
            error instanceof Error
              ? error.message
              : "The assistant could not answer right now.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-4 w-4" />
          AI Financial Assistant
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          I only answer questions about your money and transactions.
        </p>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="rounded-full border bg-white px-3 py-1 text-xs hover:bg-muted"
              onClick={() => send(example)}
            >
              {example}
            </button>
          ))}
        </div>

        <div className="mb-4 max-h-[420px] space-y-3 overflow-y-auto rounded-lg border bg-muted/20 p-4">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Try “How much did I spend on food in August?”
            </p>
          )}
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                message.role === "user"
                  ? "ml-auto bg-primary text-primary-foreground"
                  : "bg-background"
              }`}
            >
              {message.text}
            </div>
          ))}
          {loading && (
            <p className="text-sm text-muted-foreground">
              Analyzing your transactions...
            </p>
          )}
        </div>

        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void send(input);
          }}
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about your finances..."
            className="h-10 flex-1 rounded-md border bg-white px-3 text-sm outline-none focus:ring-2"
          />
          <Button type="submit" disabled={loading}>
            Send
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
