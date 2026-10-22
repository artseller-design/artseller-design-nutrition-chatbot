const apiBaseInput = document.getElementById("api-base");
if (window.APP_CONFIG?.apiBaseUrl) {
  apiBaseInput.value = window.APP_CONFIG.apiBaseUrl;
} else if (window.location.hostname) {
  apiBaseInput.value = `http://${window.location.hostname}:8000`;
}
const authEnabled = Boolean(window.APP_CONFIG?.authEnabled);
const firebaseApiKey = window.APP_CONFIG?.firebaseApiKey || "";
const googleOAuthClientId = window.APP_CONFIG?.googleOAuthClientId || "";
const appUserId = window.APP_CONFIG?.userId || "demo-user";
const authSessionStorageKey = "nutrition-chat-firebase-session";
let authSession = null;
let appInitialized = false;
let googleIdentityPromise = null;
const userIdInput = document.getElementById("user-id");
const entryForm = document.getElementById("entry-form");
const entriesList = document.getElementById("entries-list");
const summaryContent = document.getElementById("summary-content");
const formMessage = document.getElementById("form-message");
const summaryMessage = document.getElementById("summary-message");
const lookupMessage = document.getElementById("lookup-message");
const connectionStatus = document.getElementById("connection-status");
const connectionDot = document.getElementById("connection-dot");
const foodNameInput = document.getElementById("food-name");
const amountInput = document.getElementById("amount");
const unitInput = document.getElementById("unit");
const foodMatchField = document.getElementById("food-match-field");
const foodMatchInput = document.getElementById("food-match");
const addFoodButton = document.getElementById("add-food-button");
const nutrientLabels = {
  calories_kcal: "열량",
  protein_g: "단백질",
  carbohydrate_g: "탄수화물",
  fat_g: "지방",
  sugar_g: "당류",
  sodium_mg: "나트륨",
};
let foodMatches = [];
let selectedFood = null;
let selectedNutrients = null;
let mealFoods = [];
let lookupTimer = null;
let lookupSequence = 0;
let editingDataId = null;
let activeConversationId = null;
let activeMessages = [];

function pendingMealStorageKey() {
  return `pending-meal:${apiBaseInput.value.trim()}:${userIdInput.value.trim()}`;
}

function persistPendingMeal() {
  try {
    const key = pendingMealStorageKey();
    if (mealFoods.length) {
      window.localStorage.setItem(key, JSON.stringify(mealFoods));
    } else {
      window.localStorage.removeItem(key);
    }
    return true;
  } catch (error) {
    setMessage(
      formMessage,
      `현재 한 끼 구성은 화면에 남아 있지만 브라우저에 임시 저장하지 못했습니다: ${error.message}`,
      true,
    );
    return false;
  }
}

function restorePendingMeal() {
  try {
    const saved = window.localStorage.getItem(pendingMealStorageKey());
    if (!saved) {
      mealFoods = [];
      renderMealFoods();
      return;
    }
    const restored = JSON.parse(saved);
    if (
      !Array.isArray(restored)
      || restored.length > 50
      || restored.some((food) => (
        !food
        || typeof food.food_name !== "string"
        || typeof food.amount !== "number"
        || !Number.isFinite(food.amount)
        || food.amount <= 0
        || typeof food.unit !== "string"
        || !food.nutrients
        || typeof food.nutrients !== "object"
      ))
    ) {
      throw new SyntaxError("저장된 한 끼 구성의 형식이 올바르지 않습니다.");
    }
    mealFoods = restored;
    renderMealFoods();
    if (mealFoods.length) {
      setMessage(formMessage, `작성 중이던 한 끼 구성 ${mealFoods.length}개 음식을 복원했습니다.`);
    }
  } catch (error) {
    if (error instanceof SyntaxError) {
      try {
        window.localStorage.removeItem(pendingMealStorageKey());
      } catch (storageError) {
        setMessage(formMessage, `잘못된 임시 구성 데이터를 지우지 못했습니다: ${storageError.message}`, true);
        return;
      }
      mealFoods = [];
      renderMealFoods();
      setMessage(formMessage, error.message, true);
      return;
    }
    setMessage(formMessage, `작성 중인 한 끼 구성을 복원하지 못했습니다: ${error.message}`, true);
  }
}

function apiUrl(path) {
  const base = apiBaseInput.value.trim().replace(/\/+$/, "");
  if (!base) throw new Error("API 주소를 입력해 주세요.");
  return `${base}${path}`;
}

function currentUserId() {
  const userId = (authEnabled ? appUserId : userIdInput.value).trim();
  if (!userId) throw new Error("사용자 ID를 입력해 주세요.");
  return userId;
}

function readAuthSession() {
  try {
    const saved = window.sessionStorage.getItem(authSessionStorageKey);
    if (!saved) return null;
    const parsed = JSON.parse(saved);
    if (
      !parsed
      || typeof parsed !== "object"
      || typeof parsed.idToken !== "string"
      || typeof parsed.refreshToken !== "string"
      || typeof parsed.expiresAt !== "number"
    ) {
      window.sessionStorage.removeItem(authSessionStorageKey);
      return null;
    }
    return parsed;
  } catch (error) {
    setMessage(
      document.getElementById("login-message"),
      `로그인 세션을 읽을 수 없습니다: ${error.message}`,
      true,
    );
    return null;
  }
}

function storeAuthSession(session) {
  authSession = session;
  window.sessionStorage.setItem(authSessionStorageKey, JSON.stringify(session));
}

function setAuthView(isAuthenticated) {
  document.getElementById("login-panel").hidden = isAuthenticated;
  document.getElementById("app-shell").hidden = !isAuthenticated;
  document.getElementById("logout-button").hidden = !isAuthenticated || !authEnabled;
  document.querySelector(".connection").hidden = authEnabled && !isAuthenticated;
  if (authEnabled && !isAuthenticated) {
    prepareGoogleLogin();
  }
}

function loadGoogleIdentity() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  if (googleIdentityPromise) return googleIdentityPromise;
  googleIdentityPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = () => {
      if (window.google?.accounts?.oauth2) {
        resolve();
      } else {
        googleIdentityPromise = null;
        reject(new Error("Google 로그인 모듈을 초기화하지 못했습니다."));
      }
    };
    script.onerror = () => {
      googleIdentityPromise = null;
      reject(new Error("Google 로그인 모듈을 불러오지 못했습니다."));
    };
    document.head.appendChild(script);
  });
  return googleIdentityPromise;
}

