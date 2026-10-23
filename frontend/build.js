const fs = require("node:fs");
const path = require("node:path");

const apiBaseUrl = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");
const firebaseApiKey = (process.env.FIREBASE_API_KEY || "").trim();
const googleOAuthClientId = (process.env.GOOGLE_OAUTH_CLIENT_ID || "").trim();
const authEnabled = Boolean(
  process.env.VERCEL || process.env.FIREBASE_HOSTING || process.env.GCLOUD_PROJECT,
);
if (authEnabled && !apiBaseUrl) {
  throw new Error("배포 환경 변수 API_BASE_URL에 Render 백엔드의 HTTPS URL을 설정하세요.");
}
if (authEnabled && !firebaseApiKey) {
  throw new Error("Firebase 로그인 사용을 위해 FIREBASE_API_KEY를 설정하세요.");
}
if (authEnabled && !googleOAuthClientId) {
  throw new Error("Google 로그인을 위해 GOOGLE_OAUTH_CLIENT_ID를 설정하세요.");
}
if (apiBaseUrl && !/^https?:\/\/[^/]+/.test(apiBaseUrl)) {
  throw new Error("API_BASE_URL에는 http(s) 백엔드 주소를 입력하세요.");
}
if (authEnabled && !/^https:\/\/[^/]+/.test(apiBaseUrl)) {
  throw new Error("Firebase 인증이 활성화된 배포에서는 HTTPS API_BASE_URL이 필요합니다.");
}

const outputDirectory = path.join(__dirname, "dist");
fs.rmSync(outputDirectory, { recursive: true, force: true });
fs.mkdirSync(outputDirectory, { recursive: true });
for (const file of ["index.html", "script.js", "style.css"]) {
  fs.copyFileSync(path.join(__dirname, file), path.join(outputDirectory, file));
}
fs.writeFileSync(
  path.join(outputDirectory, "config.js"),
  `window.APP_CONFIG = ${JSON.stringify({ apiBaseUrl, firebaseApiKey, googleOAuthClientId, authEnabled, userId: "demo-user" })};\n`,
  "utf8",
);
