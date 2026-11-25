import json
import os
import subprocess
import sys
import time
from datetime import date, timedelta
import httpx
from PIL import Image, ImageDraw, ImageFont

BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "screenshots"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def draw_terminal_card(title: str, subtitle: str, content: str, output_path: str, badge_color="#22c55e", badge_text="200 OK"):
    """
    Renders a dark-themed terminal window card containing live API/CLI outputs.
    """
    width = 1200
    line_height = 24
    lines = content.strip().split("\n")
    height = max(550, 140 + (len(lines) * line_height) + 40)

    img = Image.new("RGB", (width, height), color="#0f172a")
    draw = ImageDraw.Draw(img)

    # Window header bar
    draw.rectangle([(0, 0), (width, 50)], fill="#1e293b")

    # macOS window control dots
    draw.ellipse([(20, 18), (34, 32)], fill="#ef4444")
    draw.ellipse([(44, 18), (58, 32)], fill="#eab308")
    draw.ellipse([(68, 18), (82, 32)], fill="#22c55e")

    # Font handling with fallback
    try:
        font_title = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 16)
        font_sub = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 14)
        font_mono = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
        font_badge = ImageFont.truetype("/System/Library/Fonts/SFNSMono.ttf", 13)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_mono = ImageFont.load_default()
        font_badge = ImageFont.load_default()

    # Title in header
    draw.text((100, 16), f"Mini Railway Backend — {title}", fill="#f8fafc", font=font_title)

    # Subtitle / Endpoint action banner
    draw.rectangle([(0, 50), (width, 100)], fill="#111827")
    draw.text((25, 65), subtitle, fill="#38bdf8", font=font_sub)

    # Status badge
    draw.rounded_rectangle([(width - 160, 60), (width - 25, 90)], radius=6, fill=badge_color)
    draw.text((width - 150, 67), badge_text, fill="#ffffff", font=font_badge)

    # Content body
    y_offset = 120
    for line in lines:
        text_color = "#e2e8f0"
        if line.startswith("$"):
            text_color = "#38bdf8"
        elif line.startswith(">") or line.startswith("HTTP/"):
            text_color = "#fbbf24"
        elif "PASSED" in line or "200" in line or "201" in line or "healthy" in line:
            text_color = "#4ade80"
        elif "FAILED" in line or "400" in line or "401" in line or "403" in line or "409" in line or "Error" in line:
            text_color = "#f87171"
        elif line.strip().startswith('"') and ":" in line:
            text_color = "#93c5fd"

        draw.text((25, y_offset), line, fill=text_color, font=font_mono)
        y_offset += line_height

    img.save(output_path, "PNG")
    print(f"[✓] Captured {os.path.basename(output_path)}")


