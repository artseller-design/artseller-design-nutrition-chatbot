# Data-driven nutrition assistant API

FastAPI, Firestore, and OpenAI backend for dated numeric observations, saved conversations, and meal nutrition records.

## Local setup

Use Python 3.10 or newer. From the project root in PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Configure the values in `backend/.env`:

| Variable | Required for | Value |
|---|---|---|
| `FIREBASE_KEY_PATH` | Firestore | Path to a Firebase service-account JSON file, relative to `backend` or absolute |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firestore on Render | Entire service-account JSON as a secret environment variable; use this or `FIREBASE_KEY_PATH` |
| `AI_PROVIDER` | AI chat | `openai` (default) or `gemini`; setting `GEMINI_API_KEY` defaults to Gemini |
| `OPENAI_API_KEY` | AI chat | OpenAI API key |
| `OPENAI_MODEL` | AI chat | Defaults to `gpt-4o-mini` |
| `GEMINI_API_KEY` | AI chat | Google AI Studio Gemini API key |
| `GEMINI_MODEL` | AI chat | Defaults to `gemini-3.5-flash` |
| `FOOD_API_KEY` | Food nutrition lookup | data.go.kr 식품의약품안전처_식품영양성분DB정보 API key |
| `KMA_API_KEY` | Weather sync | Korea Meteorological Administration API key |
| `KMA_APIHUB_KEY` | Changwon medium-range forecast sync | API key issued by KMA API Hub |
| `KMA_MIDTA_REGION_ID` | Changwon medium-range forecast sync | Defaults to Changwon region code `11H20301` |
| `WEATHER_CSV_URL` | Scheduled weather sync | Public or server-accessible direct CSV download URL; unset disables polling |
| `WEATHER_CSV_PATH` | Scheduled weather sync | Local CSV path for a locally running API; ignored when URL is set |
| `WEATHER_CSV_REFRESH_MINUTES` | Scheduled weather sync | Poll interval in minutes; defaults to 60, minimum 5 |
| `WEATHER_CSV_USER_ID` | Scheduled weather sync | Firestore app user ID; defaults to `APP_USER_ID` |
| `CORS_ORIGINS` | Browser access | Comma-separated exact frontend origins |

Never commit `.env` or service-account credentials. If Firebase or the selected AI provider is not configured, unrelated routes and `/docs` remain available; dependent API routes return an explicit `503`.

For Gemini, set `GEMINI_API_KEY` to the Google AI Studio key. The app uses Google's OpenAI-compatible API endpoint; it does not send a Gemini key to OpenAI. Set `AI_PROVIDER=gemini` if both provider keys are configured. `OPENAI_API_KEY` is also accepted as a migration fallback when `AI_PROVIDER=gemini`.

For a local Firebase connection, open Firebase Console → Project settings → Service accounts → Generate new private key. Save the downloaded JSON as `backend/serviceAccountKey.json` and set `FIREBASE_KEY_PATH=serviceAccountKey.json` in `backend/.env`. A Firebase Console browser login or a Firestore database by itself does not authenticate this backend. `/health` performs a real Firestore read and reports `firestore_connected`; inspect `firestore_error` and the backend log if it is false.

Start the API:

```powershell
uvicorn app.main:app --reload
```

In another terminal from the project root, serve the framework-free frontend:

```powershell
python -m http.server 5500 --directory frontend
```

Open `http://localhost:5500`; Swagger UI is at `http://127.0.0.1:8000/docs`.

To access the local app from a phone on the same Wi-Fi, bind both servers to
`0.0.0.0`, open TCP ports 5500 and 8000 only to the local subnet in Windows
Firewall, and add the PC's current frontend origin (for example,
`http://192.168.0.10:5500`) to `CORS_ORIGINS`. The frontend derives the API host
from the page's hostname. Use the PC's private Wi-Fi address on the phone; do
not expose this unauthenticated demo to the public internet. If DHCP changes the
PC's address, update `CORS_ORIGINS`, the firewall scope if necessary, and use
the new frontend URL.

## Time-series data API

