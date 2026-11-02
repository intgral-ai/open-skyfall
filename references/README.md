# Upstream skills and provenance

Retrieved on 2026-11-02. The vendored text-to-cad files are unmodified research copies. The specify-one reference is a project-authored integration note. No upstream runtime or global skill was installed.

The source is [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad) at revision [`5efa85a911d9d0d3802fe516fe3c8cc387c47ea8`](https://github.com/earthtojake/text-to-cad/commit/5efa85a911d9d0d3802fe516fe3c8cc387c47ea8). The corresponding released plugin revision observed during research is [`fa74864fc464c9a36ea9695d6e0760a68f44d2f9`](https://github.com/earthtojake/text-to-cad/commit/fa74864fc464c9a36ea9695d6e0760a68f44d2f9). This records the source inspected, not a promise of future stability.

| Saved component | Purpose in this project | Limit |
| --- | --- | --- |
| [smlibpy kernel reference](../skills/open-skyfall/references/smlibpy.md) | Required native construction and STEP export for new reconstruction work; verified local environment and API | The legacy automated fitter and printer producer have not been migrated. A dependency probe does not validate a user case. |
| [CAD skill](upstream/text-to-cad/skills/cad/SKILL.md) and all its references | Part modeling, measurement, assembly, inspection, and export contracts | Does not reconstruct arbitrary STL assemblies automatically |
| [Standard-parts skill](upstream/text-to-cad/skills/step-parts/SKILL.md) and its downloader | Find exact catalog hardware and preserve asset provenance | Catalog availability and asset redistribution rights require separate checks |
| [Root MIT license](upstream/text-to-cad/LICENSE) and skill licenses | Preserve upstream notices | Does not license third-party dependencies or downloaded CAD assets |
| [File lock](upstream-lock.json) | Record source URLs, revision, Git blob IDs, byte counts, and SHA-256 | Records this snapshot only |
| [specify-one factory-intent reference](../skills/open-skyfall/references/specify-one.md) | Public Specify repository, pinned interface evidence, and AP242 manufacturing-intent handoff | Documentation reference only. Runtime integration and target-tool PMI verification remain untested. |

The snapshot contains 18 files and 143,166 bytes including the root license. Retrieval checked every file against its upstream Git blob ID. The lock also records each file's SHA-256.

The upstream snapshot documents its own build123d workflow. It is a reference, not an active OpenSkyfall executor or a replacement for the required smlibpy kernel.

The native-kernel requirement is smlibpy for new reconstruction work. The project-authored kernel reference takes precedence over these historical cadgen/build123d execution examples. Vendored upstream files remain unmodified.

The [Anatomy repository](https://github.com/wheresryan22/anatomy) is a visual reference for exploded diagrams. The installed local skill was inspected. Its upstream revision observed during research is [`1482e8469b0a9e0d8cc18ea2740a01423d29ae80`](https://github.com/wheresryan22/anatomy/commit/1482e8469b0a9e0d8cc18ea2740a01423d29ae80). No Anatomy files were copied or installed. It does not supply semantic segmentation, B-rep reconstruction, or STEP export.

The project-local [OpenSkyfall skill](../skills/open-skyfall/SKILL.md) now routes factory-intent work to `references/specify-one.md`. The public source is [pzfreo/specify-core](https://github.com/pzfreo/specify-core), not a repository literally named specify-one. The inspected revision is `ac5d31bd5fe04b7b02a1987d84c8fb9879640d2f`. Its source was read for this reference but was not vendored into the text-to-cad snapshot or installed globally.
