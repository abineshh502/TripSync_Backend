# TripSync Backend — API Endpoint Inventory

**Generated:** 2026-07-19T17:28:22.367Z  
**Total Endpoints:** 21

---

## Security Summary

| Metric | Count |
|--------|-------|
| Total Endpoints | 21 |
| Endpoints with Auth | 17 |
| Endpoints without Auth | 4 |
| Endpoints with Rate Limiting | 16 |
| Endpoints with Input Validation | 17 |

## Endpoint Details

| Method | Route | Function | Auth | JWT | Input Validation | Rate Limit | Notes |
|--------|-------|----------|------|-----|-----------------|------------|-------|
| **GET** | `/` | `read_root` | ❌ | ❌ | ⚠️ | ✅ | No auth dependency detected; Minimal input validation |
| **GET** | `/` | `read_root` | ❌ | ❌ | ⚠️ | ❌ | No auth dependency detected; Minimal input validation; No rate limiting |
| **POST** | `/api/briefing` | `briefing_helper` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/chat` | `chat_helper` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/expenses/split` | `split_expense` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/itinerary/generate` | `generate_itinerary` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/otp/send` | `send_otp_email_endpoint` | ❌ | ❌ | ⚠️ | ✅ | No auth dependency detected; Minimal input validation |
| **POST** | `/api/otp/verify` | `verify_otp_endpoint` | ❌ | ❌ | ⚠️ | ✅ | No auth dependency detected; Minimal input validation |
| **GET** | `/api/protected` | `handler` | ✅ | ✅ | ✅ | ❌ | No rate limiting |
| **POST** | `/api/routes/optimize` | `optimize_route` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/routes/share` | `share_route_endpoint` | ✅ | ❌ | ✅ | ✅ |  |
| **GET** | `/api/safety` | `safety_score` | ✅ | ❌ | ✅ | ✅ |  |
| **GET** | `/api/trips` | `get_trips` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/trips` | `create_trip` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/voice/respond` | `voice_respond_helper` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/api/voice/transcribe` | `transcribe_voice` | ✅ | ❌ | ✅ | ✅ |  |
| **GET** | `/api/weather` | `weather_proxy` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/chat` | `chat_helper` | ✅ | ❌ | ✅ | ❌ | No rate limiting |
| **GET** | `/health` | `health_check` | ✅ | ❌ | ✅ | ✅ |  |
| **POST** | `/routes/optimize` | `optimize_route` | ✅ | ❌ | ✅ | ❌ | No rate limiting |
| **GET** | `/safety` | `safety_score` | ✅ | ❌ | ✅ | ❌ | No rate limiting |

## Unauthenticated Endpoints (HIGH RISK)

⚠️ **2 endpoints lack authentication:**

- `POST /api/otp/send` → `send_otp_email_endpoint()`
- `POST /api/otp/verify` → `verify_otp_endpoint()`