All CRUD routes require `user_id` as a query parameter. A data point is a daily calorie value and memo stored in the Firestore `data` collection.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/data?user_id=demo-user` | Add `{ "date": "2026-10-19", "value": 2100, "memo": "..." }` |
| `GET` | `/api/data?user_id=demo-user&start_date=2026-07-01&end_date=2026-10-19` | List date-filtered points |
| `PUT` | `/api/data/{id}?user_id=demo-user` | Replace the date, value, and memo |
| `DELETE` | `/api/data/{id}?user_id=demo-user` | Delete a point |
| `GET` | `/api/data/summary?user_id=demo-user&start_date=2026-07-01&end_date=2026-10-19` | Count, average, median, population standard deviation, minimum, maximum, and recent trend |

Trend compares the latest seven recorded points with the preceding up-to-seven points. Fewer than four points is reported as insufficient data. The summary only uses stored records in the requested inclusive date range.

For a clearly labelled synthetic demonstration dataset (not real measurements), configure Firestore and run from `backend`:

```powershell
python -m scripts.seed_demo_data --user-id demo-user --count 120
```

The script creates 100–1000 daily synthetic calorie records. Deterministic document IDs make rerunning it update the same date range rather than create duplicate seed points.

## Conversations and data-grounded chat

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/conversations` | Save a conversation and its messages |
| `GET` | `/api/conversations?user_id=demo-user` | List conversation metadata |
| `GET` | `/api/conversations/{id}?user_id=demo-user` | Load the selected conversation and full messages |
| `DELETE` | `/api/conversations/{id}?user_id=demo-user` | Delete a conversation |
| `POST` | `/api/chat` | Ask a question using a recent-data summary; persist the user/assistant exchange |

Chat body:

```json
{
  "user_id": "demo-user",
  "conversation_id": null,
  "message": "최근 섭취 열량의 평균과 추세를 알려줘."
}
```

The chat context includes the user's last-30-day daily calorie summary and meal records, with meal-level nutrient totals and daily summaries. Nutrient totals cover every meal record in the period; individual food details are limited to the latest 100 entries to bound prompt size. For food questions, the response also appends the matching saved food records and their recorded calorie total so an AI summary cannot silently omit entries. The assistant treats meal entries and daily calorie observations as separate sources and does not add them together because they may represent the same intake. The exchange is saved to `conversations`; the frontend can load and delete it. `/api/chat` requires Firestore and a key for the selected AI provider.

## Meal and food-nutrition APIs

- `POST /users/{user_id}/food-entries/meal` — atomically save 1–50 foods as one meal.
- `POST/GET/DELETE /users/{user_id}/food-entries` — save, list, and delete individual food records.
- `DELETE /users/{user_id}/food-entries/meals/{meal_id}` — delete an entire meal and all its foods.
- `GET /api/food-nutrition?query=현미밥` — search data.go.kr's 전국통합식품영양성분정보(음식) standard-data API; the frontend scales the source reference amount to the entered amount.
- `GET /users/{user_id}/analysis/summary` — period nutrient totals and averages, counting a grouped meal once while retaining its individual food count.
- Existing weather, activity, and recommendation routes remain available under `/api`.
- `POST /api/weather/csv/recommend` — accept `{ "user_id", "target_date", "csv_text" }`, upsert daily weather observations, and save a weather-based food recommendation. CSV requires `tm` and `avgTa`; `sumRn` and `avgRhm` are optional.
- `POST /api/weather/recommend-saved` — accept `{ "user_id", "target_date" }` and recommend from observations already imported into Firestore.

Recent weather observations and saved weather-CSV recommendations are included in `/api/chat` context alongside food and calorie records. Missing dates are reported as missing observations and are not imputed as zero. Weather-based menu rules do not perform seasonal decomposition or statistical outlier detection.

In the meal form, search and select each food (for example rice, kimchi, and egg), set its serving amount, and choose **이 음식을 한 끼에 추가**. The unfinished meal is temporarily saved in the browser for the current API address and user ID, so it can be restored after a refresh. A selected food that is still in the search form is also included automatically when **한 끼 저장하기** is pressed. If a typed search has no selected result, the form asks the user to select a result or clear that search before saving. Every component is stored as an individual food record with a shared `meal_id`; nutrient totals include all components, while the journal groups them into one meal. The journal lets users delete either an individual food or the entire meal.

