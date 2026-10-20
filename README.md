# 영양 데이터 분석 및 AI 채팅

식사별 음식·영양 정보와 일일 섭취 열량 시계열을 Firestore에 저장·분석하고, 최근 30일 기록을 바탕으로 AI 채팅을 제공하는 프로젝트입니다. 프런트엔드는 순수 HTML/CSS/JavaScript입니다.

## 기능

- 데이터 관리: 날짜·값·메모 필드 추가, 목록 조회, 수정, 삭제
- 데이터 요약: 기간, 데이터 건수, 평균·최대·최소, 최근 증가·감소·유지 추세
- AI 채팅: 최근 30일 식사 기록의 음식별 영양 정보와 일일 칼로리 요약을 컨텍스트로 답변
- 대화 기록: 대화 자동 저장, 목록, 전체 메시지 불러오기, 삭제
- 식사 기록: 밥·반찬 등 여러 음식을 한 끼에 구성해 저장하고, 공공데이터포털 영양정보를 음식별 섭취량에 맞춰 합산
- FastAPI `/docs` API 문서

## 로컬 실행

Python 3.10 이상과 Node.js가 필요합니다.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

`backend/.env`에 최소한 `FIREBASE_KEY_PATH`와 사용할 AI 제공자의 키를 설정합니다. OpenAI는 `OPENAI_API_KEY`, Gemini는 `GEMINI_API_KEY`와 `AI_PROVIDER=gemini`를 사용합니다. Firebase 프로젝트 설정의 서비스 계정 메뉴에서 새 비공개 키(JSON)를 발급해 `backend/serviceAccountKey.json`으로 저장하고, `FIREBASE_KEY_PATH=serviceAccountKey.json`으로 지정합니다. Firebase 콘솔에 로그인한 것만으로 백엔드가 인증되는 것은 아닙니다. AI 키와 Firebase 서비스 계정 JSON은 코드·저장소에 넣지 마세요.

터미널 1 (프로젝트 루트에서):

```powershell
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0
```

터미널 2 (프로젝트 루트에서):

```powershell
python -m http.server 5500 --bind 0.0.0.0 --directory frontend
```

- 프런트엔드: `http://localhost:5500`
- Swagger UI: `http://127.0.0.1:8000/docs`
- 상태 확인: `http://127.0.0.1:8000/health`

같은 Wi-Fi의 휴대폰에서는 PC의 사설 IP로 접속합니다. 현재 PC 주소는 `http://172.16.110.209:5500`이며, 앱은 페이지 주소에서 API 호스트를 자동으로 설정합니다. PC의 주소가 바뀌면 `backend/.env`의 `CORS_ORIGINS`에 새 프런트엔드 주소(`http://<PC-IP>:5500`)를 반영하고 백엔드를 재시작하세요. Windows 방화벽은 TCP 5500·8000을 로컬 서브넷에 한해 허용해야 합니다. 현재 데모는 사용자 인증이 없으므로 공용 인터넷에 노출하지 마세요.

`/health`는 실제 Firestore 읽기 요청까지 확인합니다. `firestore_connected`가 `false`이면 응답의 `firestore_error`와 백엔드 시작 로그를 확인하세요. Firestore 콘솔에서 만든 컬렉션은 연결된 프로젝트 안에 그대로 존재하지만, 이 앱의 API는 시계열 값을 `data` 컬렉션에, 식사 기록을 `users/{user_id}/food_entries`에 저장합니다.

100개 이상의 데모 데이터가 필요하면 Firestore 설정 후 `backend` 폴더에서 명시적으로 실행합니다.

```powershell
python -m scripts.seed_demo_data --user-id demo-user --count 120
```

생성되는 레코드는 실제 측정값이 아닌 합성 시연 데이터임을 각 메모에 표시합니다. 대화형 화면은 사용자 ID `demo-user`를 기준으로 데이터를 조회합니다.

## 환경 변수

