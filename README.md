# 영양 데이터 분석 및 AI 채팅

식사별 음식·영양 정보와 일일 섭취 열량 시계열을 Firestore에 저장·분석하고, 최근 30일 기록을 바탕으로 AI 채팅을 제공하는 프로젝트입니다. 프런트엔드는 순수 HTML/CSS/JavaScript입니다.

## 기능

- 데이터 관리: 날짜·값·메모 필드 추가, 목록 조회, 수정, 삭제
- 데이터 요약: 기간, 데이터 건수, 평균·중앙값·표준편차·최대·최소, 최근 증가·감소·유지 추세
- AI 채팅: 최근 30일 식사 기록의 음식별 영양 정보와 일일 칼로리 요약을 컨텍스트로 답변
- 대화 기록: 대화 자동 저장, 목록, 전체 메시지 불러오기, 삭제
- 식사 기록: 밥·반찬 등 여러 음식을 한 끼에 구성해 저장하고, 공공데이터포털 영양정보를 음식별 섭취량에 맞춰 합산
- 날씨 기반 추천: 창원 ASOS 일자료 CSV를 올려 날짜별 관측을 정규화하고, 선택 날짜의 기온·강수와 최근 7일 자료 품질을 반영해 음식 후보를 제안
- FastAPI `/docs` API 문서

## 구조와 설계

1. **시계열 분석**: `/api/data/summary` 라우터는 Firestore 클라이언트와 기간 조건을 `services/time_series.py`에 전달합니다. 서비스가 데이터 조회, 기간 필터, 건수·평균·중앙값·모집단 표준편차·최대·최소, 최근 최대 7개와 이전 구간의 평균 비교를 수행합니다. 식사 영양 요약은 `/users/{user_id}/analysis/summary`가 별도로 계산해 시계열 칼로리와 실제 식사 영양을 혼합하지 않습니다.
2. **라우터와 서비스**: `app/main.py`가 도메인별 라우터를 등록하고, 라우터가 HTTP 입력·응답과 상태 코드를 담당합니다. 시계열 계산·CRUD, 대화 저장, 음식 검색 및 추천 계산은 `app/services/`의 재사용 로직에 위임합니다.
3. **요청 검증**: `app/models.py`의 Pydantic 모델이 날짜·타입·필수값을 검증합니다. 시계열 값은 유한한 0 이상의 숫자이며 메모는 최대 2,000자입니다. 식사량은 양수, 영양값은 유한한 0 이상이어야 합니다. 검증 실패는 FastAPI의 422 응답으로 반환됩니다.
4. **Firestore CRUD**: 시계열 데이터는 `data` 컬렉션에 `user_id`를 포함해 저장합니다. 추가·기간 조회·수정·삭제를 제공하고, 수정·삭제 때 문서 소유자를 확인합니다. 식사 및 분석 자료는 `users/{user_id}` 아래에 저장해 사용자별 경계를 유지합니다.
5. **AI 컨텍스트**: `/api/chat`은 최근 30일 UTC 범위의 열량·식사 요약, 날씨 관측 시계열과 저장된 날씨 추천을 JSON으로 전달합니다. 날씨 결측을 0으로 간주하지 않도록 지시하고, 음식별 상세는 최대 100건으로 제한합니다. 기록 내용은 신뢰할 수 없는 데이터로 명시하며, 이전 대화는 최근 20개 메시지만 사용합니다.
6. **배포 설정과 비밀값**: `CORS_ORIGINS`에는 프런트엔드의 정확한 출처만 쉼표로 지정합니다. 로컬 값은 `backend/.env`에 두며 Git에서 제외합니다. Render의 API 키와 Firebase 서비스 계정 값은 대시보드의 비공개 환경 변수로 설정하고, 배포에서는 Firebase 인증 및 허용 UID 검사를 활성화합니다.

날씨 기반 음식 추천은 **날씨 조건을 이용한 규칙 기반 메뉴 후보 제안**입니다. 데이터 관리·분석의 열량 시계열과는 별도이며, 창원 ASOS 일자료 CSV의 `tm`, `avgTa` 열이 필수이고 `sumRn`, `avgRhm`은 선택입니다. 같은 날짜의 중복 행은 기온·습도 평균과 강수량 최댓값으로 합치며, 저장은 날짜별 upsert 방식입니다. 결과에는 최근 7일 결측일 및 당일 중복 행 수를 함께 표시합니다. 현재 추천 규칙은 계절성 검정이나 통계적 이상치 탐지를 수행하지 않으므로, 이 기능만으로 앞서 언급한 시계열 분석 목표 전체가 충족되지는 않습니다.

## 로컬 실행

Python 3.10 이상과 Node.js가 필요합니다.

프로젝트 루트에서 `.\start-local.ps1`을 실행하면 프런트엔드와 백엔드를 별도 창 없이 시작합니다. 브라우저에서 `http://localhost:5500/`을 엽니다. 실행 정책 때문에 스크립트 실행이 막히면 아래의 두 터미널 명령으로 각각 실행하세요.

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

