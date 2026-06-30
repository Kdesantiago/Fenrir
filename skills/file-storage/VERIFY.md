# VERIFY — file-storage

Run after `file-storage` has been applied to a repo. All BLOCKING checks must pass.

These checks are scoped to the **storage module** — the file(s) implementing the upload/download + `StoragePort` — not the whole repo. A repo-wide search is not falsifiable (a stray `open(` or `tempfile` import would pass with zero real storage code). Resolve the storage file(s) first, then run the co-located checks:

```
STO_FILES=$(grep -rlE 'StoragePort|UploadFile|copyfileobj|shutil\.|NamedTemporaryFile|mkdtemp|\.upload_blob|put\(|get_blob' --include='*.py' . )
echo "${STO_FILES:-<none — storage module not found, FAIL>}"
```
If `STO_FILES` is empty, the skill produced no wired storage layer → FAIL all blocking checks below.

## Blocking (the skill's output is incomplete/wrong if any fail)
- [ ] **storage port abstraction** — callers depend on a port, not a concrete backend: `for f in $STO_FILES; do grep -qE 'class \w*Storage\w*\(|StoragePort|Protocol\)|ABC\)' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-PORT`
- [ ] **size cap enforced** — an upload is bounded before/while reading, not unbounded: `for f in $STO_FILES; do grep -qE 'max_size|MAX_.*SIZE|content_length|413|size\s*>|len\(.*\)\s*>' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-SIZE-CAP`
- [ ] **content-type allowlist / magic-byte sniff** — type is validated, not trusted from the client: `for f in $STO_FILES; do grep -qE 'allowed_(types|content)|ALLOWED_|magic|imghdr|filetype|mimetypes|415|content_type\s+(in|not in)' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-TYPE-VALIDATION`
- [ ] **safe path — no caller-controlled traversal** — key is derived/validated, `..` and absolute paths rejected, final path checked under the root: `for f in $STO_FILES; do grep -qE 'uuid|secure_filename|sha256|resolve\(\)|commonpath|startswith\(.*root|\.\.\b' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-PATH-GUARD`
- [ ] **streamed, not buffered** — large files are chunked, not fully read into memory: `for f in $STO_FILES; do grep -qE 'copyfileobj|iter_content|stream|chunk|\.read\([0-9]|async for' "$f" && echo "OK $f"; done | grep -q OK && echo OK || echo MISSING-STREAMING`
- [ ] **temp-file hygiene** — a staged temp is cleaned on every path: `for f in $STO_FILES; do grep -qE 'NamedTemporaryFile|mkdtemp|mkstemp' "$f" && { grep -qE 'finally|os\.remove|os\.unlink|shutil\.rmtree|cleanup|delete=True' "$f" && echo "OK $f" || echo "TEMP-NO-CLEANUP in $f"; }; done | grep -q OK && echo OK || echo NOTE-no-temp-staging-confirm-direct-write`
- [ ] **no literal storage credential in source** (hard fail): `! grep -rEq '(AccountKey|connection_string|sas_token|access_key)\s*[:=]\s*["'\''][^"'\''$@{][^"'\'']+["'\'']' $STO_FILES && echo OK || echo CRED-LITERAL-FOUND`
- [ ] (profile-driven) `framework` in `org-profile.yaml` is the supported (FastAPI/Streamlit) shape

## Informational (tooling presence — does NOT block; note if absent)
- [ ] **magic-byte lib present** — advisory, NOT a gate (a hand-rolled signature check is valid): `python -c 'import magic' 2>/dev/null && echo "python-magic present" || echo "NOTE: no python-magic — confirm a hand-rolled magic-byte / mimetypes sniff is in place"`
- [ ] **Azure layer is opt-in only** — if `cloud_layer: azure`, an `azure-storage-blob` port impl may be present; its ABSENCE never fails (core is zero-cloud): `grep -rEq 'azure\.storage\.blob|BlobServiceClient|DefaultAzureCredential' . && echo "azure blob wiring present" || echo "NOTE: no Azure Blob wiring — expected for a local/zero-cloud user"`

## Functional
Exercise the byte path against the storage layer with no `az`/network call: (1) POST a file OVER the cap → rejected with 413 and process memory stays flat (not buffered); (2) POST a disallowed type renamed to an allowed extension → rejected 415 by magic-byte sniff; (3) POST/request a key containing `../` or an absolute path → rejected, nothing is written or read outside the storage root; (4) force a mid-write error → no temp file remains and no partial object is served; (5) round-trip a large file → the bytes returned equal the bytes stored and resident memory stays bounded throughout.
