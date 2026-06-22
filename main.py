import math
import uvicorn
import os
import shutil
import tempfile
from fastapi import FastAPI, Query, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# Load .env file manually at startup if it exists
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split("=", 1)
                if len(parts) == 2:
                    key, val = parts
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")


# ─── App Initialization ──────────────────────────────────────────────────────
app = FastAPI(
    title="TripSync Core AI Backend Service",
    description="Scalable async FastAPI backend for AI Chatbot, travel safety, TSP route solver & more.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ──────────────────────────────────────────────────────────
class RouteSpot(BaseModel):
    name: str
    latitude: float
    longitude: float

class ChatMessageItem(BaseModel):
    role: str
    content: str

class ChatMessage(BaseModel):
    message: str
    history: Optional[List[ChatMessageItem]] = []

class VoiceRespondRequest(BaseModel):
    query: str
    context: dict

class TripCreate(BaseModel):
    title: str
    destination: str
    startDate: str
    endDate: str
    userId: str
    description: Optional[str] = ""

class ExpenseSplit(BaseModel):
    totalAmount: float
    members: List[str]
    description: Optional[str] = ""

class BriefingRequest(BaseModel):
    userName: str
    activeTripName: Optional[str] = None
    activeTripDestination: Optional[str] = None
    todayScheduleTitle: Optional[str] = None
    todayScheduleSpots: Optional[List[str]] = []
    upcomingTripName: Optional[str] = None
    upcomingTripDestination: Optional[str] = None
    upcomingTripDays: Optional[int] = None
    groupName: Optional[str] = None
    groupExpensesCount: Optional[int] = 0
    groupMembersCount: Optional[int] = 1
    groupLastExpenseAmount: Optional[float] = 0.0
    groupLastExpenseDesc: Optional[str] = None
    weatherTemp: Optional[float] = None
    weatherDesc: Optional[str] = None

class ItineraryItem(BaseModel):
    day: int
    title: str
    description: str
    location: Optional[str] = ""
    time: Optional[str] = ""

# ─── Health Check ─────────────────────────────────────────────────────────────
@app.get("/")
def read_root():
    return {
        "status": "Online ✅",
        "service": "TripSync Core Backend",
        "engine": "FastAPI 2.0 (Python)",
        "version": "2.0.0",
        "endpoints": {
            "docs": "/docs",
            "chat": "POST /api/chat",
            "safety": "GET /api/safety?city=<city>",
            "optimize": "POST /api/routes/optimize",
            "trips": "GET /api/trips",
            "split": "POST /api/expenses/split",
            "weather": "GET /api/weather?lat=<lat>&lon=<lon>",
            "itinerary": "POST /api/itinerary/generate",
        },
        "message": "Welcome to TripSync AI Core Backend API Services! 🚀"
    }

# ─── Dedicated Health Probe ────────────────────────────────────────────────────
# Always returns HTTP 200 {"status":"ok"} — safe for load balancers, k6, and
# uptime monitors. Registered BEFORE AI imports so infra probes never fail even
# when AI providers are degraded or keys are missing.
@app.get("/health")
def health_check():
    return {"status": "ok"}

from src.services.ai import ai_service
from src.services.voice import voice_service

# ─── AI Chatbot ───────────────────────────────────────────────────────────────
@app.post("/api/chat")
async def chat_helper(data: ChatMessage):
    history_list = [h.dict() for h in data.history] if data.history else []
    reply = await ai_service.generate_chat_response(data.message, history_list)
    return {"reply": reply}

# ─── AI Voice Briefing ─────────────────────────────────────────────────────────
@app.post("/api/briefing")
async def briefing_helper(data: BriefingRequest):
    briefing = await ai_service.generate_voice_briefing(data.dict())
    return {"briefing": briefing}

# ─── City Safety Score ────────────────────────────────────────────────────────
@app.get("/api/safety")
async def safety_score(city: str = Query(..., description="City name to assess")):
    result = await ai_service.get_safety_assessment(city)
    return result

# ─── Voice Assistant Speech Endpoints ─────────────────────────────────────────
@app.post("/api/voice/transcribe")
async def transcribe_voice(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1] if file.filename else ".m4a"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        shutil.copyfileobj(file.file, temp_file)
        temp_path = temp_file.name

    try:
        text = await voice_service.transcribe_audio(temp_path)
        return {"text": text}
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/voice/respond")
async def voice_respond_helper(data: VoiceRespondRequest):
    reply = await ai_service.generate_voice_response(data.query, data.context)
    return {"reply": reply}

# ─── TSP Route Optimizer ──────────────────────────────────────────────────────
@app.post("/api/routes/optimize")
async def optimize_route(spots: List[RouteSpot]):
    if len(spots) <= 2:
        return spots

    def haversine_km(s1: RouteSpot, s2: RouteSpot) -> float:
        R = 6371
        rad = math.pi / 180
        dlat = (s2.latitude - s1.latitude) * rad
        dlon = (s2.longitude - s1.longitude) * rad
        a = math.sin(dlat / 2) ** 2 + math.cos(s1.latitude * rad) * math.cos(s2.latitude * rad) * math.sin(dlon / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    unvisited = list(spots[1:])
    ordered = [spots[0]]

    while unvisited:
        last = ordered[-1]
        nearest_idx = min(range(len(unvisited)), key=lambda i: haversine_km(last, unvisited[i]))
        ordered.append(unvisited.pop(nearest_idx))

    return ordered

# ─── Trip Management Endpoints ────────────────────────────────────────────────
@app.get("/api/trips")
async def get_trips(userId: str = Query(..., description="User ID")):
    # Returns sample trips – in production this fetches from Firestore
    return {
        "trips": [
            {
                "id": "trip_001",
                "title": "Goa Beach Holiday",
                "destination": "Goa, India",
                "startDate": "2025-12-20",
                "endDate": "2025-12-27",
                "status": "upcoming",
                "coverImage": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800"
            },
            {
                "id": "trip_002",
                "title": "Manali Snow Adventure",
                "destination": "Manali, Himachal Pradesh",
                "startDate": "2026-01-10",
                "endDate": "2026-01-17",
                "status": "planning",
                "coverImage": "https://images.unsplash.com/photo-1548013146-72479768bada?w=800"
            }
        ],
        "total": 2
    }

@app.post("/api/trips")
async def create_trip(trip: TripCreate):
    return {
        "success": True,
        "tripId": f"trip_{abs(hash(trip.title + trip.userId)) % 100000:05d}",
        "message": f"Trip '{trip.title}' created successfully!",
        "trip": trip.dict()
    }

# ─── Expense Split Calculator ─────────────────────────────────────────────────
@app.post("/api/expenses/split")
async def split_expense(data: ExpenseSplit):
    if not data.members:
        return {"error": "No members provided"}

    per_person = round(data.totalAmount / len(data.members), 2)
    return {
        "totalAmount": data.totalAmount,
        "perPerson": per_person,
        "memberCount": len(data.members),
        "splits": [
            {"member": m, "amount": per_person, "paid": False}
            for m in data.members
        ],
        "description": data.description
    }

# ─── AI Itinerary Generator ───────────────────────────────────────────────────
@app.post("/api/itinerary/generate")
async def generate_itinerary(data: dict):
    result = await ai_service.generate_itinerary(data)
    return result

# ─── Weather Proxy ────────────────────────────────────────────────────────────
@app.get("/api/weather")
async def weather_proxy(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude")
):
    import httpx
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            )
            data = res.json()
            return data.get("current_weather", {})
    except Exception as e:
        return {"error": str(e), "message": "Weather service temporarily unavailable"}

# ─── OTP Email Sender ─────────────────────────────────────────────────────────
class OTPSendRequest(BaseModel):
    email: str
    otp: str

@app.post("/api/otp/send")
async def send_otp_email_endpoint(data: OTPSendRequest):
    import os
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email_to = data.email
    otp_code = data.otp

    subject = "Your TripSync OTP Verification Code 🔐"
    body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #0F172A; color: white; padding: 20px; border-radius: 12px;">
        <h2 style="color: #38BDF8;">TripSync Verification Code</h2>
        <p>Hello,</p>
        <p>Thank you for choosing TripSync. Use the following One-Time Password (OTP) to complete your verification:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 4px; color: #38BDF8; margin: 20px 0; background-color: #1E293B; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #334155;">
          {otp_code}
        </div>
        <p style="color: #94A3B8; font-size: 13px;">This code is valid for 5 minutes. If you did not request this code, please ignore this email.</p>
        <hr style="border-color: #334155;" />
        <p style="color: #475569; font-size: 11px;">TripSync AI Travel Companion</p>
      </body>
    </html>
    """

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")

    success = False
    error_msg = ""

    if smtp_user and smtp_pass:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = email_to

            # Plain text version as fallback
            plain_body = f"Hello,\n\nThank you for choosing TripSync. Use the following One-Time Password (OTP) to complete your verification:\n\n{otp_code}\n\nThis code is valid for 5 minutes. If you did not request this code, please ignore this email.\n\nTripSync AI Travel Companion"
            msg.attach(MIMEText(plain_body, "plain"))
            msg.attach(MIMEText(body, "html"))

            if smtp_port == 465:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=5)
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=5)
                server.starttls()

            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email_to, msg.as_string())
            server.quit()
            success = True
            print(f"📧 [OTP SENT] Successfully sent OTP email to {email_to}")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ [SMTP ERROR] Failed to send email to {email_to}: {e}")
    else:
        error_msg = "SMTP credentials not configured in environment variables"
        print(f"⚠️ [SMTP WARNING] SMTP credentials not set. OTP for {email_to} is: {otp_code}")

    return {
        "success": success,
        "message": "OTP email sent successfully!" if success else f"OTP logged to terminal (SMTP offline: {error_msg})",
        "otp": otp_code,
        "email": email_to
    }

# ─── Route Sharing & Analytics ────────────────────────────────────────────────
class ShareRouteMetadata(BaseModel):
    routeId: str
    routeName: str
    stopsCount: int
    totalDistance: str
    totalDuration: str

@app.post("/api/routes/share")
async def share_route_endpoint(data: ShareRouteMetadata):
    scenic_factor = round(8.0 + (data.stopsCount % 3) * 0.5, 1)
    complexity = "Easy Navigation" if data.stopsCount <= 3 else "Scenic Adventure" if data.stopsCount <= 6 else "Epic Multi-Stop Expedition"
    return {
        "success": True,
        "message": f"Route '{data.routeName}' sharing registered successfully!",
        "analytics": {
            "scenicFactor": scenic_factor,
            "complexity": complexity,
            "recommendation": f"Best time to start this {data.stopsCount}-stop journey is 8:30 AM to beat traffic indices."
        }
    }

# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

