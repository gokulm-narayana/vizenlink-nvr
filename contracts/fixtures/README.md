# Golden Fixtures

This directory contains golden fixtures used across contract and protocol tests for VizenLink NVR.

## Provenance Requirements

Every fixture file in this directory tree (except this `README.md`) must carry traceable provenance to a vendored contract source file listed in `contracts/camera_api.lock.json`.

### JSON Fixtures
JSON fixtures must be structured with a top-level `source` object and a `data` object:
```json
{
  "source": {
    "path": "contracts/camera_api/path/to/vendored/file.dart",
    "lines": "10-25"
  },
  "data": { ... }
}
```

### XML Fixtures
XML fixtures must begin with an XML comment pointing to the source file and line range:
```xml
<!-- source: contracts/camera_api/path/to/vendored/file.xml#L10-L25 -->
<soap:Envelope ...>
...
</soap:Envelope>
```

All fixtures are verified for provenance in `tests/contract/test_fixtures_provenance.py`.
