# Factory intent in the conversation

Manufacturing questions and confirmation belong in the chat host through HTTP/MCP operations. The STEP pane has no factory interview form. Read the [Specify reference](../../../../skills/open-skyfall/references/specify-one.md) before writing.

For an eligible synthetic owned case, analyse the actual current STEP with `GET /api/jobs/{id}/intent`. Compare its revision, hash, part scope, questions, suggested defaults, and unresolved fields. Do not turn suggestions into factory confirmation.

Submit `POST /api/jobs/{id}/intent` only with reviewed answers and the required confirmation. The body retains `revision`, `analysis_id`, `answers`, `confirmed`, and `accept_defaults`. Require incomplete or unconfirmed answers to refuse without creating a PMI artifact. Check supported PMI through an independent reader and preserve warnings and unwritten items in the conversational delivery.

After a geometry rebuild, reuse the old revision/analysis and require stale rejection without overwriting immutable outputs. Geometry validation, complete factory intent, target-reader PMI visibility, and manufacturing acceptance remain separate outcomes.

The registered native wiring cover rejects factory-intent operations. Its native edit does not pass this journey. Full smlibpy-to-intent acceptance stays blocked until the actual supported STEP path exists. Earlier workbench-form and legacy PMI evidence remains historical. Do not invent requirements or write intent to the user's real case merely to fill coverage.
