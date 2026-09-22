# GraceHealth — full app foundation

This is the first complete working foundation for the GraceHealth app.

### Included
- Girlish/feminine GraceHealth visual theme
- Generated GraceHealth logo
- Login/register
- Unique Health IDs (`GH-1001`, ...)
- One shared Health_Box (`HB-0001`)
- One active user session at a time
- Explicit Connect / Disconnect
- Per-user sensor history
- Partial sensor values supported (`null` stays `—`)
- Period tracker foundation
- Wellness/PMS and medication APIs/UI
- Medical records
- Reports section
- Profile and admin contact
- React/Vite frontend
- Capacitor configuration for Android
- Flask API with password hashing and authenticated user separation

### Run backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Run frontend
```bash
cd frontend
npm install
npm run dev
```

### Android
```bash
npm install
npx cap add android
npm run build
npx cap sync android
npx cap open android
```

### ESP8266 reading protocol
POST to `/api/device/reading`:
```json
{
  "device_id":"HB-0001",
  "device_key":"DEVICE_KEY_HB_0001",
  "bpm":78,
  "spo2":98,
  "temperature":33.2
}
```
The backend attaches the reading to the currently active authenticated app session. If no user is connected, the device reading is rejected.
