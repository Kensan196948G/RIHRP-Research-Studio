import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

function Broken(): JSX.Element {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("renders a recoverable error message instead of a blank screen", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("画面の表示中にエラーが発生しました");
    expect(screen.getByRole("button", { name: "再読み込み" })).toBeInTheDocument();
    spy.mockRestore();
  });
});
