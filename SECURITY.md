# Security

Do not include credentials or private customer geometry in public issues.
Use GitHub's private vulnerability reporting on this repository when available.
If it is unavailable, ask a maintainer for a private reporting channel without
posting exploit details or affected private data publicly.

The service binds to loopback. It is a local research tool, not a hardened public
CAD execution service. The registered native executor uses trusted pinned source;
HTTP input cannot choose a Python file or interpreter. Run newly authored scripts
only in an environment appropriate for code you have reviewed.

Preserve input and artifact hashes. A read-only native case adapter refuses
output whose bound artifacts or validation reports have changed. Do not bypass
those checks to present an unverified result as accepted CAD.
