# TripSync Backend — Dependency Security Report

**Generated:** 2026-07-19T17:28:22.367Z  
**File:** requirements.txt

---

## Dependency Analysis

| Package | Installed | Latest | Severity | Notes |
|---------|-----------|--------|----------|-------|
| fastapi | >=0.100.0,<1.0.0 | 0.115.x | INFO | fastapi version should be kept updated |
| uvicorn | >=0.22.0,<1.0.0 | 0.32.x | INFO | uvicorn version should be kept updated |
| pydantic | >=2.0.0,<3.0.0 | 2.10.x | INFO | pydantic version should be kept updated |
| openai | >=1.0.0,<2.0.0 | 1.58.x | INFO | openai version should be kept updated |
| httpx | >=0.24.0,<1.0.0 | 0.28.x | INFO | httpx version should be kept updated |
| sentence-transformers | >=2.2.0 | check PyPI | LOW | sentence-transformers uses minimum version constraint (>=) without upper bound. May install untested versions. |
| qdrant-client | >=1.3.0 | check PyPI | LOW | qdrant-client uses minimum version constraint (>=) without upper bound. May install untested versions. |
| firebase-admin | >=6.2.0,<7.0.0 | 6.6.x | INFO | firebase-admin version should be kept updated |
| python-multipart | >=0.0.7 | 0.0.20 | LOW | python-multipart uses minimum version constraint (>=) without upper bound. May install untested versions. |
| python-multipart | >=0.0.7 | 0.0.20 | MEDIUM | Verify python-multipart >= 0.0.7 to avoid form parsing vulnerabilities |
| slowapi | >=0.1.9 | check PyPI | LOW | slowapi uses minimum version constraint (>=) without upper bound. May install untested versions. |
| email-validator | >=2.0.0 | check PyPI | LOW | email-validator uses minimum version constraint (>=) without upper bound. May install untested versions. |
| JWT library (MISSING) | not installed | python-jose>=3.3.0 or PyJWT>=2.8.0 | HIGH | No JWT verification library installed. Token verification relies on firebase-admin only. |

## Security Recommendations

1. **Pin all dependency versions** using exact pins (==) instead of minimum (>=)
2. **Install slowapi** for rate limiting
3. **Run pip-audit** regularly: `pip install pip-audit && pip-audit`
4. **Use virtual environments** and lock file for reproducible deployments
5. **Enable Dependabot** or Renovate for automated dependency updates