Unsubmitted meal components are temporarily kept in the browser for the current API URL and user ID. Searching another food or refreshing the page will not discard the items already added; they are removed from temporary storage after the meal is successfully saved.

Food lookup uses the [official 식품의약품안전처_식품영양성분DB정보 Open API](https://www.data.go.kr/data/15127578/openapi.do), at `https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03`. Apply for that API on data.go.kr and set its issued key as `FOOD_API_KEY`. The API filters with `FOOD_NM_KR`; nutrient values are mapped from fields such as `AMT_NUM1` (energy), `AMT_NUM3` (protein), `AMT_NUM4` (fat), `AMT_NUM6` (carbohydrate), `AMT_NUM7` (sugar), and `AMT_NUM13` (sodium).

Search first checks the first result page for an exact food-name match. If none is present, it also checks the last 50 records, where general food-composition entries may appear after many recipe and branded-product matches. For example, a `김치` query can include `김치, 배추 김치` and other kimchi types alongside recipe results.

Search ignores spaces and normalizes the common `시레기` misspelling to the standard `시래기` spelling, so `시레기 국` can find the official `시래기국` entry.

Food searches are cached in the running backend for five minutes (up to 256 query/limit combinations). The primary upstream request times out after seven seconds and the optional fallback page after eight seconds; if that fallback fails, the first-page matches are still returned. The frontend stops waiting after 18 seconds with an error message instead of remaining in a loading state.

Food matches are ordered with exact normalized name matches first, then names starting with the search term, followed by other containing matches. The frontend intentionally leaves the selection blank until the user chooses a result; nutrient fields are filled only after that choice.

## Tests

From the project root:

```powershell
python -m unittest discover -s backend\tests -v
node --check frontend\script.js
```

API unit tests use an in-memory Firestore substitute and do not need a Firebase project or OpenAI request.

## Deployment

### Render backend

1. Push the repository to GitHub and create a Render Web Service from the repository. `render.yaml` also defines the service.
2. Set the secret environment variables `FIREBASE_SERVICE_ACCOUNT_JSON`, `OPENAI_API_KEY`, `FOOD_API_KEY`, and `CORS_ORIGINS` in Render. `FOOD_API_KEY` is the key issued after applying for the API on data.go.kr. `FIREBASE_SERVICE_ACCOUNT_JSON` is the JSON text of the service-account file; do not upload it to GitHub.
3. Set `CORS_ORIGINS` to the exact Vercel origin, such as `https://your-project.vercel.app`.
4. Verify `https://<render-service>.onrender.com/health` and `/docs`. The free instance may sleep; its first request can be delayed.

### Vercel frontend

1. Import the same repository into Vercel and set the project Root Directory to `frontend`.
2. Set the environment variable `API_BASE_URL` to the Render backend origin, without a trailing slash.
3. Deploy. `frontend/vercel.json` builds the static HTML/CSS/JavaScript into `dist`; `build.js` embeds the configured backend URL.
4. Add the deployed Vercel origin to Render's `CORS_ORIGINS`, redeploy/restart the backend, then verify browser API access.

Production URLs are assigned by the hosting providers and are not committed into this repository. After deployment, record the actual frontend, backend, and `/docs` URLs in the project hand-in.

## Submission screenshots

Capture and add these screenshots after deploying with configured services and at least 100 explicitly labelled demo points:

- `docs/screenshots/chat.png` — a data-grounded question, answer, and loading completion
- `docs/screenshots/data-crud.png` — the data list with one visible update or delete interaction
- `docs/screenshots/conversations.png` — saved conversation list and a loaded message history

Do not present a mocked browser response as proof of a live Render, Firestore, or OpenAI integration.

## Security note

The current demo uses `user_id` from the request and does not authenticate users. Do not put personal data in a public deployment until Firebase Authentication ID tokens are verified and the token UID is used for authorization.
