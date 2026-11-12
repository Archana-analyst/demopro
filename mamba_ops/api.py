"""Small API for the WordPress website (live availability + online booking).
It calls the SAME services as the staff app, so a web booking appears at the
front desk instantly. Run:  uvicorn api:app --port 8000
Secure it in production: HTTPS, API key, CORS limited to mambapointhotel.com, rate limiting.
"""
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date
import db, services as svc

db.init_db()
app = FastAPI(title="Mamba Point Hotel Booking API")
app.add_middleware(CORSMiddleware, allow_origins=["https://mambapointhotel.com"], allow_methods=["GET", "POST"], allow_headers=["*"])
API_KEY = "change-me"   # move to an environment variable


@app.get("/availability")
def availability(property_id: int, check_in: date, check_out: date):
    if check_out <= check_in:
        raise HTTPException(400, "check_out must be after check_in")
    rooms = svc.available_rooms(property_id, check_in, check_out)
    n = svc.nights(check_in, check_out)
    return [{"room_id": r["id"], "type": r["type"], "rate": r["rate"], "total": r["rate"] * n} for r in rooms]


class Booking(BaseModel):
    property_id: int
    room_id: int
    check_in: date
    check_out: date
    name: str
    phone: str = ""
    email: str = ""


@app.post("/book")
def book(b: Booking, x_api_key: str = Header(default="")):
    if x_api_key != API_KEY:
        raise HTTPException(401, "Invalid API key")
    try:
        rid = svc.create_reservation(b.property_id, b.name, b.phone, b.email, b.check_in, b.check_out, b.room_id, source="website")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"reservation_id": rid, "status": "booked"}
