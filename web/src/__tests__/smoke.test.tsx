import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";

vi.mock("../auth", () => ({
  getIdToken: () => null,
  beginLogin: vi.fn(),
  completeLogin: vi.fn(),
}));

test("app renders sign-in entry when unauthenticated", () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>,
  );
  expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
});
