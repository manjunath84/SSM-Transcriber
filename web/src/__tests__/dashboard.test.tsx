import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import BudgetPill from "../components/BudgetPill";

const transcriptsMock = vi.fn();
const meMock = vi.fn();

vi.mock("../hooks", () => ({
  useTranscripts: () => transcriptsMock(),
  useMe: () => meMock(),
}));

vi.mock("../auth", () => ({
  getIdToken: () => "fake-token",
  beginLogin: vi.fn(),
}));

async function renderDashboard() {
  const { default: Dashboard } = await import("../components/Dashboard");
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>,
  );
}

describe("Dashboard", () => {
  test("renders rows newest-first in returned order", async () => {
    transcriptsMock.mockReturnValue({
      data: [
        { jobId: "j2", lastModified: "2026-05-02T00:00:00Z" },
        { jobId: "j1", lastModified: "2026-05-01T00:00:00Z" },
      ],
      isLoading: false,
      isError: false,
    });
    meMock.mockReturnValue({ data: undefined, isLoading: false });
    await renderDashboard();
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(
      expect.arrayContaining(["j2", "j1"]),
    );
    expect(links[0].textContent).toContain("j2");
    expect(links[1].textContent).toContain("j1");
  });

  test("empty list shows empty state", async () => {
    transcriptsMock.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    meMock.mockReturnValue({ data: undefined, isLoading: false });
    await renderDashboard();
    expect(screen.getByText(/no transcripts yet/i)).toBeInTheDocument();
  });
});

describe("BudgetPill", () => {
  test("renders static $5 budget value (no usage math)", () => {
    render(<BudgetPill email="a@b.com" monthlyBudgetUsd={5} />);
    expect(screen.getByText(/\$5/)).toBeInTheDocument();
  });
});