| 이름 | 용도 |
|---|---|
| `FIREBASE_KEY_PATH` | 로컬 Firebase 서비스 계정 JSON 경로 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | 호스팅 환경에서 사용하는 서비스 계정 JSON 문자열 |
| `AI_PROVIDER` | AI 제공자 (`openai` 또는 `gemini`) |
| `OPENAI_API_KEY` | OpenAI 채팅 키 |
| `OPENAI_MODEL` | OpenAI 모델 (기본 `gpt-4o-mini`) |
| `GEMINI_API_KEY` | Google AI Studio Gemini 키 |
| `GEMINI_MODEL` | Gemini 모델 (기본 `gemini-3.5-flash`) |
| `FOOD_API_KEY` | 공공데이터포털 식품의약품안전처 식품영양성분DB정보 API 활용 키 |
| `KMA_API_KEY` | 기상청 관측 데이터 동기화 |
| `CORS_ORIGINS` | 쉼표로 구분한 허용 프런트엔드 출처 |
| `API_BASE_URL` | Vercel 정적 프런트엔드 빌드 시 Render API URL |
| `REQUIRE_FIREBASE_AUTH` | API Firebase 로그인 필수 여부 (배포는 `true`) |
| `FIREBASE_ALLOWED_UID` | API 접근을 허용할 Firebase 사용자 UID |
| `APP_USER_ID` | 로그인 사용자에게 매핑할 Firestore 앱 사용자 ID |
| `FIREBASE_API_KEY` | Vercel 로그인 화면의 Firebase 웹 API 키 |
| `GOOGLE_OAUTH_CLIENT_ID` | Vercel Google OAuth 웹 클라이언트 ID |

## 주요 API

| 기능 | 메서드와 주소 |
|---|---|
| 데이터 추가 | `POST /api/data?user_id=demo-user` |
| 데이터 목록 | `GET /api/data?user_id=demo-user` |
| 데이터 수정 | `PUT /api/data/{id}?user_id=demo-user` |
| 데이터 삭제 | `DELETE /api/data/{id}?user_id=demo-user` |
| 기간 요약 | `GET /api/data/summary?user_id=demo-user&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` |
| 대화 저장 | `POST /api/conversations` |
| 대화 목록 | `GET /api/conversations?user_id=demo-user` |
| 대화 메시지 불러오기 | `GET /api/conversations/{id}?user_id=demo-user` |
| 대화 삭제 | `DELETE /api/conversations/{id}?user_id=demo-user` |
| 요약 기반 AI 질문 | `POST /api/chat` |

`/api/chat`은 최근 30일 식사 기록(음식별 영양 정보와 날짜별 합계) 및 일일 칼로리 데이터 요약을 선택한 AI 제공자(OpenAI 또는 Gemini)에 전달하며 질문·답변을 Firestore `conversations` 컬렉션에 자동 저장합니다. 두 기록은 같은 섭취를 나타낼 수 있으므로 AI가 서로 합산하지 않도록 구분합니다. 대화 컨텍스트의 음식별 상세 목록은 최근 100건까지 포함하고, 영양 합계는 해당 기간 기록 전체를 기준으로 계산합니다. 전체 API와 요청 스키마는 `/docs`에서 확인할 수 있습니다.

