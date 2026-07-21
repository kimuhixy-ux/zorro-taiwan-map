"use strict";

const STAR_COLORS = { 3: "#ffc72c", 2: "#f7931e", 1: "#2b6cb0", unknown: "#9aa0a6" };
const STAR_SIZES = { 3: 32, 2: 24, 1: 24, unknown: 18 };

let allStores = [];
let starThreeLayer;
let clusterLayer;
let map;

// 表記ゆれ（魯肉飯／滷肉飯 など）をまとめて拾えるよう、
// 各料理につき複数のキーワードを持たせている
const DISH_PRESETS = [
  { label: "魯肉飯", keywords: ["魯肉飯", "滷肉飯", "ルーロー飯"] },
  { label: "牛肉麺", keywords: ["牛肉麺", "牛肉麵"] },
  { label: "小籠包", keywords: ["小籠包"] },
  { label: "鶏肉飯", keywords: ["鶏肉飯", "雞肉飯"] },
  { label: "豆花", keywords: ["豆花"] },
  { label: "水餃子", keywords: ["水餃", "餃子", "蒸餃"] },
  { label: "麺線", keywords: ["麺線"] },
  { label: "臭豆腐", keywords: ["臭豆腐"] },
  { label: "かき氷", keywords: ["かき氷"] },
  { label: "火鍋", keywords: ["火鍋"] },
  { label: "鵝肉・鴨肉飯", keywords: ["鵝肉", "鴨肉飯"] },
  { label: "胡椒餅", keywords: ["胡椒餅"] },
];

const state = {
  search: "",
  stars: new Set([3, 2, 1, "unknown"]),
  area: "all",
  genre: "all",
  dish: null,
};

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function classifyArea(address) {
  if (!address) return "その他";
  if (address.includes("台北") || address.includes("臺北")) return "台北";
  if (address.includes("新北")) return "新北";
  if (address.includes("台中") || address.includes("臺中")) return "台中";
  if (address.includes("台南") || address.includes("臺南")) return "台南";
  if (address.includes("高雄")) return "高雄";
  return "その他";
}

function starKey(stars) {
  return stars === 3 || stars === 2 || stars === 1 ? stars : "unknown";
}