function prepareGoogleLogin() {
  const loginButton = document.getElementById("google-login-button");
  if (!firebaseApiKey || !googleOAuthClientId) {
    loginButton.disabled = true;
    setMessage(
      document.getElementById("login-message"),
      "Firebase 또는 Google OAuth 설정이 배포 환경에 없습니다.",
      true,
    );
    return;
  }
  loginButton.disabled = true;
  loadGoogleIdentity()
    .then(() => { loginButton.disabled = false; })
    .catch((error) => {
      loginButton.disabled = false;
      setMessage(document.getElementById("login-message"), error.message, true);
    });
}

async function refreshFirebaseSession() {
  if (!authSession?.refreshToken || !firebaseApiKey) return false;
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: authSession.refreshToken,
  });
  const response = await fetch(
    `https://securetoken.googleapis.com/v1/token?key=${encodeURIComponent(firebaseApiKey)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    },
  );
  if (!response.ok) {
    authSession = null;
    window.sessionStorage.removeItem(authSessionStorageKey);
    return false;
  }
  const result = await response.json();
  const expiresIn = Number(result.expires_in);
  if (
    typeof result.id_token !== "string"
    || typeof result.refresh_token !== "string"
    || !Number.isFinite(expiresIn)
    || expiresIn <= 0
  ) {
    throw new Error("Firebase가 유효한 갱신 세션을 반환하지 않았습니다.");
  }
  storeAuthSession({
    idToken: result.id_token,
    refreshToken: result.refresh_token,
    expiresAt: Date.now() + expiresIn * 1000,
  });
  return true;
}

async function request(path, options = {}, canRefresh = true) {
  if (authEnabled && authSession && authSession.expiresAt < Date.now() + 60_000) {
    await refreshFirebaseSession();
  }
  const headers = new Headers(options.headers || {});
  if (authSession?.idToken) {
    headers.set("Authorization", `Bearer ${authSession.idToken}`);
  }
  const response = await fetch(apiUrl(path), { ...options, headers });
  if (response.status === 401 && authEnabled && canRefresh) {
    if (await refreshFirebaseSession()) {
      return request(path, options, false);
    }
    authSession = null;
    window.sessionStorage.removeItem(authSessionStorageKey);
    setAuthView(false);
    setMessage(
      document.getElementById("login-message"),
      "로그인 세션이 만료되었습니다. 다시 로그인해 주세요.",
      true,
    );
  }
  if (!response.ok) {
    let detail = `요청에 실패했습니다 (${response.status}).`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      if (typeof body.error?.message === "string") {
        detail = body.error.message;
      }
    } catch {
      // Keep the HTTP status message if the server did not return JSON.
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

async function initializeAuthenticatedApp() {
  if (appInitialized) return;
  appInitialized = true;
  if (authEnabled) {
    userIdInput.value = appUserId;
    userIdInput.readOnly = true;
    apiBaseInput.readOnly = true;
    document.querySelector(".notice").hidden = true;
  }
  restorePendingMeal();
  checkConnection();
  refreshPage();
  refreshDataView();
  loadConversationHistory();
}

function firebaseLoginError(code) {
  return ({
    OPERATION_NOT_ALLOWED: "Firebase 콘솔에서 Google 로그인 제공자를 활성화해 주세요.",
    INVALID_OAUTH_CLIENT_ID: "Google OAuth 클라이언트 ID 설정을 확인해 주세요.",
    INVALID_IDP_RESPONSE: "Google 인증 응답을 확인하지 못했습니다. 다시 로그인해 주세요.",
    USER_DISABLED: "이 계정은 사용할 수 없습니다.",
    API_KEY_INVALID: "Firebase 웹 API 키 설정을 확인해 주세요.",
  })[code] || "Google 로그인에 실패했습니다. Firebase 및 Google OAuth 설정을 확인해 주세요.";
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatNumber(value) {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 }).format(value);
}

function formatDateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "날짜 미상"
    : new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function setMessage(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function nutrientInput(key) {
  return entryForm.elements.namedItem(key);
}

function clearNutrients() {
  selectedNutrients = null;
  for (const key of Object.keys(nutrientLabels)) {
    nutrientInput(key).value = "";
  }
  updateAddFoodButton();
}

function updateAddFoodButton() {
  addFoodButton.disabled = !selectedFood || !selectedNutrients;
}

function renderMealFoods() {
  const totalCalories = mealFoods.reduce(
    (total, food) => total + Number(food.nutrients.calories_kcal || 0),
    0,
  );
  document.getElementById("meal-food-count").textContent = String(mealFoods.length);
  document.getElementById("meal-calorie-total").textContent = `${formatNumber(totalCalories)} kcal`;
  if (!mealFoods.length) {
    document.getElementById("meal-food-list").innerHTML =
      '<p class="empty-state">음식 검색 후 한 끼에 추가해 주세요.</p>';
    return;
  }
  document.getElementById("meal-food-list").innerHTML = mealFoods.map((food, index) => `
    <div class="meal-food-row">
      <div>
        <strong>${escapeHtml(food.food_name)}</strong>
        <span>${formatNumber(food.amount)} ${escapeHtml(food.unit)} · ${formatNumber(food.nutrients.calories_kcal || 0)} kcal</span>
      </div>
      <button class="delete-button" type="button" data-meal-food-remove="${index}" aria-label="${escapeHtml(food.food_name)} 한 끼 구성에서 제거">제거</button>
    </div>`).join("");
}

function applyFoodAmount() {
  clearNutrients();
  if (!selectedFood) return false;

  const amount = Number(amountInput.value);
  if (!Number.isFinite(amount) || amount <= 0) {
    setMessage(lookupMessage, "섭취량을 0보다 큰 숫자로 입력해 주세요.", true);
    return false;
  }

  let amountInGrams;
  if (unitInput.value === "g") {
    amountInGrams = amount;
  } else if (unitInput.value === "kg") {
    amountInGrams = amount * 1000;
  } else if (unitInput.value === "serving" && selectedFood.serving_size_g > 0) {
    amountInGrams = amount * selectedFood.serving_size_g;
  } else {
    setMessage(lookupMessage, "이 음식은 1회 제공량 정보가 없어 인분으로 환산할 수 없습니다. g 또는 kg을 선택해 주세요.", true);
    return false;
  }

  const multiplier = amountInGrams / selectedFood.basis_amount_g;
  selectedNutrients = {};
  for (const [key, baseAmount] of Object.entries(selectedFood.nutrients_per_basis)) {
    const total = Number((baseAmount * multiplier).toFixed(2));
    selectedNutrients[key] = total;
    const input = nutrientInput(key);
    if (input) input.value = String(total);
  }
  updateAddFoodButton();
  setMessage(
    lookupMessage,
    `${selectedFood.food_name}의 ${formatNumber(selectedFood.basis_amount_g)}g 기준 영양정보를 ${formatNumber(amountInGrams)}g 섭취량으로 계산했습니다.`,
  );
  return true;
}

async function lookupFoodNutrition() {
  window.clearTimeout(lookupTimer);
  const query = foodNameInput.value.trim();
  if (!query) {
    setMessage(lookupMessage, "먼저 음식 이름을 입력해 주세요.", true);
    foodNameInput.focus();
    return;
  }

  const button = document.getElementById("lookup-button");
  const requestSequence = ++lookupSequence;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.firstChild.textContent = "검색 중... ";
  setMessage(lookupMessage, "식품 영양정보를 검색 중...");
  foodMatchField.hidden = true;
  foodMatches = [];
  selectedFood = null;
  clearNutrients();
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 18000);
  try {
    const params = new URLSearchParams({ query, limit: "10" });
    const matches = await request(`/api/food-nutrition?${params}`, {
      signal: controller.signal,
    });
    if (requestSequence !== lookupSequence || query !== foodNameInput.value.trim()) return;
    foodMatches = matches;
    if (!foodMatches.length) {
      setMessage(lookupMessage, "영양정보를 찾지 못했습니다. 음식 이름을 바꿔 다시 검색해 주세요.", true);
      return;
    }
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "검색 결과를 직접 선택해 주세요";
    placeholder.selected = true;
    foodMatchInput.replaceChildren(placeholder, ...foodMatches.map((food, index) => {
      const option = document.createElement("option");
      const calories = food.nutrients_per_basis.calories_kcal;
      option.value = String(index);
      option.textContent = `${food.food_name}${calories == null ? "" : ` · ${formatNumber(food.basis_amount_g)}g ${formatNumber(calories)} kcal`}`;
      return option;
    }));
    foodMatchField.hidden = false;
    selectedFood = null;
    clearNutrients();
    setMessage(lookupMessage, `${foodMatches.length}개 검색 결과가 있습니다. 목록에서 먹은 음식을 직접 선택해 주세요.`);
  } catch (error) {
    if (requestSequence === lookupSequence) {
      const message = error.name === "AbortError"
        ? "식품 영양정보 검색이 18초 안에 끝나지 않았습니다. 잠시 후 다시 시도해 주세요."
        : error.message;
      setMessage(lookupMessage, message, true);
    }
  } finally {
    window.clearTimeout(timeoutId);
    if (requestSequence === lookupSequence) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.firstChild.textContent = "영양정보 다시 찾기 ";
    }
  }
}

function selectFoodMatch() {
  if (foodMatchInput.value === "") {
    selectedFood = null;
    clearNutrients();
    setMessage(lookupMessage, "목록에서 먹은 음식과 가장 가까운 항목을 선택해 주세요.");
    return;
  }
  selectedFood = foodMatches[Number(foodMatchInput.value)] || null;
  if (selectedFood) applyFoodAmount();
}

function clearCurrentFood() {
  lookupSequence += 1;
  window.clearTimeout(lookupTimer);
  foodNameInput.value = "";
  foodMatchField.hidden = true;
  foodMatches = [];
  selectedFood = null;
  clearNutrients();
  amountInput.value = "1";
  unitInput.value = "g";
  document.getElementById("lookup-button").disabled = false;
  setMessage(lookupMessage, "");
}

function addCurrentFoodToMeal() {
  if (!selectedFood || !selectedNutrients) {
    setMessage(formMessage, "먼저 음식 검색 결과를 선택하고 섭취량을 확인해 주세요.", true);
    return;
  }
  const amount = Number(amountInput.value);
  if (!Number.isFinite(amount) || amount <= 0) {
    setMessage(formMessage, "섭취량을 0보다 큰 숫자로 입력해 주세요.", true);
    amountInput.focus();
    return;
  }
  mealFoods.push({
    food_name: selectedFood.food_name,
    amount,
    unit: unitInput.value,
    nutrients: { ...selectedNutrients },
    source: "food_safety_api",
  });
  const savedTemporarily = persistPendingMeal();
  renderMealFoods();
  clearCurrentFood();
  setMessage(
    formMessage,
    savedTemporarily
      ? "음식을 한 끼 구성에 추가했습니다. 반찬이나 음식을 더 추가할 수 있습니다."
      : "음식은 한 끼 구성에 추가했지만 임시 보존에 실패했습니다. 페이지를 닫지 말고 저장해 주세요.",
    !savedTemporarily,
  );
}

function selectedPeriod() {
  const start = document.getElementById("start-date").value;
  const end = document.getElementById("end-date").value;
  if (!start || !end) throw new Error("분석할 시작일과 종료일을 모두 선택해 주세요.");
  if (start > end) throw new Error("시작일은 종료일보다 늦을 수 없습니다.");
  return { start, end };
}

async function loadEntries() {
  const userId = encodeURIComponent(currentUserId());
  const { start, end } = selectedPeriod();
  const query = new URLSearchParams({ start_date: start, end_date: end, limit: "500" });
  entriesList.innerHTML = '<p class="empty-state">기록을 불러오는 중...</p>';
  const entries = await request(`/users/${userId}/food-entries?${query}`);
  const meals = new Map();
  for (const entry of entries) {
    const mealKey = entry.meal_id || entry.id;
    if (!meals.has(mealKey)) meals.set(mealKey, []);
    meals.get(mealKey).push(entry);
  }
  const countBadge = document.getElementById("entry-count");
  countBadge.textContent = String(meals.size);
  countBadge.title = `${meals.size}끼 식사, ${entries.length}개 음식`;
  if (!entries.length) {
    entriesList.innerHTML = '<p class="empty-state">선택한 기간에 식사 기록이 없습니다.</p>';
    return;
  }
  entriesList.innerHTML = [...meals.values()].map((mealEntries) => {
    const firstEntry = mealEntries[0];
    const mealLabel = {
      breakfast: "아침",
      lunch: "점심",
      dinner: "저녁",
      snack: "간식",
    }[firstEntry.meal_type] || firstEntry.meal_type;
    const calorieTotal = mealEntries.reduce(
      (total, entry) => total + Number(entry.nutrients?.calories_kcal || 0),
      0,
    );
    const foodRows = mealEntries.map((entry) => {
      const nutrients = Object.entries(entry.nutrients || {})
        .map(([key, value]) => `${escapeHtml(nutrientLabels[key] || key)} ${formatNumber(value)}${key.endsWith("_g") ? "g" : key.endsWith("_kcal") ? "kcal" : key.endsWith("_mg") ? "mg" : ""}`)
        .join(" · ");
      return `
        <div class="entry-food">
          <div class="entry-main">
            <div>
              <h3>${escapeHtml(entry.food_name)}</h3>
              <p class="entry-amount">${formatNumber(entry.amount)} ${escapeHtml(entry.unit)}</p>
            </div>
            <button class="delete-button" type="button" data-entry-id="${escapeHtml(entry.id)}" aria-label="${escapeHtml(entry.food_name)} 기록 삭제">삭제</button>
          </div>
          ${nutrients ? `<p class="entry-nutrients">${nutrients}</p>` : ""}
        </div>`;
    }).join("");
    return `
      <article class="entry-card">
        <div class="entry-topline">
          <span class="meal-tag">${escapeHtml(mealLabel)}</span>
          <time>${escapeHtml(formatDateTime(firstEntry.recorded_at))}</time>
          <span>${mealEntries.length}개 음식 · ${formatNumber(calorieTotal)} kcal</span>
          <button class="delete-button" type="button" data-meal-id="${escapeHtml(firstEntry.meal_id || firstEntry.id)}" aria-label="${escapeHtml(mealLabel)} 한 끼 식사 삭제">한 끼 삭제</button>
        </div>
        <div class="entry-food-list">${foodRows}</div>
        ${firstEntry.memo ? `<p class="entry-memo">${escapeHtml(firstEntry.memo)}</p>` : ""}
      </article>`;
  }).join("");
}

async function loadSummary() {
  const userId = encodeURIComponent(currentUserId());
  const { start, end } = selectedPeriod();
  setMessage(summaryMessage, "분석 중...");
  const query = new URLSearchParams({ start_date: start, end_date: end });
  const summary = await request(`/users/${userId}/analysis/summary?${query}`);
  const keyMetrics = [
    ["calories_kcal", "열량", "kcal"],
    ["protein_g", "단백질", "g"],
    ["carbohydrate_g", "탄수화물", "g"],
    ["fat_g", "지방", "g"],
  ];
  const metrics = keyMetrics.map(([key, label, unit]) => {
    const total = summary.nutrient_totals[key] ?? 0;
    const average = summary.daily_nutrient_averages[key] ?? 0;
    return `
      <div class="metric-card">
        <span>${label}</span>
        <strong>${formatNumber(total)}<small>${unit}</small></strong>
        <p>일평균 ${formatNumber(average)} ${unit}</p>
      </div>`;
  }).join("");
  const days = Object.entries(summary.daily_entry_counts || {});
  const dailyRows = days.length
    ? days.map(([day, count]) => `<li><time>${escapeHtml(day)}</time><span>${count}끼 식사</span></li>`).join("")
    : '<li class="no-days">아직 기록된 식사가 없습니다.</li>';
  const notes = (summary.notes || []).map((note) => `<li>${escapeHtml(note)}</li>`).join("");
  summaryContent.innerHTML = `
    <div class="summary-total"><strong>${summary.entry_count}</strong><span>끼 식사 · ${summary.food_entry_count ?? summary.entry_count}개 음식 기록</span></div>
    <div class="metrics-grid">${metrics}</div>
    <div class="daily-section">
      <h3>날짜별 기록</h3>
      <ul class="daily-list">${dailyRows}</ul>
    </div>
    ${notes ? `<ul class="summary-notes">${notes}</ul>` : ""}`;
  setMessage(summaryMessage, "분석 내용을 저장했습니다.");
}

async function refreshPage() {
  setMessage(formMessage, "");
  setMessage(summaryMessage, "");
  try {
    const results = await Promise.allSettled([loadEntries(), loadSummary()]);
    const failed = results.find((result) => result.status === "rejected");
    if (failed) {
      if (results[0].status === "rejected") {
        entriesList.innerHTML = `<p class="empty-state error">${escapeHtml(failed.reason.message)}</p>`;
      }
      if (results[1].status === "rejected") {
        summaryContent.innerHTML = `<p class="empty-state error">${escapeHtml(results[1].reason.message)}</p>`;
        setMessage(summaryMessage, results[1].reason.message, true);
      }
    }
  } catch (error) {
    setMessage(formMessage, error.message, true);
  }
}

async function checkConnection() {
  try {
    const health = await request("/health");
    connectionStatus.textContent = health.firestore_connected
      ? "API · Firestore 연결됨"
      : "API 연결됨 · Firestore 설정 필요";
    connectionDot.classList.toggle("connected", Boolean(health.firestore_connected));
    connectionDot.classList.toggle("warning", !health.firestore_connected);
  } catch {
    connectionStatus.textContent = "API에 연결할 수 없습니다";
    connectionDot.classList.remove("connected");
    connectionDot.classList.add("warning");
  }
}

function renderDataSummary(summary) {
  const number = (value) => value == null ? "—" : formatNumber(value);
  const trendLabels = {
    increase: "증가",
    decrease: "감소",
    stable: "유지",
    insufficient_data: "데이터 부족",
  };
  const trend = summary.trend || {};
  const trendText = trend.direction === "insufficient_data"
    ? "비교 가능한 데이터가 4개 이상 필요합니다."
    : `최근 ${trend.compared_points.recent}개 평균 ${number(trend.recent_average)} kcal · 이전 ${trend.compared_points.previous}개 평균 ${number(trend.previous_average)} kcal · ${trend.change > 0 ? "+" : ""}${number(trend.change)} kcal`;
  document.getElementById("data-summary-content").innerHTML = `
    <p class="summary-period">${escapeHtml(summary.period_start)} ~ ${escapeHtml(summary.period_end)}</p>
    <div class="summary-total"><strong>${summary.count}</strong><span>개 데이터 포인트</span></div>
    <div class="metrics-grid">
      <div class="metric-card"><span>평균</span><strong>${number(summary.average)}<small>kcal</small></strong></div>
      <div class="metric-card"><span>중앙값</span><strong>${number(summary.median)}<small>kcal</small></strong><p>기록을 크기순으로 나눈 가운데 값</p></div>
      <div class="metric-card"><span>표준편차</span><strong>${number(summary.standard_deviation)}<small>kcal</small></strong><p>평균을 중심으로 한 기록의 변동 폭</p></div>
      <div class="metric-card"><span>최대</span><strong>${number(summary.maximum)}<small>kcal</small></strong></div>
      <div class="metric-card"><span>최소</span><strong>${number(summary.minimum)}<small>kcal</small></strong></div>
      <div class="metric-card"><span>최근 추세</span><strong>${escapeHtml(trendLabels[trend.direction] || "—")}</strong><p>${escapeHtml(trendText)}</p></div>
    </div>`;
  setMessage(document.getElementById("data-summary-message"), "요약을 불러왔습니다.");
}

async function loadDataSummary() {
  const userId = currentUserId();
  const start = document.getElementById("data-start-date").value;
  const end = document.getElementById("data-end-date").value;
  if (!start || !end) throw new Error("분석할 시작일과 종료일을 선택해 주세요.");
  if (start > end) throw new Error("시작일은 종료일보다 늦을 수 없습니다.");
  const query = new URLSearchParams({ user_id: userId, start_date: start, end_date: end });
  setMessage(document.getElementById("data-summary-message"), "요약 계산 중...");
  const summary = await request(`/api/data/summary?${query}`);
  renderDataSummary(summary);
}

function cancelDataEdit() {
  editingDataId = null;
  document.getElementById("data-form").reset();
  document.getElementById("data-date").value = localDateValue(new Date());
  document.getElementById("data-form-title").textContent = "관측값 추가";
  document.getElementById("data-submit").textContent = "데이터 저장";
  document.getElementById("data-cancel-edit").hidden = true;
  setMessage(document.getElementById("data-form-message"), "");
}

function renderDataList(records) {
  const list = document.getElementById("data-list");
  document.getElementById("data-count").textContent = records.length;
  if (!records.length) {
    list.innerHTML = '<p class="empty-state">선택한 기간의 데이터가 없습니다. 100개 이상을 준비하면 추세를 더 잘 볼 수 있습니다.</p>';
    return;
  }
  list.innerHTML = records.map((record) => `
    <article class="data-record">
      <div class="data-record-main">
        <time>${escapeHtml(record.date)}</time>
        <strong>${formatNumber(record.value)} <small>kcal</small></strong>
        ${record.memo ? `<p>${escapeHtml(record.memo)}</p>` : ""}
      </div>
      <div class="data-record-actions">
        <button class="delete-button" type="button" data-data-edit="${escapeHtml(record.id)}">수정</button>
        <button class="delete-button" type="button" data-data-delete="${escapeHtml(record.id)}">삭제</button>
      </div>
    </article>`).join("");
}

async function loadDataRecords() {
  const userId = currentUserId();
  const start = document.getElementById("data-start-date").value;
  const end = document.getElementById("data-end-date").value;
  if (!start || !end) throw new Error("조회할 시작일과 종료일을 선택해 주세요.");
  const query = new URLSearchParams({
    user_id: userId,
    start_date: start,
    end_date: end,
    limit: "500",
  });
  const records = await request(`/api/data?${query}`);
  renderDataList(records);
}

async function refreshDataView() {
  try {
    const results = await Promise.allSettled([loadDataRecords(), loadDataSummary()]);
    const listResult = results[0];
    const summaryResult = results[1];
    if (listResult.status === "rejected") {
      document.getElementById("data-list").innerHTML =
        `<p class="empty-state error">${escapeHtml(listResult.reason.message)}</p>`;
    }
    if (summaryResult.status === "rejected") {
      document.getElementById("data-summary-content").innerHTML =
        `<p class="empty-state error">${escapeHtml(summaryResult.reason.message)}</p>`;
      setMessage(document.getElementById("data-summary-message"), summaryResult.reason.message, true);
    }
  } catch (error) {
    setMessage(document.getElementById("data-form-message"), error.message, true);
  }
}

async function editDataRecord(recordId) {
  const userId = currentUserId();
  const query = new URLSearchParams({ user_id: userId });
  const records = await request(`/api/data?${query}&limit=10000`);
  const record = records.find((item) => item.id === recordId);
  if (!record) throw new Error("수정할 데이터를 찾을 수 없습니다. 목록을 새로고침해 주세요.");
  editingDataId = record.id;
  document.getElementById("data-date").value = record.date;
  document.getElementById("data-value").value = record.value;
  document.getElementById("data-memo").value = record.memo || "";
  document.getElementById("data-form-title").textContent = "관측값 수정";
  document.getElementById("data-submit").textContent = "수정 저장";
  document.getElementById("data-cancel-edit").hidden = false;
  document.getElementById("data-form").scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderMessages() {
  const container = document.getElementById("chat-messages");
  if (!activeMessages.length) {
    container.innerHTML = '<p class="empty-state chat-empty">예: “오늘 먹은 음식과 열량을 알려줘.”</p>';
    return;
  }
  container.innerHTML = activeMessages.map((message) => `
    <article class="chat-bubble ${message.role === "user" ? "user-bubble" : "assistant-bubble"}">
      <span>${message.role === "user" ? "나" : "AI 분석"}</span>
      <p>${escapeHtml(message.content)}</p>
    </article>`).join("");
  container.scrollTop = container.scrollHeight;
}

async function loadConversationList() {
  const query = new URLSearchParams({ user_id: currentUserId(), limit: "100" });
  const conversations = await request(`/api/conversations?${query}`);
  const list = document.getElementById("conversation-list");
  if (!conversations.length) {
    list.innerHTML = '<p class="empty-state">저장된 대화가 없습니다. 질문을 보내면 대화가 자동 저장됩니다.</p>';
    return;
  }
  list.innerHTML = conversations.map((conversation) => `
    <article class="conversation-card ${conversation.id === activeConversationId ? "selected" : ""}">
      <button class="conversation-open" type="button" data-conversation-open="${escapeHtml(conversation.id)}">
        <strong>${escapeHtml(conversation.title || "새 대화")}</strong>
        <time>${escapeHtml(formatDateTime(conversation.updated_at))}</time>
      </button>
      <button class="delete-button" type="button" data-conversation-delete="${escapeHtml(conversation.id)}">삭제</button>
    </article>`).join("");
}

async function loadConversationHistory() {
  try {
    await loadConversationList();
    setMessage(document.getElementById("conversation-list-message"), "");
  } catch (error) {
    document.getElementById("conversation-list").innerHTML =
      `<p class="empty-state error">${escapeHtml(error.message)}</p>`;
    setMessage(document.getElementById("conversation-list-message"), error.message, true);
  }
}

async function openConversation(conversationId) {
  const query = new URLSearchParams({ user_id: currentUserId() });
  const conversation = await request(
    `/api/conversations/${encodeURIComponent(conversationId)}?${query}`,
  );
  activeConversationId = conversation.id;
  activeMessages = conversation.messages || [];
  document.getElementById("chat-title").textContent = conversation.title || "저장된 대화";
  renderMessages();
  await loadConversationList();
}

function startNewConversation() {
  activeConversationId = null;
  activeMessages = [];
  document.getElementById("chat-title").textContent = "데이터에게 질문하기";
  setMessage(document.getElementById("chat-message"), "");
  renderMessages();
  loadConversationHistory();
  document.getElementById("chat-input").focus();
}

entryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage(formMessage, "저장 중...");
  const submitButton = entryForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const foodsToSave = [...mealFoods];
    if (selectedFood && selectedNutrients) {
      const amount = Number(amountInput.value);
      if (!Number.isFinite(amount) || amount <= 0) {
        throw new Error("현재 선택한 음식의 섭취량을 0보다 큰 숫자로 입력해 주세요.");
      }
      foodsToSave.push({
        food_name: selectedFood.food_name,
        amount,
        unit: unitInput.value,
        nutrients: { ...selectedNutrients },
        source: "food_safety_api",
      });
    } else if (foodNameInput.value.trim()) {
      throw new Error("현재 입력한 음식의 검색 결과를 선택하거나 이름을 지운 뒤 저장해 주세요.");
    }
    if (!foodsToSave.length) {
      throw new Error("한 끼를 저장하기 전에 음식 하나 이상을 검색해 추가해 주세요.");
    }
    const form = new FormData(entryForm);
    const recordedAt = new Date(form.get("recorded_at"));
    if (Number.isNaN(recordedAt.getTime())) throw new Error("날짜와 시간을 확인해 주세요.");
    const payload = {
      recorded_at: recordedAt.toISOString(),
      meal_type: form.get("meal_type"),
      foods: foodsToSave,
      memo: form.get("memo"),
    };
    await request(`/users/${encodeURIComponent(currentUserId())}/food-entries/meal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    mealFoods = [];
    const pendingMealCleared = persistPendingMeal();
    renderMealFoods();
    clearCurrentFood();
    document.getElementById("memo").value = "";
    await refreshPage();
    setMessage(
      formMessage,
      pendingMealCleared
        ? "한 끼 식사 내용을 저장했습니다."
        : "한 끼 식사 내용을 저장했습니다. 단, 브라우저의 임시 구성을 지우지 못했습니다.",
      !pendingMealCleared,
    );
  } catch (error) {
    setMessage(formMessage, error.message, true);
  } finally {
    submitButton.disabled = false;
  }
});

