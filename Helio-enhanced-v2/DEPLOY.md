# Deploy Helio on Render (one click)

1. Push this folder to GitHub (the `.env` file is intentionally NOT included).
2. Render dashboard -> **New +** -> **Blueprint** -> pick your repo -> **Apply**.
3. Wait for the build, then open the URL Render gives you.

Optional: add `GEMINI_API_KEY` in Render -> Environment. Without it, triage uses the built-in rule-based fallback.

Note: on the free plan the disk is ephemeral, so the SQLite database is re-created and re-seeded with demo data on every deploy/restart.

## Local dev
- Backend: `cd backend && pip install -r requirements.txt && python run.py`
- Frontend: `cd frontend && npm ci && npm run dev`

## Sign-in accounts (password for all: `123`)
- tharshini@gmail.com (Doctor)
- eva@gmail.com (Doctor)
- tahseen@gmail.com (Nurse)
- hawwa@gmail.com (Nurse)

On a fresh database, data is loaded from `backend/app/database/data/`:
- `patient_vitals_with_symptoms.csv` -> 500 patients
- `doctors_and_nurses.csv` -> 38 doctors and 72 nurses

If you already have a local `helio.db`, delete it once so the new columns and data are created.

## Patient accounts and nurse check-in
- Patients can register from the sign-in page (**Patient -> Create an account**) with an email or phone number, name and password. Passwords are stored hashed (PBKDF2). Existing Patient ID + name sign-in still works.
- On the Appointments page a signed-in **Nurse** sees a **Visited** button on scheduled appointments. Once an appointment time passes without a visit it is set to **Not visited** automatically (checked every minute).
- Optional env var `APPOINTMENT_GRACE_MINUTES` (default `0`) delays that automatic Not visited change for late arrivals.
- New columns (patient email/phone/password, appointment visit details) are added automatically to an existing `helio.db` on startup.

## Nurse vitals and AI-assisted diagnostic imaging
- **New patient**: name, age, gender and symptoms are required. When a **Nurse** is signed in, heart rate, SpO2 and temperature are required too. On a selected patient the nurse can use **Record / Update vitals** to change vitals and symptoms (`PATCH /api/patients/{id}/vitals`, nurse only, ranges validated, audited).
- **Diagnostics**: after a doctor's request is **Started**, a nurse uploads the scan (X-ray / CT / MRI / ultrasound as PNG, JPEG or WEBP, max 8 MB) with `POST /api/diagnostics/{id}/image` (nurse only). The **Imaging Agent** (local **SVM** models, no external API) reports **what is in the X-ray (body part), what has happened (fracture / normal) and a confidence score**, plus findings, urgency and a suggested next step. The request moves to `AWAITING_REVIEW`; the doctor sees the image and report and clicks **Review & complete** to confirm or edit the final diagnosis.
- **Train the SVM first**: `cd backend && python train_xray_svm.py --data <xray_folder>` where the folder is `<body_part>/<normal|fracture>/*.png`. This writes `backend/app/ml/xray_svm.joblib` (commit it or generate it in the build step). Held-out accuracy is stored in the model and shown on the report.
- Without a trained model file (or if the image is not an X-ray) the image is still saved and the report says **"AI reading unavailable"** / "Not an X-ray image" so a doctor reads it manually. No result is ever made up.
- Confidence is the SVM's calibrated probability (overall = body-part x fracture confidence), not a guarantee. Reports are decision support only and must be reviewed by a doctor.
- DICOM (.dcm) files are not read directly; export them as PNG/JPEG first.
- New diagnostic columns are added automatically to an existing `helio.db` on startup.

## Emergency alarm (nurse -> doctor siren)
- A signed-in **Nurse** sees a red **Emergency** button in the top bar. They pick the emergency type (road accident / major trauma, cardiac arrest, stroke / head injury, severe breathing difficulty, severe bleeding, major burns, fractures / spine injury, other), optionally add the patient description, location and notes, then press **Sound the alarm** (`POST /api/emergency/alerts`, nurse only, audited).
- Each type maps to a specialty (see `backend/app/services/emergency_service.py`). The **3 most experienced available doctors** of that specialty are paged; if none is available, the next specialty in the list is used.
- A paged **Doctor** gets a full-screen red alert with a siren (Web Audio, no audio file) on whatever page they are on. It repeats until they press **I'm responding** (`PATCH /api/emergency/alerts/{id}/acknowledge`). The doctor screen checks for alerts every 3 seconds. Browsers may keep audio silent until the page has been clicked once; the alert says so if that happens.
- The nurse sees who responded, and can cancel a false alarm.
- Only the sign-in accounts above can receive a siren (tharshini = Emergency & Urgent Care, eva = Cardiology). Other doctors in the roster are paged in the alert record but have no login to hear it.
- The `emergency_alerts` table is created automatically on startup.

## Doctor specialties
Doctor specialties now follow the hospital specialty list (e.g. Emergency & Urgent Care, Cardiology, Critical Care, Orthopaedics, Neurology & Neurosurgery, Anesthesiology, General Surgery, Plastic Surgery, Vascular Surgery, Infectious Diseases, Nephrology and Urology Science, Paediatrics and Neonatology). On startup, an existing `helio.db` is brought in line with the CSV by staff ID, so you do not need to delete it.
