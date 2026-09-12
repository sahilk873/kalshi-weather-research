You are maintaining a Kalshi development project that uses:

* the official Kalshi Python SDK
* `openapi.yaml` for the REST API specification
* `asyncapi.yaml` for the WebSocket specification

Your job is to keep these dependencies/specifications current without breaking the codebase.

Tasks:

1. Check the currently installed/pinned Kalshi SDK version in the project.
2. Check whether a newer official Kalshi Python SDK version exists.
3. Do NOT automatically upgrade the SDK if a newer version exists.
4. Instead:

   * report the current version
   * report the latest available version
   * summarize relevant release/changelog differences if available
   * flag any potentially breaking changes
5. Refresh the Kalshi REST OpenAPI specification by downloading the latest official `openapi.yaml`.
6. Refresh the Kalshi WebSocket AsyncAPI specification by downloading the latest official `asyncapi.yaml`.
7. Store them under:

```text
specs/openapi.yaml
specs/asyncapi.yaml
```

8. Before overwriting the existing specs, compare the old and new versions and summarize meaningful API changes, including:

   * added endpoints
   * removed endpoints
   * deprecated endpoints
   * renamed parameters
   * new or removed fields
   * schema/type changes
   * authentication changes
   * pagination changes
   * WebSocket channel changes
   * WebSocket message/schema changes

9. If the specs changed, preserve the updated files and produce a concise diff summary.

10. Inspect the existing Kalshi client/data-ingestion code and determine whether any spec changes require code changes.

11. Do not modify working application code unless necessary to remain compatible with the current Kalshi API.

12. If code changes are necessary:

* make the smallest compatible change
* preserve existing interfaces where possible
* update/add tests
* explain exactly why each change was required

13. Run the project's relevant tests after any SDK or compatibility changes.

14. Keep the Kalshi SDK version pinned in the dependency file. Never change it to an unpinned `latest` dependency.

15. If upgrading the SDK appears safe and useful, present the proposed version bump and compatibility findings before making the upgrade unless explicitly instructed to upgrade automatically.

Use the official Kalshi documentation/specification as the source of truth. Do not infer endpoints or fields from blog posts, old examples, or unofficial wrappers when the official specification disagrees.

Suggested refresh commands:

```bash
mkdir -p specs

curl -L https://docs.kalshi.com/openapi.yaml \
  -o /tmp/kalshi-openapi-new.yaml

curl -L https://docs.kalshi.com/asyncapi.yaml \
  -o /tmp/kalshi-asyncapi-new.yaml
```

Compare them against:

```text
specs/openapi.yaml
specs/asyncapi.yaml
```

before replacing the existing files.

At the end, output a maintenance report in this format:

```text
Kalshi API Maintenance Report

SDK
- Current version:
- Latest version:
- Upgrade recommended: yes/no
- Relevant changes:

REST OpenAPI
- Changed: yes/no
- Added endpoints:
- Removed/deprecated endpoints:
- Schema changes:
- Code impact:

WebSocket AsyncAPI
- Changed: yes/no
- Channel changes:
- Message/schema changes:
- Code impact:

Codebase
- Files inspected:
- Files modified:
- Tests run:
- Test result:

Recommended action
- ...
```

If there are no meaningful changes, say so and leave the application code untouched.

