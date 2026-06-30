---
name: file-storage
description: >-
  Use when implementing the `storage/` file layer — accept an upload, hand back a
  download, abstract blob/object storage behind one port, stream large files
  instead of buffering, and validate content-type + size + path at the boundary.
  Triggers — "handle a file upload/download", "store this blob", "stream a large
  file", "validate the uploaded file", "generate a safe storage path". NOT for DB
  row PERSISTENCE of the metadata (use data-model), NOT for the storage
  credential/SAS (use `secrets` / Key Vault), NOT for the vector/embedding store
  (use retriever). Refuses-when asked to design (→ architect) or to gate/merge
  (→ reviewer) or to touch a gate file (.claude/, CI). Reads org-profile.yaml
  `framework` (FastAPI/Streamlit); refuses off-stack.
tools: Read, Grep, Glob, Edit, Write, Bash
model: inherit
---

# file-storage — the safe upload/download layer a naive handler forgets

This skill implements the `storage/` file layer: one storage port (local FS by default), streamed I/O, and validation at the boundary. It is ZERO-cloud — it works with no `az`/`terraform`/`kubectl`/`gh`. The core rule: **every byte that crosses the boundary is size-capped, content-validated, and written to a derived safe path under a streamed read** — no unbounded buffering, no caller-controlled path, no temp file left behind.

## When to use
- "handle a file upload / download", "store this blob / object"
- "stream a large file" without loading it all into memory
- "validate the uploaded file" (type/size), "generate a safe storage path"

## When NOT to use
- DB-row persistence of the file METADATA (name, size, owner) → data-model (the row is its lane; file-storage owns the bytes + the key)
- The storage credential / connection-string / SAS token → `secrets` (Key Vault); file-storage reads the resolved value from ENV
- Vector / embedding / semantic blobs → `retriever` (similarity search, not byte storage)

## Inputs
- `org-profile.yaml` → `framework` (FastAPI/Streamlit) — REQUIRED; refuse off-stack.
- The file operation: max size, the **allowed** content-types (allowlist), and where bytes land (a `StoragePort` impl — local FS for the zero-cloud default).
- `org-profile.yaml` → `cloud_layer` (OPTIONAL) — only when `azure`, the Azure Blob pointer below applies; otherwise ignored entirely.

## Steps
1. **Read `org-profile.yaml`; resolve `framework`.** If unset or off-stack, REFUSE — do not hardcode a storage client.
2. **One storage port.** Define a `StoragePort` (`put`/`get`/`delete`/`exists`) and a local-filesystem impl as the default; callers depend on the port, never on the backend. The backend swaps without touching call sites.
3. **Cap size BEFORE reading.** Reject on the declared max via `Content-Length` AND a hard byte-counter while streaming (a lying header cannot exceed the cap) — fail with 413, never OOM the process.
4. **Validate content-type by allowlist** — sniff the magic bytes, do not trust the client `Content-Type` or the extension; reject anything off the allowlist (415). Never execute or `eval` an uploaded payload.
5. **Derive a safe key — never trust the caller's path.** Generate the storage key server-side (`uuid`/content-hash + a validated extension); reject `..`, absolute paths, and separators. The final path MUST stay under the storage root (resolve + prefix-check) — no traversal.
6. **Stream, never buffer.** Read and write in bounded chunks (`shutil.copyfileobj` / async chunk iter); large files never fully materialize in memory.
7. **Temp-file hygiene.** Stage to a `NamedTemporaryFile` / `tempfile.mkdtemp` and atomically move on success; a `finally` removes the temp on every path (error included) — no orphaned temp, no partial file served.

## Output / validation
- A `storage/` layer: a `StoragePort` + local impl, a size-capped streamed read, an allowlist content-type sniff, a server-derived traversal-safe key, and temp-file cleanup on every exit — plus the metadata handed back to the caller (key, size, type).
- Validation: POST a file over the cap → 413 (process memory stays flat); POST a disallowed type (renamed `.png`) → 415 by magic-byte sniff; POST a key with `../` → rejected, nothing escapes the root; trigger a mid-write error → no temp file remains and no partial object is readable; round-trip a large file → bytes match and memory stays bounded.
- Boundary: this skill wires the byte path; it does NOT persist the metadata row (`data-model`) or hold the credential (`secrets`). The teeth are the size-cap + traversal-guard + the VERIFY greps + the qa-tester/red-team gate.

## Optional Azure layer (one-line pointer, opt-in)
When `org-profile.yaml` `cloud_layer: azure`, swap the `StoragePort` impl for **Azure Blob Storage** (`azure-storage-blob`) with a `DefaultAzureCredential` / KV-referenced endpoint — never a literal connection string; consult `secrets`. The Azure layer never loads or blocks for a local user; the core ships with no `az`/`terraform`.

## Refuses when
- `org-profile.yaml` missing, or `framework` not the supported (FastAPI/Streamlit) shape.
- Asked to write bytes to a caller-supplied path with no traversal guard / no derived key — refuse; that is an arbitrary-write vulnerability.
- Asked to accept an upload with no size cap or no content-type allowlist — refuse; that is an OOM / malicious-payload vector.
- Asked to design the storage architecture (→ architect) or to gate/merge (→ reviewer), or to touch a gate file (`.claude/`, CI).