function createIcon(stars) {
  const key = starKey(stars);
  const size = STAR_SIZES[key];
  const color = STAR_COLORS[key];
  const cls = key === "unknown" ? "unknown" : `star${key}`;
  return L.divIcon({
    className: `store-marker ${cls}`,
    html: `<div class="marker-dot" style="width:${size}px;height:${size}px;background:${color};"></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
}

function buildPopup(store) {
  const stars = store.stars;
  const starsDisplay =
    stars === 3 || stars === 2 || stars === 1
      ? "★".repeat(stars) + "☆".repeat(3 - stars)
      : "評価不明";

  const nameJa = store.name_ja
    ? `<div class="popup-name-ja">${escapeHtml(store.name_ja)}</div>`
    : "";

  const videos = store.videos || [];
  const videosHtml = videos
    .map((v, i) => {
      const label = videos.length > 1 ? `▶ 紹介動画を見る (${i + 1})` : "▶ 紹介動画を見る";
      return `<a class="popup-btn video-btn" href="${escapeHtml(v.video_url)}" target="_blank" rel="noopener">${label}</a>`;
    })
    .join("");

  const mapsQuery = store.address
    ? encodeURIComponent(store.address)
    : `${store.lat},${store.lng}`;
  const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${mapsQuery}`;

  return `
    <div class="popup">
      <div class="popup-title">${escapeHtml(store.name)}</div>
      ${nameJa}
      <div class="popup-stars">${starsDisplay}</div>
      ${store.genre ? `<div class="popup-row">🍽 ${escapeHtml(store.genre)}</div>` : ""}
      ${store.address ? `<div class="popup-row">📍 ${escapeHtml(store.address)}</div>` : ""}
      ${store.hours ? `<div class="popup-row">🕒 ${escapeHtml(store.hours)}</div>` : ""}
      <div class="popup-actions">
        ${videosHtml}
        <a class="popup-btn maps-btn" href="${mapsUrl}" target="_blank" rel="noopener">🗺 Google Mapsで開く</a>
      </div>
    </div>`;
}

function storeSearchableText(store) {
  return [store.name, store.name_ja, store.genre]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function matchesFilters(store) {
  if (!state.stars.has(starKey(store.stars))) return false;
  if (state.area !== "all" && classifyArea(store.address) !== state.area) return false;
  if (state.genre !== "all" && store.genre !== state.genre) return false;
  if (state.dish) {
    const text = storeSearchableText(store);
    if (!state.dish.keywords.some((kw) => text.includes(kw.toLowerCase()))) return false;
  }
  if (state.search) {
    if (!storeSearchableText(store).includes(state.search)) return false;
  }
  return true;
}

function renderMarkers() {
  starThreeLayer.clearLayers();
  clusterLayer.clearLayers();

  let visibleCount = 0;
  for (const store of allStores) {
    if (!matchesFilters(store)) continue;
    visibleCount++;

    const marker = L.marker([store.lat, store.lng], {
      icon: createIcon(store.stars),
      zIndexOffset: store.stars === 3 ? 1000 : 0,
    });
    marker.bindPopup(buildPopup(store));

    if (store.stars === 3) {
      starThreeLayer.addLayer(marker);
    } else {
      clusterLayer.addLayer(marker);
    }
  }

  const countEl = document.getElementById("filter-count");
  if (countEl) {
    countEl.textContent = `表示中: ${visibleCount}件 / 全${allStores.length}件`;
  }
}

function populateGenreOptions(stores) {
  const genres = new Set();
  for (const s of stores) {
    if (s.genre) genres.add(s.genre);
  }
  const select = document.getElementById("genre-filter");
  const sorted = Array.from(genres).sort((a, b) => a.localeCompare(b, "ja"));
  for (const g of sorted) {
    const opt = document.createElement("option");
    opt.value = g;
    opt.textContent = g;
    select.appendChild(opt);
  }
}

function setupFilterUI() {
  const filterToggle = document.getElementById("filter-toggle");
  const filterPanel = document.getElementById("filter-panel");
  filterToggle.addEventListener("click", () => {
    const isHidden = filterPanel.hidden;
    filterPanel.hidden = !isHidden;
    filterToggle.setAttribute("aria-expanded", String(isHidden));
  });

  const searchInput = document.getElementById("search-input");
  searchInput.addEventListener("input", () => {
    state.search = searchInput.value.trim().toLowerCase();
    if (state.search) clearDishSelection();
    renderMarkers();
  });

  const starsFilter = document.getElementById("stars-filter");
  starsFilter.addEventListener("change", () => {
    const checked = starsFilter.querySelectorAll("input[type=checkbox]:checked");
    state.stars = new Set(
      Array.from(checked).map((el) => (el.value === "null" ? "unknown" : Number(el.value)))
    );
    syncStar3ToggleButton();
    renderMarkers();
  });

  const areaFilter = document.getElementById("area-filter");
  areaFilter.addEventListener("change", () => {
    state.area = areaFilter.value;
    renderMarkers();
  });

  const genreFilter = document.getElementById("genre-filter");
  genreFilter.addEventListener("change", () => {
    state.genre = genreFilter.value;
    renderMarkers();
  });

  document.getElementById("filter-reset").addEventListener("click", () => {
    searchInput.value = "";
    areaFilter.value = "all";
    genreFilter.value = "all";
    starsFilter.querySelectorAll("input[type=checkbox]").forEach((el) => (el.checked = true));
    state.search = "";
    state.area = "all";
    state.genre = "all";
    state.stars = new Set([3, 2, 1, "unknown"]);
    clearDishSelection();
    syncStar3ToggleButton();
    renderMarkers();
  });
}

function clearDishSelection() {
  state.dish = null;
  const container = document.getElementById("dish-filter");
  container.querySelectorAll(".chip-btn").forEach((el) => el.classList.remove("active"));
}

function setupDishButtons() {
  const container = document.getElementById("dish-filter");
  for (const preset of DISH_PRESETS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-btn";
    btn.textContent = preset.label;
    btn.addEventListener("click", () => {
      const isActive = btn.classList.contains("active");
      const searchInput = document.getElementById("search-input");
      searchInput.value = "";
      state.search = "";
      clearDishSelection();
      if (!isActive) {
        state.dish = preset;
        btn.classList.add("active");
      }
      renderMarkers();
    });
    container.appendChild(btn);
  }
}

function syncStar3ToggleButton() {
  const btn = document.getElementById("star3-toggle");
  const isStar3Only = state.stars.size === 1 && state.stars.has(3);
  btn.setAttribute("aria-pressed", String(isStar3Only));
}

function setupStar3Toggle() {
  const btn = document.getElementById("star3-toggle");
  btn.addEventListener("click", () => {
    const starsFilter = document.getElementById("stars-filter");
    const checkboxes = starsFilter.querySelectorAll("input[type=checkbox]");
    const isStar3Only = state.stars.size === 1 && state.stars.has(3);

    if (isStar3Only) {
      // 全解除して元に戻す
      checkboxes.forEach((el) => (el.checked = true));
      state.stars = new Set([3, 2, 1, "unknown"]);
    } else {
      checkboxes.forEach((el) => (el.checked = el.value === "3"));
      state.stars = new Set([3]);
    }
    syncStar3ToggleButton();
    renderMarkers();
  });
}

async function loadStores() {
  const res = await fetch("data/stores.json", { cache: "no-cache" });
  if (!res.ok) throw new Error("stores.json の読み込みに失敗しました");
  const data = await res.json();
  return data.filter((s) => typeof s.lat === "number" && typeof s.lng === "number");
}

function initMap() {
  map = L.map("map", { zoomControl: false });
  L.control.zoom({ position: "bottomright" }).addTo(map);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  starThreeLayer = L.layerGroup().addTo(map);
  clusterLayer = L.markerClusterGroup({
    disableClusteringAtZoom: 17,
    maxClusterRadius: 50,
  }).addTo(map);

  // 台湾全体が収まる初期ビュー（台北中心）
  map.setView([23.9, 121.0], 8);
}

async function main() {
  initMap();
  setupFilterUI();
  setupStar3Toggle();
  setupDishButtons();

  try {
    allStores = await loadStores();
  } catch (e) {
    console.error(e);
    allStores = [];
  }

  populateGenreOptions(allStores);
  renderMarkers();

  if (allStores.length > 0) {
    const bounds = L.latLngBounds(allStores.map((s) => [s.lat, s.lng]));
    map.fitBounds(bounds, { padding: [20, 20], maxZoom: 12 });
  }
}

main();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch((e) => console.error("SW登録失敗:", e));
  });
}
