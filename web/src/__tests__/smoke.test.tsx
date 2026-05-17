import { render, screen } from "@testing-library/react";
import App from "../App";

test("app renders sign-in entry", () => {
  render(<App />);
  expect(screen.getByText(/sign in with google/i)).toBeInTheDocument();
});
