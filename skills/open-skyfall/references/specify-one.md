# specify-one factory-intent reference

Added on 2026-11-02 in Europe/Madrid. The public Specify repository is the factory-intent reference. `specify-one` is the local reference alias. The upstream project is Specify, its repository is `pzfreo/specify-core`, and its executable is `specify-core`.

## Public source and revision

- Repository is [pzfreo/specify-core](https://github.com/pzfreo/specify-core).
- Inspected revision is [`ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f`](https://github.com/pzfreo/specify-core/commit/ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f). Git remote HEAD resolved to this revision during this update.
- [README](https://github.com/pzfreo/specify-core/blob/ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f/README.md) documents a deterministic Rust engine, CLI, Python package, and WebAssembly interface for interview-driven AP242 semantic PMI.
- [Python interface](https://github.com/pzfreo/specify-core/blob/ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f/crates/specify-core-py/README.md) documents part analysis, questions, preview, intent application, assembly writing, and write reports.
- [Face identity contract](https://github.com/pzfreo/specify-core/blob/ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f/docs/face-names.md) documents answer binding and revision refusals.
- [LICENSE](https://github.com/pzfreo/specify-core/blob/ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f/LICENSE) is Apache-2.0. Preserve its [NOTICE](https://github.com/pzfreo/specify-core/blob/ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f/NOTICE) when distributing the dependency. Third-party fixture and font notices are separate.

These are documentation observations. This update did not install Specify, execute its engine, or test PMI in a downstream CAD application. Pin a compatible release artifact separately before runtime integration. A source revision is not proof that a downloaded wheel matches it.

## Capture the factory's intent

Collect supplied requirements early so they guide decomposition and construction. Use a `FactoryIntent` record alongside the geometry document. The fields below are the proposed project contract, not a claimed upstream JSON schema.

| Field | Record |
| --- | --- |
| Scope and provenance | Project revision, part definition, optional occurrence scope, source document or factory statement, author, and confirmation status |
| Material | Required material and grade, with its source |
| Functional features | Hole purpose, thread requirements, fits, and mating function |
| Inspection requirements | Datums, dimensional and geometric tolerances, and surface finish |
| Other factory constraints | Process, machine access, batch quantity, and assembly instructions when supplied |
| STEP binding | Exact STEP hash, analysis version, question IDs, selected feature or face evidence, and upstream answer-evidence payload |
| Export result | Confirmed answers, unresolved requirements, supported PMI written, `not_written`, and warnings |

Keep a proposal distinct from a confirmed answer. A factory requirement that conflicts with the observed geometry needs an explicit correction or documented unresolved condition. Do not silently alter the requirement to fit the reconstructed shape.

Material, dimensions, tolerances, datums, fits, threads, surface texture, and supported notes can map to the documented PMI vocabulary. Do not assume every process, capacity, batch, or scheduling requirement has a semantic PMI encoding. Keep unsupported requirements in the sidecar with an explicit export status. Preserve occurrence-specific requirements separately. The inspected writer assigns assembly PMI to part definitions, not individual occurrences.

## Apply intent to the final STEP

1. Reconstruct and geometrically validate the parts. Preserve a geometry-only intermediate such as `assembly.geometry.step`.
2. Assemble the geometry before the final PMI pass. Use Specify's documented `parts` and `analyse` interfaces to inspect the actual STEP definitions. Bind each analysis to that exact file hash and the project's definition ID. Part indices and question IDs are local to that analysis.
3. Use `questions` and `preview` to present gaps and suggestions in the ChatGPT panel. Capture the factory's confirmations and preserve their provenance.
4. Translate confirmed requirements into the version-pinned answer format. The Python `apply` contract defaults to `accept_defaults=False`. Keep that behavior. Do not enable CLI `--accept-defaults` unless the user explicitly accepts the presented defaults.
5. Write all specified part definitions into the existing assembly using the documented assembly writer. Preserve every occurrence and placement. Avoid reassembling annotated standalone parts through a geometry exporter that may drop their PMI.
6. Preserve the writer's complete report. Treat required entries in `not_written`, relevant warnings, verification failure, and unresolved requirements as incomplete intent export. An output file or zero exit code alone is insufficient.
7. Re-read the final `assembly.step`. Verify requested semantics and their feature bindings in a target CAD or inspection tool. Also compare units, solids, definitions, occurrences, and placements against the geometry-only intermediate.

Keep geometry-only delivery available when the user wants it, but label missing or unverified factory intent. A Python or CLI integration belongs behind the existing service and needs no additional LLM or new hosted application.

## Rebuilds require new bindings

After a geometry edit, invalidate the previous analysis and PMI status. Reanalyse the new STEP and use upstream revision comparison or answer-rematching capabilities before applying old answers.

The inspected face-name contract accepts unique authored names in the explicit `f:` namespace for new persistent identities. Arbitrary semantic labels and integer face indices do not establish stable binding. Missing or duplicated saved names remain unresolved and do not fall back to geometry. Unnamed supports need the documented geometric evidence. Preserve the full upstream evidence payload beside externally stored answers.

Compatibility between this contract and the pinned text-to-cad exporter remains untested. Validate it using a dimension edit, a removed face, and duplicated face names. Never silently transfer a tolerance to the nearest surviving face.

## Integration acceptance

Require a repeated-part assembly with confirmed material, a fit or thread, datums, and a tolerance. Verify that each requirement belongs to the intended definition and feature. Confirm that repeated placements survive the final write. Reject a stale analysis after rebuild. Keep missing answers, unsupported requirements, and binding ambiguities visible.

Measure the deterministic PMI pass and factory-interview time separately from reconstruction. Provide identical confirmed factory input to every cost-comparison arm. Count interview and repair labor consistently. Do not report the addition of a reference as completed manufacturing-intent integration.