document.getElementById("analyze-button").addEventListener("click", refreshPage);
document.getElementById("refresh-button").addEventListener("click", refreshPage);
document.getElementById("lookup-button").addEventListener("click", lookupFoodNutrition);
addFoodButton.addEventListener("click", addCurrentFoodToMeal);
foodMatchInput.addEventListener("change", selectFoodMatch);
amountInput.addEventListener("input", applyFoodAmount);
unitInput.addEventListener("change", applyFoodAmount);
foodNameInput.addEventListener("input", () => {
  lookupSequence += 1;
  window.clearTimeout(lookupTimer);
  document.getElementById("lookup-button").disabled = false;
  selectedFood = null;
  foodMatches = [];
  foodMatchField.hidden = true;
  clearNutrients();
  setMessage(lookupMessage, "");
  setMessage(formMessage, "");
  if (foodNameInput.value.trim()) {
    lookupTimer = window.setTimeout(lookupFoodNutrition, 650);
  }
});
document.getElementById("meal-food-list").addEventListener("click", (event) => {
  const removeButton = event.target.closest("[data-meal-food-remove]");
  if (!removeButton) return;
  mealFoods.splice(Number(removeButton.dataset.mealFoodRemove), 1);
  persistPendingMeal();
  renderMealFoods();
});
apiBaseInput.addEventListener("change", () => {
  restorePendingMeal();
  checkConnection();
  refreshPage();
  refreshDataView();
  loadConversationHistory();
});
userIdInput.addEventListener("change", () => {
  restorePendingMeal();
  refreshPage();
  refreshDataView();
  activeConversationId = null;
  activeMessages = [];
  renderMessages();
  loadConversationHistory();
});
entriesList.addEventListener("click", async (event) => {
  const mealButton = event.target.closest("[data-meal-id]");
  const button = event.target.closest("[data-entry-id]");
  if (!mealButton && !button) return;
  const isDeletingMeal = Boolean(mealButton);
  const itemName = button?.getAttribute("aria-label")?.replace(/ 기록 삭제$/, "") || "";
  const confirmation = isDeletingMeal
    ? "이 한 끼 식사에 포함된 모든 음식 기록을 삭제할까요?"
    : `${itemName ? `${itemName} ` : ""}음식 기록만 삭제할까요?`;
  const deleteTarget = mealButton || button;
  deleteTarget.disabled = true;
  if (!window.confirm(confirmation)) {
    deleteTarget.disabled = false;
    return;
  }
  try {
    const userPath = `/users/${encodeURIComponent(currentUserId())}/food-entries`;
    const path = isDeletingMeal
      ? `${userPath}/meals/${encodeURIComponent(mealButton.dataset.mealId)}`
      : `${userPath}/${encodeURIComponent(button.dataset.entryId)}`;
    await request(path, { method: "DELETE" });
    await refreshPage();
    setMessage(
      formMessage,
      isDeletingMeal ? "한 끼 식사 기록을 삭제했습니다." : "음식 기록을 삭제했습니다.",
    );
  } catch (error) {
    deleteTarget.disabled = false;
    setMessage(formMessage, error.message, true);
  }
});