음식 영양정보 자동 조회는 [식품의약품안전처_식품영양성분DB정보 Open API](https://www.data.go.kr/data/15127578/openapi.do)를 사용합니다. 공공데이터포털에서 해당 API 활용 신청 후 발급한 인증 키를 `FOOD_API_KEY`에 설정해야 합니다. 이 프로젝트는 `https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03`에 `FOOD_NM_KR` 검색어를 전달하고, API의 영양성분 기준량에 맞춰 사용자의 섭취량을 환산합니다. 검색 결과는 음식명 완전 일치 항목을 우선 정렬하고, 영양값은 사용자가 목록에서 결과를 직접 선택한 뒤 채웁니다.

## 검증

프로젝트 루트에서 PowerShell로:

```powershell
Set-Location backend
python -m unittest discover -s tests -v
node --check ..\frontend\script.js
```

기본 단위 테스트는 Firebase/OpenAI 계정 없이 실행되도록 Firestore를 대체합니다. 실제 외부 연동은 유효한 Firebase 및 OpenAI 키를 설정해야 검증할 수 있습니다.

## 배포

- **Google 로그인 설정**: Firebase 콘솔 Authentication에서 Google 제공자를 활성화합니다. Google Cloud에서 웹 OAuth 클라이언트를 만들고, OAuth 동의 화면에 배포 도메인을 승인된 JavaScript 원본으로 추가합니다. Firebase Authentication의 승인된 도메인에도 같은 도메인을 등록합니다.
- **Backend / Render**: 저장소의 `render.yaml`을 사용합니다. Render 환경 변수에 `FIREBASE_SERVICE_ACCOUNT_JSON`, 선택한 AI 제공자의 키(`OPENAI_API_KEY` 또는 `GEMINI_API_KEY`), `FOOD_API_KEY`, `CORS_ORIGINS`를 등록합니다. 최초 배포에서는 `FIREBASE_ALLOWED_UID`에 임시 문자열(예: `pending-user`)을 설정해 두고, `REQUIRE_FIREBASE_AUTH=true`와 `APP_USER_ID=demo-user`를 유지합니다. Gemini를 사용할 때는 `AI_PROVIDER=gemini`로 설정합니다. `/health`는 공개 상태 확인용이며 데이터 API는 Firebase 로그인을 요구합니다.
- **Frontend / Vercel**: Vercel 프로젝트의 Root Directory를 `frontend`로 설정합니다. 환경 변수 `API_BASE_URL`에 Render의 HTTPS URL을, `FIREBASE_API_KEY`에 Firebase 프로젝트의 웹 API 키를, `GOOGLE_OAUTH_CLIENT_ID`에 Google Cloud의 웹 OAuth 클라이언트 ID를 등록한 뒤 배포합니다. Render `CORS_ORIGINS`를 실제 Vercel 출처로 바꾸고 백엔드를 다시 배포합니다. 빌드 결과에는 공개 Firebase 웹 설정값만 포함됩니다.
- **허용 계정 등록**: 배포된 화면에서 Google 로그인을 한 번 시도합니다. 첫 로그인으로 Firebase 사용자가 생성되며 임시 UID가 설정된 동안 앱 화면 진입은 거부됩니다. Firebase Authentication 사용자 목록에서 해당 사용자의 UID를 확인해 Render `FIREBASE_ALLOWED_UID`에 넣고 백엔드를 다시 배포하면 로그인할 수 있습니다. 앱은 해당 UID 하나만 허용합니다. Firebase 서비스 계정 JSON은 비밀값이므로 채팅이나 저장소에 올리지 마세요.
- 실제 배포 URL은 각 계정에서 생성해야 하므로 이 저장소만으로 배포가 완료되는 것은 아닙니다. 배포 후 이 문서에 프런트엔드·백엔드·Swagger URL과 제출 스크린샷을 추가하세요.

제출 스크린샷은 실제 배포 후 다음 화면을 `docs/screenshots/`에 저장합니다: 채팅 질문·답변, 데이터 CRUD 동작, 대화 불러오기. 외부 서비스가 설정되지 않은 모의 화면을 실제 연동 증거로 사용하지 마세요.

## 주의

배포 API는 Google 계정으로 발급한 Firebase Authentication ID 토큰을 검증하고 `FIREBASE_ALLOWED_UID` 한 계정만 허용합니다. 해당 계정의 앱 데이터는 `APP_USER_ID` 범위로 제한됩니다. Firebase 웹 API 키와 Google OAuth 클라이언트 ID는 브라우저에 포함되는 공개 설정값이며, 서비스 계정 JSON은 비밀값으로 공개 저장소에 커밋하지 마세요. 무료 Render 인스턴스는 비활성 후 첫 요청이 지연될 수 있습니다.