터미널 2 (**프로젝트 루트에서**, `frontend` 폴더가 아니라 `E:\ai-chatbot-project` 위치에서):

```powershell
python -m http.server 5500 --bind 0.0.0.0 --directory frontend
```

- 프런트엔드: `http://localhost:5500`
- Swagger UI: `http://127.0.0.1:8000/docs`
- 상태 확인: `http://127.0.0.1:8000/health`

브라우저에 `localhost:5500`의 404가 나오면 기존 서버가 다른 폴더를 웹 루트로 제공하는지 확인하세요. 실행 중인 서버를 종료한 뒤, 프로젝트 루트에서 위 `python -m http.server ... --directory frontend` 명령을 다시 실행합니다. 주소 끝에 `/`를 붙여 `http://localhost:5500/`로 접속하세요. Live Server 확장을 쓴다면 `frontend/index.html`을 열어 **Open with Live Server**를 실행하세요.

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
| `KMA_API_KEY` | 공공데이터포털 기상청 ASOS 일자료 관측 API 키. 설정하면 창원(155) 최근 7일 관측을 자동 수집 |
| `KMA_APIHUB_KEY` | 창원 중기기온예보 API 자동 수집 (기상청 API허브에서 별도 발급) |
| `KMA_MIDTA_REGION_ID` | 중기기온예보 지역 코드 (창원 기본값 `11H20301`) |
| `WEATHER_CSV_URL` | 주기적으로 가져올 직접 CSV 다운로드 주소 (미설정 시 자동 수집 안 함) |
| `WEATHER_CSV_PATH` | 로컬 실행 시 계속 읽을 CSV 파일 경로 (URL이 없을 때 사용, 예: `E:\\data\\changwon.csv`) |
| `WEATHER_CSV_REFRESH_MINUTES` | 자동 수집 주기(분, 기본 60) |
| `WEATHER_CSV_USER_ID` | CSV 자동 수집 자료를 저장할 앱 사용자 ID (기본 `APP_USER_ID`) |
| `CORS_ORIGINS` | 쉼표로 구분한 허용 프런트엔드 출처 |
| `API_BASE_URL` | Vercel 정적 프런트엔드 빌드 시 Render API URL |
| `REQUIRE_FIREBASE_AUTH` | API Firebase 로그인 필수 여부 (배포는 `true`) |
| `FIREBASE_ALLOWED_UID` | API 접근을 허용할 Firebase 사용자 UID |
| `APP_USER_ID` | 로그인 사용자에게 매핑할 Firestore 앱 사용자 ID |

CSV 업로드 없이 관측을 자동으로 받으려면 [공공데이터포털 기상청 종관기상관측(ASOS) 조회서비스](https://www.data.go.kr/data/15059093/openapi.do)에서 로그인 후 활용신청을 하고 인증키를 발급받으세요. 발급한 서비스키를 `backend/.env`의 `KMA_API_KEY`에 넣고 백엔드를 재시작하면 창원 관측소 155의 최근 7일 자료를 기본 60분 간격으로 조회해 Firestore에 저장합니다. 날짜별 추천은 저장된 날씨를 사용합니다. `.env`에 키를 넣고도 `/health`의 `weather_csv_sync_enabled`가 `false`라면 백엔드 재시작 여부를 확인하세요.

기상청 API허브 키는 [회원가입](https://apihub.kma.go.kr/join.do) 및 마이페이지에서 발급받아 `KMA_APIHUB_KEY`에 넣을 수 있습니다. 이 키는 기존 중기기온예보 연동용이며, API허브의 가입·키 발급 절차가 필요합니다. `KMA_API_KEY`와는 별개의 키입니다. 중기예보는 발표 시점 기준 4~10일 뒤의 전망이므로 과거 관측이나 오늘의 실황을 대신하지 않습니다.

`WEATHER_CSV_URL`에는 로그인 없이 백엔드가 접근할 수 있는 직접 CSV 다운로드 주소를 설정합니다. 기상자료개방포털의 조회/다운로드 화면 URL은 CSV 파일 주소가 아니므로 자동 CSV 주소로 사용할 수 없습니다. 고정된 공개 CSV 주소가 없다면 ASOS API 키 연동을 사용하세요. 로컬에서는 `WEATHER_CSV_PATH`로 USB 파일도 읽을 수 있습니다. `/health`의 `weather_csv_sync_enabled`로 자동 수집 설정 여부를 확인할 수 있습니다.

계절성·결측·이상치 분석용 실제 관측 CSV는 [기상청 ASOS 일자료 조회 화면](https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36)에서 지점 **창원(155)**, 자료 형태 **일자료**, 원하는 요소와 기간을 선택해 내려받으세요. 장기간 자료는 [ASOS 파일셋 화면](https://data.kma.go.kr/data/grnd/selectAsosList.do?pgmNo=36&tabNo=1)에서 연도별 CSV 파일셋을 선택할 수 있습니다. 포털은 일자료를 한 번에 최대 10년까지 조회할 수 있다고 안내하므로, 그보다 긴 기간은 파일셋을 이용하세요.
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
