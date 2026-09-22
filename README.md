# GraceHealth Cloud Setup

Architecture:
Phone -> HTTPS -> Render Flask API -> Neon PostgreSQL
Health_Box HB-0001 -> HTTPS -> Render Flask API

## Backend deployment

Deploy the `backend` directory as a Render Web Service.

Build:
`pip install -r requirements.txt`

Start:
`gunicorn --bind 0.0.0.0:$PORT app:app`

Environment variables:
- DATABASE_URL = Neon PostgreSQL connection string
- SECRET_KEY = long random secret
- DEVICE_KEY_HB_0001 = long random device key
- PYTHON_VERSION = 3.13.4

The API creates its tables automatically on first start.

## Frontend

After the Render API is live, set:

`VITE_API_URL=https://YOUR-RENDER-SERVICE.onrender.com/api`

Then:
`npm run build`
`npx cap sync android`
`cd android`
`.\gradlew assembleDebug`

The Android app does not require users to know any IP address or run Flask locally.

## Health_Box

The ESP8266 will POST sensor readings to:
`https://YOUR-RENDER-SERVICE.onrender.com/api/device/reading`

It must send:
`device_id`, `device_key`, `bpm`, `spo2`, `temperature`.

A reading is stored against the user who currently owns the active HB-0001 session.
