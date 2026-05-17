// Transcript viewer: markdown body + frontmatter sidebar + download + delete.
//
// Markdown render choice: PREFORMATTED TEXT (zero new deps). The body is
// rendered in a <pre> with wrapping; 7a does not need rich markdown and
// the plan explicitly allows the zero-dep path.

import { useNavigate, useParams } from "react-router-dom";
import { useDeleteTranscript, useTranscript } from "../hooks";
import { splitFrontmatter } from "../manifest";

function TranscriptViewer() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useTranscript(id);
  const del = useDeleteTranscript();

  if (isLoading) return <p>Loading…</p>;
  if (isError || !data) return <p>Could not load transcript.</p>;

  const { frontmatter, body } = splitFrontmatter(data.markdown);
  const entries = Object.entries(frontmatter);

  const downloadHref = `data:text/markdown;charset=utf-8,${encodeURIComponent(
    data.markdown,
  )}`;

  function onDelete() {
    if (!window.confirm(`Delete transcript ${id}?`)) return;
    del.mutate(id, { onSuccess: () => void navigate("/") });
  }

  return (
    <main className="viewer">
      <aside className="viewer-sidebar">
        <h2>Metadata</h2>
        {entries.length === 0 ? (
          <p>No metadata.</p>
        ) : (
          <dl>
            {entries.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        )}
        <a href={downloadHref} download={`${id}.md`}>
          Download
        </a>
        <button type="button" onClick={onDelete} disabled={del.isPending}>
          Delete
        </button>
      </aside>
      <article className="viewer-body">
        <pre style={{ whiteSpace: "pre-wrap" }}>{body}</pre>
      </article>
    </main>
  );
}

export default TranscriptViewer;