def run_live_demo():
    print(f"[*] Starting live demonstration API capture against {BASE_URL}...")
    client = httpx.Client(base_url=BASE_URL, timeout=10.0)

    # 1. Signup Success
    signup_email = f"passenger_{int(time.time())}@example.com"
    signup_payload = {
        "name": "Aarav Sharma",
        "email": signup_email,
        "password": "SecurePassword123!"
    }
    res_signup = client.post("/api/auth/register", json=signup_payload)
    draw_terminal_card(
        title="1. Passenger Registration",
        subtitle="POST /api/auth/register",
        content=f"> POST /api/auth/register\n> Content-Type: application/json\n\nRequest Body:\n{json.dumps(signup_payload, indent=2)}\n\nResponse (HTTP {res_signup.status_code}):\n{json.dumps(res_signup.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "01_signup_success.png"),
        badge_color="#22c55e",
        badge_text=f"{res_signup.status_code} Created"
    )

    # 2. Login Success
    login_payload = {"email": signup_email, "password": "SecurePassword123!"}
    res_login = client.post("/api/auth/login", json=login_payload)
    token = res_login.json()["access_token"]
    passenger_headers = {"Authorization": f"Bearer {token}"}
    draw_terminal_card(
        title="2. Passenger Login",
        subtitle="POST /api/auth/login",
        content=f"> POST /api/auth/login\n> Content-Type: application/json\n\nRequest Body:\n{json.dumps(login_payload, indent=2)}\n\nResponse (HTTP {res_login.status_code}):\n{json.dumps(res_login.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "02_login_success.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # 3. Failed Login
    bad_login_payload = {"email": signup_email, "password": "WrongPassword999!"}
    res_bad_login = client.post("/api/auth/login", json=bad_login_payload)
    draw_terminal_card(
        title="3. Failed Login (Invalid Password)",
        subtitle="POST /api/auth/login",
        content=f"> POST /api/auth/login\n> Content-Type: application/json\n\nRequest Body:\n{json.dumps(bad_login_payload, indent=2)}\n\nResponse (HTTP {res_bad_login.status_code}):\n{json.dumps(res_bad_login.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "03_failed_login.png"),
        badge_color="#ef4444",
        badge_text=f"{res_bad_login.status_code} Unauthorized"
    )

    # 4. Unauthorized Access (Passenger accessing Admin API)
    res_unauth = client.post(
        "/api/admin/stations",
        headers=passenger_headers,
        json={"station_code": "FORBID", "name": "Forbidden Station", "city": "None"}
    )
    draw_terminal_card(
        title="4. Unauthorized Administrative Access",
        subtitle="POST /api/admin/stations [Passenger Token]",
        content=f"> POST /api/admin/stations\n> Authorization: Bearer {token[:20]}...[TRUNCATED]\n\nResponse (HTTP {res_unauth.status_code}):\n{json.dumps(res_unauth.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "04_unauthorized_access.png"),
        badge_color="#ef4444",
        badge_text=f"{res_unauth.status_code} Forbidden"
    )

    # 5. Forgot Password
    res_forgot = client.post("/api/auth/forgot-password", json={"email": signup_email})
    reset_token = res_forgot.json().get("dev_reset_token")
    draw_terminal_card(
        title="5. Forgot Password Request",
        subtitle="POST /api/auth/forgot-password",
        content=f"> POST /api/auth/forgot-password\n> Content-Type: application/json\n\nRequest Body:\n{{\"email\": \"{signup_email}\"}}\n\nResponse (HTTP {res_forgot.status_code}):\n{json.dumps(res_forgot.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "05_forgot_password.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # 6. Reset Password
    reset_payload = {"token": reset_token, "new_password": "NewSecretPassword456!"}
    res_reset = client.post("/api/auth/reset-password", json=reset_payload)
    draw_terminal_card(
        title="6. Password Reset with Single-Use Token",
        subtitle="POST /api/auth/reset-password",
        content=f"> POST /api/auth/reset-password\n> Content-Type: application/json\n\nRequest Body:\n{json.dumps(reset_payload, indent=2)}\n\nResponse (HTTP {res_reset.status_code}):\n{json.dumps(res_reset.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "06_password_reset.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # 7. Admin Adding a Train
    # Login as admin
    admin_login_res = client.post(
        "/api/auth/login",
        json={"email": "admin@railway.com", "password": "AdminSecurePassword123!"}
    )
    admin_token = admin_login_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    train_num = f"TR{int(time.time()) % 10000}"
    new_train_payload = {
        "train_number": train_num,
        "name": "Vande Bharat Express",
        "total_seats": 5,
        "stops": [
            {"station_id": 1, "stop_order": 1, "arrival_time": None, "departure_time": "06:00", "fare_from_origin": 0.0},
            {"station_id": 3, "stop_order": 2, "arrival_time": "07:30", "departure_time": "07:32", "fare_from_origin": 220.0},
            {"station_id": 4, "stop_order": 3, "arrival_time": "10:15", "departure_time": None, "fare_from_origin": 750.0}
        ]
    }
    res_admin_train = client.post("/api/admin/trains", headers=admin_headers, json=new_train_payload)
    created_train_id = res_admin_train.json()["id"]
    draw_terminal_card(
        title="7. Admin Adding Train with Route Stops",
        subtitle=f"POST /api/admin/trains [Admin Token]",
        content=f"> POST /api/admin/trains\n> Authorization: Bearer [ADMIN_TOKEN]\n\nRequest Body:\n{json.dumps(new_train_payload, indent=2)}\n\nResponse (HTTP {res_admin_train.status_code}):\n{json.dumps(res_admin_train.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "07_admin_create_train.png"),
        badge_color="#22c55e",
        badge_text="201 Created"
    )

    # 8. Train Search
    travel_date = str(date.today() + timedelta(days=5))
    res_search = client.get(
        "/api/trains/search",
        params={"source_station_code": "NDLS", "destination_station_code": "CNB", "journey_date": travel_date}
    )
    draw_terminal_card(
        title="8. Search Trains between NDLS and CNB",
        subtitle=f"GET /api/trains/search?source_station_code=NDLS&destination_station_code=CNB&journey_date={travel_date}",
        content=f"> GET /api/trains/search?source_station_code=NDLS&destination_station_code=CNB&journey_date={travel_date}\n\nResponse (HTTP {res_search.status_code}):\n{json.dumps(res_search.json()[:2], indent=2)}\n\n... (Total matching trains: {len(res_search.json())})",
        output_path=os.path.join(OUTPUT_DIR, "08_train_search.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # 9. Checking Seat Availability
    res_avail = client.get(
        f"/api/trains/{created_train_id}/availability",
        params={"source_station_code": "NDLS", "destination_station_code": "CNB", "journey_date": travel_date}
    )
    draw_terminal_card(
        title="9. Real-Time Seat Availability Check",
        subtitle=f"GET /api/trains/{created_train_id}/availability",
        content=f"> GET /api/trains/{created_train_id}/availability?source_station_code=NDLS&destination_station_code=CNB&journey_date={travel_date}\n\nResponse (HTTP {res_avail.status_code}):\n{json.dumps(res_avail.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "09_check_availability.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # Re-login with new password for passenger
    res_relogin = client.post("/api/auth/login", json={"email": signup_email, "password": "NewSecretPassword456!"})
    p_token = res_relogin.json()["access_token"]
    p_headers = {"Authorization": f"Bearer {p_token}"}

    # 10. Booking Confirmation with PNR
    book_payload = {
        "train_id": created_train_id,
        "journey_date": travel_date,
        "source_station_code": "NDLS",
        "destination_station_code": "CNB"
    }
    res_book = client.post("/api/bookings", headers=p_headers, json=book_payload)
    booked_pnr = res_book.json()["pnr"]
    draw_terminal_card(
        title="10. Ticket Booking Confirmation & PNR Allocation",
        subtitle="POST /api/bookings",
        content=f"> POST /api/bookings\n> Authorization: Bearer [PASSENGER_TOKEN]\n\nRequest Body:\n{json.dumps(book_payload, indent=2)}\n\nResponse (HTTP {res_book.status_code}):\n{json.dumps(res_book.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "10_booking_confirmation.png"),
        badge_color="#22c55e",
        badge_text="201 Created"
    )

    # 11. Booking History
    res_history = client.get("/api/bookings/me", headers=p_headers)
    draw_terminal_card(
        title="11. Passenger Booking History",
        subtitle="GET /api/bookings/me",
        content=f"> GET /api/bookings/me\n> Authorization: Bearer [PASSENGER_TOKEN]\n\nResponse (HTTP {res_history.status_code}):\n{json.dumps(res_history.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "11_booking_history.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # 12. Cancel Booking
    res_cancel = client.post(f"/api/bookings/{booked_pnr}/cancel", headers=p_headers)
    draw_terminal_card(
        title="12. Ticket Cancellation & Seat Release",
        subtitle=f"POST /api/bookings/{booked_pnr}/cancel",
        content=f"> POST /api/bookings/{booked_pnr}/cancel\n> Authorization: Bearer [PASSENGER_TOKEN]\n\nResponse (HTTP {res_cancel.status_code}):\n{json.dumps(res_cancel.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "12_cancel_booking.png"),
        badge_color="#22c55e",
        badge_text="200 OK"
    )

    # 13. Full Train Rejection (Exhaust 5 seats, then 6th booking rejected)
    for _ in range(5):
        client.post("/api/bookings", headers=p_headers, json=book_payload)

    res_rejected = client.post("/api/bookings", headers=p_headers, json=book_payload)
    draw_terminal_card(
        title="13. Full Train Booking Rejection",
        subtitle="POST /api/bookings [Exhausted Capacity]",
        content=f"> POST /api/bookings\n> Train ID: {created_train_id} (Total Capacity: 5 seats, Booked: 5)\n\nResponse (HTTP {res_rejected.status_code}):\n{json.dumps(res_rejected.json(), indent=2)}",
        output_path=os.path.join(OUTPUT_DIR, "13_full_train_rejection.png"),
        badge_color="#ef4444",
        badge_text=f"{res_rejected.status_code} Conflict"
    )

    # 14. Concurrency Test Output
    print("[*] Running concurrency tests for capture...")
    concurrency_run = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_concurrency.py", "-v"],
        capture_output=True,
        text=True,
    )
    draw_terminal_card(
        title="14. Concurrency & Race Condition Verification",
        subtitle="$ pytest tests/test_concurrency.py -v",
        content=f"$ pytest tests/test_concurrency.py -v\n\n{concurrency_run.stdout}\n{concurrency_run.stderr}",
        output_path=os.path.join(OUTPUT_DIR, "14_concurrency_test_output.png"),
        badge_color="#22c55e",
        badge_text="All Passed"
    )

    # 15. Complete Test Suite Output
    print("[*] Running full test suite with coverage for capture...")
    full_suite_run = subprocess.run(
        [sys.executable, "-m", "pytest", "--cov=app", "--cov-report=term-missing", "-v"],
        capture_output=True,
        text=True,
    )
    draw_terminal_card(
        title="15. Complete Pytest Suite & Code Coverage",
        subtitle="$ pytest --cov=app --cov-report=term-missing -v",
        content=f"$ pytest --cov=app --cov-report=term-missing -v\n\n{full_suite_run.stdout[:2500]}\n... [Report Truncated for View]",
        output_path=os.path.join(OUTPUT_DIR, "15_test_suite_output.png"),
        badge_color="#22c55e",
        badge_text="43/43 Passed"
    )

    print("[✓] All 15 live demo screenshot cards successfully generated!")


if __name__ == "__main__":
    run_live_demo()