document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => {
    const targetId = button.dataset.viewTarget;
    document.querySelectorAll(".nav-tab").forEach((tab) => {
      tab.classList.toggle("active", tab === button);
    });
    document.querySelectorAll(".app-view").forEach((view) => {
      view.hidden = view.id !== targetId;
    });
    if (targetId === "data-view") refreshDataView();
    if (targetId === "chat-view") loadConversationHistory();
  });
});

document.getElementById("weather-recommend-button").addEventListener("click", async () => {
  const button = document.getElementById("weather-recommend-button");
  const message = document.getElementById("weather-recommend-message");
  const file = document.getElementById("weather-csv-file").files[0];
  const targetDate = document.getElementById("weather-target-date").value;
  if (!targetDate) {
    setMessage(message, "추천 날짜를 선택해 주세요.", true);
    return;
  }
  button.disabled = true;
    setMessage(message, file ? "CSV의 날씨를 분석하고 음식 후보를 찾는 중..." : "저장된 날씨를 확인하고 음식 후보를 찾는 중...");
  try {
    let path = "/api/weather/recommend-saved";
    let payload = { user_id: currentUserId(), target_date: targetDate };
    if (file) {
      const bytes = await file.arrayBuffer();
      let csvText = new TextDecoder("utf-8").decode(bytes);
      if (csvText.includes("\uFFFD")) csvText = new TextDecoder("euc-kr").decode(bytes);
      path = "/api/weather/csv/recommend";
      payload = { ...payload, csv_text: csvText };
    }
    const result = await request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...payload,
      }),
    });
    const number = (value) => value == null ? "미기록" : formatNumber(value);
    const foods = result.foods.length
      ? result.foods.map((food) => `<article class="weather-food-card"><strong>${escapeHtml(food.food_name)}</strong><span>${number(food.calories_kcal)} kcal</span><p>단백질 ${number(food.protein_g)} g · 탄수화물 ${number(food.carbohydrate_g)} g · 기준 ${number(food.nutrient_basis_g)} g<br>${escapeHtml(food.reason || "날씨 조건에 맞는 메뉴 후보입니다.")}</p></article>`).join("")
      : '<p class="empty-state">조건에 맞는 식품 후보가 없습니다. 다른 날짜나 CSV 자료로 다시 시도해 보세요.</p>';
    const weather = result.weather || {};
    const sourceLabel = file ? "업로드한 CSV" : "저장된 날씨 자료";
    const humidity = weather.humidity_percent == null ? "" : `<div class="metric-card"><span>습도</span><strong>${number(weather.humidity_percent)}<small>%</small></strong></div>`;
    document.getElementById("weather-recommend-result").innerHTML = `
      <div class="weather-summary-head"><strong>${escapeHtml(result.target_date)} · ${escapeHtml(weather.city || "창원")}</strong><span class="weather-source-tag">${sourceLabel}</span></div>
      <div class="metrics-grid weather-metrics">
        <div class="metric-card"><span>평균 기온</span><strong>${number(weather.temperature_c)}<small>°C</small></strong></div>
        <div class="metric-card"><span>강수량</span><strong>${number(weather.precipitation_mm)}<small>mm</small></strong></div>
        ${humidity}
      </div>
      <p class="weather-reason">${escapeHtml(result.recommendation_reason || "날씨 특성을 기준으로 메뉴를 골랐습니다.")}</p>
      <h3 class="weather-foods-title">오늘의 메뉴 후보</h3><div class="weather-food-list">${foods}</div>
      <ul class="weather-quality"><li>최근 7일 관측 ${number(result.recent_weather_days)}일</li><li>누락 ${number(result.missing_days_in_recent_week)}일</li><li>당일 중복 ${number(result.duplicate_rows_for_target_date)}행</li></ul>
      <ul class="summary-notes"><li>날씨 기준의 참고용 음식 후보입니다. 개인의 알레르기나 건강 상태는 반영하지 않습니다.</li><li>기상 기록의 결측·중복 정보를 함께 표시하며, 장기 계절성 및 이상치 검정은 별도로 수행하지 않습니다.</li></ul>`;
    setMessage(message, file ? "CSV 날씨를 분석해 추천 결과를 만들었습니다." : "저장된 날씨 자료로 추천 결과를 만들었습니다.");
  } catch (error) {
    setMessage(message, error.message, true);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("data-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = document.getElementById("data-submit");
  submit.disabled = true;
  setMessage(document.getElementById("data-form-message"), "저장 중...");
  try {
    currentUserId();
    const payload = {
      date: document.getElementById("data-date").value,
      value: Number(document.getElementById("data-value").value),
      memo: document.getElementById("data-memo").value.trim(),
    };
    const query = new URLSearchParams({ user_id: currentUserId() });
    const path = editingDataId
      ? `/api/data/${encodeURIComponent(editingDataId)}?${query}`
      : `/api/data?${query}`;
    await request(path, {
      method: editingDataId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    cancelDataEdit();
    setMessage(document.getElementById("data-form-message"), "데이터를 저장했습니다.");
    await refreshDataView();
  } catch (error) {
    setMessage(document.getElementById("data-form-message"), error.message, true);
  } finally {
    submit.disabled = false;
  }
});

document.getElementById("data-cancel-edit").addEventListener("click", cancelDataEdit);
document.getElementById("data-analyze-button").addEventListener("click", refreshDataView);
document.getElementById("data-refresh-button").addEventListener("click", refreshDataView);
document.getElementById("data-list").addEventListener("click", async (event) => {
  const editButton = event.target.closest("[data-data-edit]");
  const deleteButton = event.target.closest("[data-data-delete]");
  try {
    if (editButton) {
      await editDataRecord(editButton.dataset.dataEdit);
    } else if (deleteButton) {
      if (!window.confirm("이 데이터 기록을 삭제할까요?")) return;
      const query = new URLSearchParams({ user_id: currentUserId() });
      await request(`/api/data/${encodeURIComponent(deleteButton.dataset.dataDelete)}?${query}`, {
        method: "DELETE",
      });
      await refreshDataView();
    }
  } catch (error) {
    setMessage(document.getElementById("data-form-message"), error.message, true);
  }
});

document.getElementById("new-chat-button").addEventListener("click", startNewConversation);
document.getElementById("conversation-list").addEventListener("click", async (event) => {
  const openButton = event.target.closest("[data-conversation-open]");
  const deleteButton = event.target.closest("[data-conversation-delete]");
  try {
    if (openButton) {
      await openConversation(openButton.dataset.conversationOpen);
    } else if (deleteButton) {
      if (!window.confirm("이 대화를 삭제할까요?")) return;
      const query = new URLSearchParams({ user_id: currentUserId() });
      await request(
        `/api/conversations/${encodeURIComponent(deleteButton.dataset.conversationDelete)}?${query}`,
        { method: "DELETE" },
      );
      if (activeConversationId === deleteButton.dataset.conversationDelete) {
        startNewConversation();
      }
      await loadConversationHistory();
    }
  } catch (error) {
    setMessage(document.getElementById("conversation-list-message"), error.message, true);
  }
});

document.getElementById("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const sendButton = document.getElementById("chat-send-button");
  const message = input.value.trim();
  if (!message) return;
  sendButton.disabled = true;
  setMessage(document.getElementById("chat-message"), "저장된 데이터 요약을 불러와 답변을 생성 중...");
  try {
    const result = await request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: currentUserId(),
        conversation_id: activeConversationId,
        message,
      }),
    });
    activeConversationId = result.conversation_id;
    activeMessages.push(
      { role: "user", content: message },
      { role: "assistant", content: result.message },
    );
    document.getElementById("chat-title").textContent =
      activeMessages.find((item) => item.role === "user")?.content.slice(0, 80) || "저장된 대화";
    input.value = "";
    renderMessages();
    setMessage(document.getElementById("chat-message"), "대화를 저장했습니다.");
    await loadConversationHistory();
  } catch (error) {
    setMessage(document.getElementById("chat-message"), error.message, true);
  } finally {
    sendButton.disabled = false;
  }
});

function localDateTimeValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function localDateValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

async function finishGoogleSignIn(accessToken) {
  const loginButton = document.getElementById("google-login-button");
  const loginMessage = document.getElementById("login-message");
  try {
    const response = await fetch(
      `https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=${encodeURIComponent(firebaseApiKey)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          postBody: new URLSearchParams({
            access_token: accessToken,
            providerId: "google.com",
          }).toString(),
          requestUri: window.location.origin,
          returnIdpCredential: true,
          returnSecureToken: true,
        }),
      },
    );
    const result = await response.json();
    if (!response.ok) {
      const code = result.error?.message?.split(":")[0];
      throw new Error(firebaseLoginError(code));
    }
    const expiresIn = Number(result.expiresIn);
    if (
      typeof result.idToken !== "string"
      || typeof result.refreshToken !== "string"
      || !Number.isFinite(expiresIn)
      || expiresIn <= 0
    ) {
      throw new Error("Firebase가 유효한 로그인 세션을 반환하지 않았습니다.");
    }
    storeAuthSession({
      idToken: result.idToken,
      refreshToken: result.refreshToken,
      expiresAt: Date.now() + expiresIn * 1000,
    });
    const session = await request("/api/auth/session");
    userIdInput.value = session.user_id;
    setAuthView(true);
    setMessage(loginMessage, "");
    await initializeAuthenticatedApp();
  } catch (error) {
    authSession = null;
    window.sessionStorage.removeItem(authSessionStorageKey);
    setMessage(loginMessage, error.message, true);
  } finally {
    loginButton.disabled = false;
  }
}

document.getElementById("google-login-button").addEventListener("click", () => {
  const loginButton = document.getElementById("google-login-button");
  const loginMessage = document.getElementById("login-message");
  if (!firebaseApiKey || !googleOAuthClientId) {
    setMessage(loginMessage, "Firebase 또는 Google OAuth 설정이 배포 환경에 없습니다.", true);
    return;
  }
  if (!window.google?.accounts?.oauth2) {
    setMessage(loginMessage, "Google 로그인 모듈을 불러오는 중입니다. 잠시 후 다시 시도해 주세요.", true);
    prepareGoogleLogin();
    return;
  }
  loginButton.disabled = true;
  setMessage(loginMessage, "Google 계정 인증을 기다리는 중...");
  try {
    const tokenClient = window.google.accounts.oauth2.initTokenClient({
      client_id: googleOAuthClientId,
      scope: "openid email profile",
      callback: async (tokenResponse) => {
        if (tokenResponse.error || !tokenResponse.access_token) {
          setMessage(
            loginMessage,
            tokenResponse.error_description || "Google 계정 인증이 완료되지 않았습니다.",
            true,
          );
          loginButton.disabled = false;
          return;
        }
        setMessage(loginMessage, "Firebase 로그인 세션을 확인 중...");
        await finishGoogleSignIn(tokenResponse.access_token);
      },
      error_callback: (error) => {
        setMessage(loginMessage, error.message || "Google 로그인 창을 열지 못했습니다.", true);
        loginButton.disabled = false;
      },
    });
    tokenClient.requestAccessToken({ prompt: "select_account" });
  } catch (error) {
    setMessage(loginMessage, error.message, true);
    loginButton.disabled = false;
  }
});

document.getElementById("logout-button").addEventListener("click", () => {
  authSession = null;
  window.sessionStorage.removeItem(authSessionStorageKey);
  setAuthView(false);
  setMessage(document.getElementById("login-message"), "로그아웃했습니다.");
});

const today = localDateValue(new Date());
const initialDataStart = new Date();
initialDataStart.setDate(initialDataStart.getDate() - 119);
document.getElementById("recorded-at").value = localDateTimeValue(new Date());
const latestWeatherDate = new Date();
latestWeatherDate.setDate(latestWeatherDate.getDate() - 1);
document.getElementById("weather-target-date").value = localDateValue(latestWeatherDate);
document.getElementById("start-date").value = today;
document.getElementById("end-date").value = today;
document.getElementById("data-date").value = today;
document.getElementById("data-start-date").value = localDateValue(initialDataStart);
document.getElementById("data-end-date").value = today;
const initialView = new URLSearchParams(window.location.search).get("view");
if (initialView) {
  const initialTab = [...document.querySelectorAll("[data-view-target]")]
    .find((tab) => tab.dataset.viewTarget === initialView);
  initialTab?.click();
}
if (authEnabled) {
  setAuthView(false);
  authSession = readAuthSession();
  if (authSession) {
    request("/api/auth/session")
      .then((session) => {
        userIdInput.value = session.user_id;
        setAuthView(true);
        return initializeAuthenticatedApp();
      })
      .catch((error) => {
        authSession = null;
        window.sessionStorage.removeItem(authSessionStorageKey);
        setMessage(document.getElementById("login-message"), error.message, true);
      });
  }
} else {
  setAuthView(true);
  initializeAuthenticatedApp();
}
