import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";
import { splitFrontmatter } from "../manifest";

vi.mock("../hooks", () => ({
  useTranscript: () => ({
    data: { markdown: "---\ntitle: T\n---\n# H", rawPresent: true },
    isLoading: false,
    isError: false,
  }),
  useDeleteTranscript: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe("splitFrontmatter", () => {
  test("splits leading --- fenced key:value block from body", () => {
    const md = "---\ntitle: X\nprovider: assemblyai\n---\n# Body\ntext";
    expect(splitFrontmatter(md)).toEqual({
      frontmatter: { title: "X", provider: "assemblyai" },
      body: "# Body\ntext",
    });
  });

  test("no frontmatter returns empty map + original body", () => {
    const md = "# Just a body\nno fences";
    expect(splitFrontmatter(md)).toEqual({
      frontmatter: {},
      body: "# Just a body\nno fences",
    });
  });

  test("empty input is handled", () => {
    expect(splitFrontmatter("")).toEqual({ frontmatter: {}, body: "" });
  });

  test("frontmatter block with no body", () => {
    expect(splitFrontmatter("---\ntitle: Only\n---\n")).toEqual({
      frontmatter: { title: "Only" },
      body: "",
    });
  });
});

describe("TranscriptViewer", () => {
  test("renders markdown body and frontmatter title in sidebar", async () => {
    const { default: TranscriptViewer } = await import(
      "../components/TranscriptViewer"
    );
    render(
      <MemoryRouter initialEntries={["/t/j1"]}>
        <Routes>
          <Route path="/t/:id" element={<TranscriptViewer />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText(/# H/)).toBeInTheDocument();
    expect(screen.getByText("T")).toBeInTheDocument();
  });
});
