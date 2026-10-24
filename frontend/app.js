"use strict";

const API = location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";
const GATES = ["entry", "exit"];
const GATE_NAMES = { entry: "Entry gate", exit: "Exit gate" };
const PAGES = ["overview", "activity", "vehicles", "settings"];

const CAMERA_STATES = {
    idle: "Camera off",
    stopped: "Camera off",
    running: "Watching",
    reconnecting: "Reconnecting…",
    finished: "Video finished",
};

const DETECTOR_LABELS = {
    simulated: "Demo (makes up plates)",
    yolo11: "Camera AI: YOLO11 (recommended)",
    rtdetr: "Camera AI: RT-DETR (slower)",
};

const FORECAST_LABELS = {
    baseline: "Typical daily pattern (recommended)",
    lstm: "Neural network (LSTM)",
};

const REJECT_REASONS = {
    STOLEN: "Reported stolen",
    UNAUTHORIZED: "Blocked from parking here",
    UNKNOWN: "Not a registered vehicle",
};

const SOURCE_LABELS = { manual: "recorded by hand", simulated: "demo reading", camera: "seen by camera" };

const ALERT_KIND_LABELS = {
    stolen: "stolen vehicles",
    unauthorized: "blocked vehicles",
    unknown: "unregistered vehicles",
    full: "lot full",
    unmatched: "exits with no entry",
};

const state = {
    summary: null,
    version: null,
    page: "overview",
    filter: "",
    search: "",
    day: "",
    pageSize: 50,
    shown: 50,
    seenEvents: new Set(),
    firstEventLoad: true,
    videos: [],
    history: null,
    cameras: null,
    online: null,
    signedOut: false,
};

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
        if (value === undefined || value === null || value === false) continue;
        if (key === "class") node.className = value;
        else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
        else if (key in node) node[key] = value;
        else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
}

const plate = (text) => el("span", { class: "plate" }, text);

async function api(path, { method = "GET", body } = {}) {
    let response;
    try {
        response = await fetch(API + path, {
            method,
            headers: body ? { "Content-Type": "application/json" } : undefined,
            body: body ? JSON.stringify(body) : undefined,
        });
    } catch (error) {
        setOnline(false);
        throw new Error("Can't reach the server.");
    }
    setOnline(true);

    if (response.status === 401 && !path.startsWith("/auth/")) {
        showLogin();
        throw new Error("Please sign in.");
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = Array.isArray(data.detail)
            ? data.detail.map((item) => item.msg).join("; ")
            : data.detail;
        throw new Error(detail || `Something went wrong (${response.status}).`);
    }
    return data;
}

let toastTimer = null;

function say(message, tone = "") {
    const toast = $("toast");
    toast.textContent = message;
    toast.className = "toast" + (tone ? " " + tone : "");
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, tone === "error" ? 8000 : 5000);
}

function setOnline(online) {
    if (state.online === online) return;
    state.online = online;
    $("offlineBanner").hidden = online;
    const connection = $("connection");
    connection.textContent = online ? "Online" : "Offline";
    connection.className = "connection " + (online ? "ok" : "bad");
}

function clockTime(iso) {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function timeAgo(iso) {
    if (!iso) return "";
    const seconds = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
    if (seconds < 45) return "just now";
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} h ago`;
    return new Date(iso).toLocaleDateString([], { day: "numeric", month: "short" });
}

function eventTime(iso) {
    const date = new Date(iso);
    const today = new Date().toDateString() === date.toDateString();
    return today
        ? clockTime(iso)
        : `${date.toLocaleDateString([], { day: "numeric", month: "short" })}, ${clockTime(iso)}`;
}

function parkedFor(iso) {
    if (!iso) return "";
    const minutes = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (minutes < 1) return "just arrived";
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours} h ${minutes % 60} min`;
    return `${Math.floor(hours / 24)} days`;
}

function normalizePlate(text) {
    return text.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function localToday() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function showPage(name) {
    if (!PAGES.includes(name)) name = "overview";
    state.page = name;
    for (const page of document.querySelectorAll(".page")) {
        page.hidden = page.dataset.page !== name;
    }
    for (const tab of document.querySelectorAll(".tabs a")) {
        if (tab.dataset.tab === name) tab.setAttribute("aria-current", "page");
        else tab.removeAttribute("aria-current");
    }
    document.title = name === "overview"
        ? "Smart Parking"
        : `${name[0].toUpperCase() + name.slice(1)} · Smart Parking`;
    if (name === "overview") drawChart();
    renderCameras();
}

function renderCameras() {
    if (state.cameras) for (const gate of GATES) renderCamera(gate, state.cameras[gate]);
}

window.addEventListener("hashchange", () => showPage(location.hash.slice(1)));

function setPresenting(on) {
    document.body.classList.toggle("presenting", on);
    if (on) {
        if (state.page !== "overview") location.hash = "overview";
        drawChart();
        document.documentElement.requestFullscreen?.().catch(() => {});
    } else if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
    }
    setTimeout(drawChart, 200);
}

$("presentButton").addEventListener("click", () => setPresenting(true));
$("exitPresent").addEventListener("click", () => setPresenting(false));
document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && document.body.classList.contains("presenting")) setPresenting(false);
});
document.addEventListener("keydown", (event) => {
    const typing = event.target.closest("input, select, textarea");
    if (event.key === "Escape" && document.body.classList.contains("presenting")) setPresenting(false);
    if (!typing && !event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === "p"
        && $("loginScreen").hidden) {
        setPresenting(!document.body.classList.contains("presenting"));
    }
});

function renderSummary(summary) {
    state.summary = summary;
    const parking = summary.parking;
    const forecast = summary.forecast;
    const security = summary.security;

    $("kpiFree").textContent = parking.available;
    $("kpiCapacity").textContent = parking.total_slots;
    $("kpiOccupied").textContent = parking.occupied;

    const rate = parking.occupancy_rate;
    $("meterFill").style.width = `${Math.min(100, rate)}%`;
    $("sign").className = "card sign" + (rate >= 100 ? " full" : rate >= 75 ? " filling" : "");
    $("heroStatus").textContent =
        parking.total_slots === 0 ? "No spaces set up yet"
        : rate >= 100 ? "Lot full"
        : rate >= 90 ? "Almost full"
        : rate >= 75 ? "Filling up"
        : "Plenty of space";

    $("kpiForecast").textContent = Math.round(forecast.predicted_occupancy);
    $("kpiForecastRange").textContent = Math.round(forecast.low) === Math.round(forecast.high)
        ? "cars inside"
        : `cars, likely ${Math.round(forecast.low)} to ${Math.round(forecast.high)}`;

    $("kpiRejected").textContent = security.rejected_today;
    $("kpiRejected").className = security.rejected_today ? "bad" : "";

    const capacityInput = $("capacityInput");
    if (document.activeElement !== capacityInput) capacityInput.value = parking.total_slots;

    renderBays(parking);
}

function renderBays(parking) {
    if (!parking.slots.length) {
        $("bays").replaceChildren(el("li", { class: "empty" }, "Set the number of spaces in Settings."));
        return;
    }
    $("bays").replaceChildren(...parking.slots.map((slot) => {
        if (slot.status !== "occupied") {
            return el("li", { class: "bay" },
                el("span", { class: "bay-id" }, slot.slot_id),
                el("span", { class: "bay-free" }, "Free"),
            );
        }
        const checkOut = () => {
            if (document.body.classList.contains("presenting")) return;
            logManual(slot.plate_number, "exit", `Mark ${slot.plate_number} as gone from ${slot.slot_id}?`);
        };
        return el("li", {
            class: "bay taken",
            tabIndex: 0,
            title: `Arrived at ${clockTime(slot.entered_at)}. Click to mark as gone.`,
            onclick: checkOut,
            onkeydown: (event) => { if (event.key === "Enter") checkOut(); },
        },
            el("span", { class: "bay-id" }, slot.slot_id),
            plate(slot.plate_number),
            el("span", { class: "bay-time" }, parkedFor(slot.entered_at)),
        );
    }));
}

async function loadSummary() {
    try {
        onSummary(await api("/dashboard/summary"));
    } catch (error) {}
}

function onSummary(summary) {
    const changed = summary.version !== state.version;
    state.version = summary.version;
    renderSummary(summary);
    if (changed) {
        loadLatest();
        loadEvents();
        loadVehicles();
        loadChart();
        loadReport();
        loadSystem();
    }
}

function describe(event) {
    const where = GATE_NAMES[event.gate] || "Gate";
    switch (event.status) {
        case "entered":
            return {
                tone: "green",
                what: "Came in",
                detail: `${event.security_status === "UNKNOWN" ? "Visitor · " : ""}Parked in ${event.slot_id}`,
            };
        case "exited":
            return { tone: "blue", what: "Left", detail: event.slot_id ? `${event.slot_id} is free again` : "Space freed" };
        case "entry_rejected":
            return { tone: "red", what: "Turned away", detail: REJECT_REASONS[event.security_status] || "Access denied" };
        case "capacity_full":
            return { tone: "amber", what: "Turned away", detail: "The lot was full" };
        case "unmatched_exit":
            return { tone: "amber", what: "Left", detail: "Never seen coming in. Check the entry camera" };
        case "already_parked":
            return { tone: "grey", what: "Seen again", detail: "Already inside, nothing changed" };
        default:
            return { tone: "grey", what: event.status, detail: where };
    }
}

const outcome = (info) => el("span", { class: `outcome ${info.tone}` }, info.what);

async function loadLatest() {
    let events;
    try {
        ({ events } = await api("/events?limit=6"));
    } catch (error) {
        return;
    }
    $("latest").replaceChildren(...(events.length ? events.map((event) => {
        const info = describe(event);
        return el("li", {},
            plate(event.plate_number),
            el("div", {},
                el("div", {}, outcome(info)),
                el("div", { class: "where" }, `${GATE_NAMES[event.gate]} · ${info.detail}`),
            ),
            el("time", { dateTime: event.timestamp, title: new Date(event.timestamp).toLocaleString() },
                timeAgo(event.timestamp)),
        );
    }) : [el("li", { class: "empty" }, "Nothing yet. Press Try a reading on a gate camera, or record a car by hand.")]));
}

function eventQuery() {
    const params = new URLSearchParams();
    if (state.filter === "entry" || state.filter === "exit") params.set("gate", state.filter);
    if (state.filter === "problems") params.set("status", "problems");
    if (state.search) params.set("plate", state.search);
    if (state.day) {
        params.set("since", state.day);
        params.set("until", state.day);
    }
    return params;
}

async function loadEvents() {
    const filter = state.filter;
    const params = eventQuery();
    $("exportLink").href = `${API}/events.csv?${params}`;
    params.set("limit", state.shown);

    let events, total;
    try {
        ({ events, total } = await api(`/events?${params}`));
    } catch (error) {
        return;
    }

    const filtered = state.search || state.day || filter;
    $("feedCount").textContent = total
        ? `Showing ${events.length} of ${total} ${filtered ? "matching " : ""}event${total === 1 ? "" : "s"}`
        : "";
    $("loadMore").hidden = events.length >= total;
    $("clearSearch").hidden = !(state.search || state.day);

    const rows = events.map((event) => {
        const key = event.timestamp + event.plate_number + event.gate;
        const fresh = !state.firstEventLoad && !state.seenEvents.has(key);
        state.seenEvents.add(key);

        const info = describe(event);
        const source = SOURCE_LABELS[event.source];
        return el("tr", { class: fresh ? "fresh" : "" },
            el("td", { class: "time", title: new Date(event.timestamp).toLocaleString() }, eventTime(event.timestamp)),
            el("td", {}, plate(event.plate_number)),
            el("td", {}, outcome(info)),
            el("td", { class: "detail" }, `${GATE_NAMES[event.gate]} · ${info.detail}${source ? ` · ${source}` : ""}`),
        );
    });
    state.firstEventLoad = false;

    const emptyText = state.search || state.day
        ? "No events match this search."
        : filter === "problems"
            ? "No problems. Every car was handled normally."
            : "Nothing yet. Press Try a reading on a gate camera, or record a car by hand.";
    $("feed").replaceChildren(...(rows.length ? rows
        : [el("tr", {}, el("td", { colSpan: 4 }, el("p", { class: "empty" }, emptyText)))]));
}

function resetFeed() {
    state.shown = state.pageSize;
    state.firstEventLoad = true;
    loadEvents();
}

$("eventFilter").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.filter = button.dataset.filter;
    for (const other of $("eventFilter").querySelectorAll("button")) {
        other.setAttribute("aria-pressed", String(other === button));
    }
    resetFeed();
});

let searchTimer = null;
$("searchPlate").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
        state.search = normalizePlate($("searchPlate").value);
        resetFeed();
    }, 250);
});

$("searchDay").addEventListener("change", () => {
    state.day = $("searchDay").value;
    resetFeed();
});

$("searchForm").addEventListener("submit", (event) => event.preventDefault());

$("clearSearch").addEventListener("click", () => {
    $("searchPlate").value = "";
    $("searchDay").value = "";
    state.search = "";
    state.day = "";
    resetFeed();
});

$("loadMore").addEventListener("click", () => {
    state.shown += state.pageSize;
    loadEvents();
});

async function logManual(plateNumber, direction, confirmText) {
    if (confirmText && !confirm(confirmText)) return;
    try {
        const event = await api("/parking/manual", {
            method: "POST",
            body: { plate_number: plateNumber, direction },
        });
        const info = describe(event);
        say(`${event.plate_number}: ${info.what.toLowerCase()}. ${info.detail}.`, event.gate_open ? "ok" : "error");
        await loadSummary();
    } catch (error) {
        say(error.message, "error");
    }
}

$("manualForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("manualPlate");
    const plateNumber = normalizePlate(input.value);
    if (!plateNumber) return;
    await logManual(plateNumber, event.submitter.value);
    input.value = "";
    input.focus();
});

function cameraRoot(gate) {
    return document.querySelector(`.camera[data-gate="${gate}"]`);
}

function setupCameras() {
    const template = $("cameraTemplate");
    for (const gate of GATES) {
        const root = cameraRoot(gate);
        root.append(template.content.cloneNode(true));
        root.querySelector(".camera-title").textContent = GATE_NAMES[gate];
        root.querySelector(".barrier-name").textContent = "Barrier";

        const select = root.querySelector(".source-select");
        const input = root.querySelector(".source-input");
        select.addEventListener("change", () => {
            select.dataset.touched = "1";
            input.hidden = select.value !== "custom";
            if (!input.hidden) input.focus();
        });

        root.querySelector(".camera-form").addEventListener("submit", (event) => {
            event.preventDefault();
            const source = select.value === "custom" ? input.value.trim() : select.value;
            if (!source) return say("Type a webcam number, video file path or camera address.", "error");
            startCamera(gate, source, Number(root.querySelector(".fps-input").value) || 2);
        });
        root.querySelector(".stop").addEventListener("click", () => stopCamera(gate));
        root.querySelector(".read").addEventListener("click", () => readNow(gate));
        root.querySelector(".open-barrier").addEventListener("click", (event) => openBarrier(gate, event.currentTarget));
    }
    fillSourceSelects();
}

function fillSourceSelects() {
    for (const gate of GATES) {
        const root = cameraRoot(gate);
        const select = root.querySelector(".source-select");
        const previous = select.value;
        const preferred = state.videos.find((video) => video.gate === gate);

        select.replaceChildren(
            el("option", { value: "0" }, "Webcam on this computer"),
            state.videos.length
                ? el("optgroup", { label: "Demo clips" },
                    ...state.videos.map((video) => el("option", { value: video.path }, video.label || video.filename)))
                : null,
            el("option", { value: "custom" }, "Other: file path or camera address…"),
        );
        const keep = select.dataset.touched && [...select.options].some((o) => o.value === previous);
        select.value = keep ? previous : (preferred ? preferred.path : "0");
        root.querySelector(".source-input").hidden = select.value !== "custom";
    }
}

async function loadVideos() {
    try {
        ({ videos: state.videos } = await api("/camera/test-videos"));
        fillSourceSelects();
    } catch (error) {}
}

async function startCamera(gate, source, fps) {
    say(`Starting the ${GATE_NAMES[gate].toLowerCase()} camera…`);
    try {
        await api(`/camera/${gate}/start`, { method: "POST", body: { source, fps } });
        say(`${GATE_NAMES[gate]} camera is watching.`, "ok");
        await loadCameras();
    } catch (error) {
        say(error.message, "error");
    }
}

async function stopCamera(gate) {
    try {
        await api(`/camera/${gate}/stop`, { method: "POST" });
        say(`${GATE_NAMES[gate]} camera turned off.`);
        await loadCameras();
    } catch (error) {
        say(error.message, "error");
    }
}

async function readNow(gate) {
    try {
        const result = await api(`/camera/${gate}/process`, { method: "POST" });
        const plates = result.plates.map((item) => item.plate_text);
        if (!plates.length) say(`${GATE_NAMES[gate]}: no number plate found in this frame.`);
        else if (!result.events.length) say(`${GATE_NAMES[gate]} read ${plates.join(", ")}. It was just recorded, so nothing changed.`);
        else {
            const info = describe(result.events[0]);
            say(`${GATE_NAMES[gate]} read ${plates.join(", ")}: ${info.what.toLowerCase()}. ${info.detail}.`,
                result.events[0].gate_open ? "ok" : "error");
        }
        await loadSummary();
        await loadCameras();
    } catch (error) {
        say(error.message, "error");
    }
}

async function openBarrier(gate, button) {
    button.disabled = true;
    try {
        const record = await api(`/barrier/${gate}/open`, { method: "POST", body: { reason: "manual" } });
        say(`${GATE_NAMES[gate]} barrier: ${record.result}.`, record.result.startsWith("failed") ? "error" : "ok");
        await loadSystem();
    } catch (error) {
        say(error.message, "error");
    }
    button.disabled = false;
}

async function loadCameras() {
    try {
        state.cameras = await api("/camera/");
    } catch (error) {
        return;
    }
    renderCameras();
}

function renderCamera(gate, status) {
    const root = cameraRoot(gate);
    const label = CAMERA_STATES[status.state] || status.state;
    const badge = root.querySelector(".camera-state");
    badge.textContent = label;
    badge.className = `camera-state ${status.state}`;
    root.querySelector(".stop").disabled = !status.running;

    const select = root.querySelector(".source-select");
    const input = root.querySelector(".source-input");
    if (status.running && status.source && document.activeElement !== select && document.activeElement !== input) {
        const known = [...select.options].some((option) => option.value === status.source);
        select.value = known ? status.source : "custom";
        if (!known) input.value = status.source;
        input.hidden = known;
        select.dataset.touched = "1";
    }

    // Camera streams only download while the Overview (where the gates are) is open.
    const visible = state.page === "overview";
    const img = root.querySelector(".preview img");
    const wanted = !visible ? ""
        : status.running
            ? `${API}/camera/${gate}/stream?since=${encodeURIComponent(status.started_at)}`
            : status.has_preview
                ? `${API}/camera/${gate}/snapshot.jpg?at=${encodeURIComponent(status.last_processed_at || status.started_at)}`
                : "";
    if (img.dataset.src !== wanted) {
        img.dataset.src = wanted;
        if (wanted) img.src = wanted; else img.removeAttribute("src");
    }
    img.hidden = !wanted;
    img.alt = `${GATE_NAMES[gate]} camera view`;
    root.querySelector(".preview-empty").hidden = Boolean(wanted);

    const parts = [];
    if (status.note) parts.push(status.note);
    if (state.paperPlates && status.running) parts.push("reading plates on paper");
    if (status.frames_processed) parts.push(`${status.frames_processed} frames checked`);
    if (status.last_plates.length) parts.push(`last plate ${status.last_plates.join(", ")}`);
    if (status.error) parts.push(status.error);
    const meta = root.querySelector(".camera-meta");
    meta.textContent = parts.join(" · ");
    meta.classList.toggle("error", Boolean(status.error));

}

async function loadVehicles() {
    let vehicles;
    try {
        ({ vehicles } = await api("/vehicles/"));
    } catch (error) {
        return;
    }
    $("vehicleCount").textContent = `${vehicles.length} vehicle${vehicles.length === 1 ? "" : "s"}`;

    $("vehicleRows").replaceChildren(...(vehicles.length ? vehicles.map((vehicle) => {
        const status = vehicle.stolen
            ? el("span", { class: "status stolen" }, "Stolen")
            : vehicle.authorized
                ? el("span", { class: "status allowed" }, "Allowed")
                : el("span", { class: "status denied" }, "Blocked");
        const plateNumber = vehicle.plate_number;
        const type = { motorcycle: "Motorbike" }[vehicle.vehicle_type]
            || (vehicle.vehicle_type ? vehicle.vehicle_type[0].toUpperCase() + vehicle.vehicle_type.slice(1) : "Vehicle");

        return el("tr", {},
            el("td", {}, plate(plateNumber)),
            el("td", {}, vehicle.owner_name || el("span", { class: "hint" }, "Not given")),
            el("td", {}, type),
            el("td", {}, status),
            el("td", {}, vehicle.inside ? "Yes" : el("span", { class: "hint" }, "No")),
            el("td", { class: "actions" },
                el("button", { type: "button", class: "btn-text", onclick: () => flagVehicle(plateNumber, { authorized: !vehicle.authorized }) },
                    vehicle.authorized ? "Block" : "Allow"),
                el("button", { type: "button", class: "btn-text", onclick: () => flagVehicle(plateNumber, { stolen: !vehicle.stolen }) },
                    vehicle.stolen ? "Mark found" : "Report stolen"),
                el("button", { type: "button", class: "btn-text danger", onclick: () => removeVehicle(plateNumber) }, "Remove"),
            ),
        );
    }) : [el("tr", {}, el("td", { colSpan: 6 }, el("p", { class: "empty" }, "No vehicles yet. Add one above.")))]));
}

async function flagVehicle(plateNumber, flags) {
    try {
        await api(`/vehicles/${encodeURIComponent(plateNumber)}/flag`, { method: "POST", body: flags });
        await loadSummary();
        await loadVehicles();
    } catch (error) {
        say(error.message, "error");
    }
}

async function removeVehicle(plateNumber) {
    if (!confirm(`Remove ${plateNumber} from registered vehicles?`)) return;
    try {
        await api(`/vehicles/${encodeURIComponent(plateNumber)}`, { method: "DELETE" });
        say(`${plateNumber} removed.`);
        await loadSummary();
        await loadVehicles();
    } catch (error) {
        say(error.message, "error");
    }
}

$("registerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const plateNumber = normalizePlate($("regPlate").value);
    if (!plateNumber) return;
    try {
        const result = await api("/vehicles/register", {
            method: "POST",
            body: {
                plate_number: plateNumber,
                owner_name: $("regOwner").value.trim(),
                vehicle_type: $("regType").value,
                authorized: $("regAuthorized").checked,
            },
        });
        say(`${result.plate_number} added.` + (result.valid_format ? "" : " It doesn't look like a standard Indian plate, so double-check it."),
            result.valid_format ? "ok" : "");
        event.target.reset();
        $("regAuthorized").checked = true;
        await loadSummary();
        await loadVehicles();
    } catch (error) {
        say(error.message, "error");
    }
});

async function loadChart() {
    try {
        ({ history: state.history } = await api("/dashboard/occupancy-history?limit=2000"));
    } catch (error) {
        return;
    }
    drawChart();
}

function drawChart() {
    const container = $("chart");
    const summary = state.summary;
    if (!container.clientWidth) return;
    const now = Date.now();
    const start = now - 24 * 3600 * 1000;
    const end = now + 75 * 60 * 1000;
    const points = (state.history || [])
        .map((item) => [new Date(item.timestamp).getTime(), item.occupied])
        .filter(([time]) => time >= start - 3600 * 1000);

    if (!points.length || !summary) {
        container.replaceChildren(el("p", { class: "empty" }, "The chart fills in as cars come and go."));
        return;
    }

    const capacity = summary.parking.total_slots;
    const forecast = summary.forecast;
    const presenting = document.body.classList.contains("presenting");
    const maxY = Math.max(1, capacity, forecast.high, ...points.map(([, value]) => value));
    const width = Math.max(300, container.clientWidth), height = presenting ? 220 : 240;
    const left = 30, right = 14, top = 12, bottom = 28;
    const x = (time) => left + ((Math.max(time, start) - start) / (end - start)) * (width - left - right);
    const y = (value) => top + (1 - value / maxY) * (height - top - bottom);

    let path = "";
    points.forEach(([time, value], index) => {
        path += index === 0 ? `M${x(time)},${y(value)}` : `H${x(time)}V${y(value)}`;
    });
    path += `H${x(now)}`;
    const area = `${path}V${y(0)}H${x(points[0][0])}Z`;

    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", `Cars inside over the last 24 hours. About ${Math.round(forecast.predicted_occupancy)} expected in one hour.`);
    const add = (tag, attrs, text) => {
        const node = document.createElementNS(ns, tag);
        for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
        if (text !== undefined) node.textContent = text;
        svg.append(node);
        return node;
    };

    const step = maxY <= 10 ? 1 : Math.ceil(maxY / 5);
    for (let value = 0; value <= maxY; value += step) {
        add("line", { class: "grid", x1: left, x2: width - right, y1: y(value), y2: y(value) });
        add("text", { x: left - 8, y: y(value) + 4, "text-anchor": "end" }, value);
    }
    const hourStep = width < 600 ? 6 : 3;
    for (let hour = 0; hour < 24; hour += hourStep) {
        const time = start + hour * 3600 * 1000;
        add("text", { x: x(time), y: height - 8, "text-anchor": "middle" },
            new Date(time).toLocaleTimeString([], { hour: "numeric" }));
    }
    add("text", { x: x(now), y: height - 8, "text-anchor": "middle" }, "now");

    add("line", { class: "capacity", x1: left, x2: width - right, y1: y(capacity), y2: y(capacity) });
    add("path", { class: "area", d: area });
    add("path", { class: "series", d: path });
    add("line", { class: "now", x1: x(now), x2: x(now), y1: top, y2: height - bottom });

    const fx = x(now + forecast.horizon_minutes * 60000);
    add("line", { class: "forecast", x1: fx, x2: fx, y1: y(forecast.low), y2: y(forecast.high) });
    add("circle", { class: "forecast-dot", cx: fx, cy: y(forecast.predicted_occupancy), r: 5 });

    container.replaceChildren(svg);
}

let resizeTimer = null;
window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawChart, 150);
});

async function loadModels() {
    try {
        const models = await api("/models/");
        const fill = (select, options, current, labels) => {
            select.replaceChildren(...options.map((value) => el("option", { value }, labels[value] || value)));
            select.value = current;
        };
        fill($("detectorSelect"), models.available.vehicle_detection, models.vehicle_detection, DETECTOR_LABELS);
        fill($("forecastSelect"), models.available.parking_prediction, models.parking_prediction, FORECAST_LABELS);
    } catch (error) {}
}

async function switchModel(kind, select) {
    const value = select.value;
    select.disabled = true;
    say(kind === "vehicle" ? "Loading the camera AI. This can take a few seconds…" : "Switching prediction method…");
    try {
        await api(`/models/${kind}/${value}`, { method: "POST" });
        say("Saved.", "ok");
    } catch (error) {
        say(error.message, "error");
    }
    select.disabled = false;
    await loadModels();
    await loadCameras();
    await loadSummary();
}

$("detectorSelect").addEventListener("change", (event) => switchModel("vehicle", event.target));
$("forecastSelect").addEventListener("change", (event) => switchModel("prediction", event.target));

$("capacityForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const result = await api("/parking/capacity", {
            method: "POST",
            body: { capacity: Number($("capacityInput").value) },
        });
        say(`The lot now has ${result.total_slots} spaces.`, "ok");
        $("capacityInput").blur();
        await loadSummary();
    } catch (error) {
        say(error.message, "error");
    }
});

$("trainButton").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    say("Learning from the recorded history…");
    try {
        const result = await api("/dashboard/prediction/train", { method: "POST", body: { epochs: 200 } });
        say(`Prediction updated using ${result.samples} past readings.`, "ok");
        await loadSummary();
    } catch (error) {
        say(error.message, "error");
    }
    button.disabled = false;
});

$("cooldownForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
        const settings = await api("/settings", {
            method: "POST",
            body: { event_cooldown_seconds: Number($("cooldownInput").value) },
        });
        say(`Repeat readings within ${settings.event_cooldown_seconds} seconds are now ignored.`, "ok");
        $("cooldownInput").blur();
    } catch (error) {
        say(error.message, "error");
    }
});

async function saveSetting(select, body, message) {
    select.disabled = true;
    try {
        await api("/settings", { method: "POST", body });
        say(message, "ok");
    } catch (error) {
        say(error.message, "error");
        await loadSystem();
    }
    select.disabled = false;
}

$("visitorSelect").addEventListener("change", (event) => {
    const admit = event.target.value === "yes";
    saveSetting(event.target, { admit_visitors: admit },
        admit ? "Cars not in the list now get a space as visitors." : "Cars not in the list are now turned away.");
});

$("paperSelect").addEventListener("change", async (event) => {
    const paper = event.target.value === "yes";
    await saveSetting(event.target, { paper_plates: paper },
        paper ? "Gate cameras now read plates written on paper, with no car in view." : "Gate cameras now only read real plates on cars.");
    await loadSystem();
});

$("regionSelect").addEventListener("change", (event) => {
    const region = event.target.value;
    saveSetting(event.target, { plate_region: region },
        region === "ANY" ? "Any plate format is now accepted." : "Only Indian plates are now accepted.");
});

function applyTheme(theme) {
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    else document.documentElement.removeAttribute("data-theme");
    $("themeSelect").value = ["light", "dark"].includes(theme) ? theme : "auto";
    setTimeout(drawChart, 0);
}

$("themeSelect").addEventListener("change", (event) => {
    try { localStorage.setItem("theme", event.target.value); } catch (error) {}
    applyTheme(event.target.value);
});

try { applyTheme(localStorage.getItem("theme") || "auto"); } catch (error) { applyTheme("auto"); }

function formatStay(minutes) {
    if (minutes === null || minutes === undefined) return "–";
    if (minutes < 60) return `${minutes} min`;
    return `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

async function loadReport() {
    let report;
    try {
        report = await api("/reports/daily?days=7");
    } catch (error) {
        return;
    }

    // Local date: the server groups days by local time, not UTC.
    const today = localToday();
    const todayRow = report.days.find((day) => day.date === today);
    $("kpiIn").textContent = todayRow ? todayRow.entries : 0;

    const cell = (value, badWhenPositive = false) =>
        el("td", { class: "num " + (value ? (badWhenPositive ? "bad" : "") : "zero") }, value);

    $("reportRows").replaceChildren(...report.days.slice().reverse().map((day) => {
        const date = new Date(`${day.date}T12:00:00`);
        const label = day.date === today
            ? "Today"
            : date.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
        const busiest = day.peak_occupancy
            ? `${day.peak_occupancy} car${day.peak_occupancy === 1 ? "" : "s"} at ${clockTime(day.peak_at)}`
            : "–";
        return el("tr", { class: day.date === today ? "today" : "" },
            el("td", {}, label),
            cell(day.entries),
            cell(day.exits),
            cell(day.turned_away, true),
            el("td", {}, busiest),
            el("td", {}, formatStay(day.average_stay_minutes)),
        );
    }));

    const totals = report.totals;
    $("reportTotals").textContent =
        `${totals.entries} came in · ${totals.exits} went out · ${totals.turned_away} turned away`;
}

async function loadSystem() {
    let settings;
    try {
        settings = await api("/settings");
    } catch (error) {
        return;
    }

    const cooldown = $("cooldownInput");
    if (document.activeElement !== cooldown) cooldown.value = settings.event_cooldown_seconds;
    $("visitorSelect").value = settings.admit_visitors ? "yes" : "no";
    $("regionSelect").value = settings.plate_region === "ANY" ? "ANY" : "IN";
    $("paperSelect").value = settings.paper_plates ? "yes" : "no";
    if (state.paperPlates !== settings.paper_plates) {
        state.paperPlates = settings.paper_plates;
        renderCameras();
    }

    const barrier = settings.barrier;
    for (const gate of GATES) {
        const last = barrier.last[gate];
        const line = cameraRoot(gate).querySelector(".barrier-last");
        line.textContent = last
            ? `Opened ${timeAgo(last.requested_at)}${last.plate_number ? ` for ${last.plate_number}` : ""} · ${last.result}`
            : "Not opened yet";
        line.classList.toggle("error", Boolean(last && last.result.startsWith("failed")));
    }
    $("barrierMode").textContent = barrier.mode === "simulated"
        ? "Barriers are in demo mode: no hardware is connected, so opening is only recorded. Set BARRIER_MODE=http to drive the relays."
        : `Barriers are connected to relay hardware and stay open for ${barrier.open_ms / 1000} s${barrier.auto_open ? ". They open automatically when a car is let in" : ""}.`;

    const alerts = settings.alerts;
    const kinds = alerts.enabled.map((kind) => ALERT_KIND_LABELS[kind] || kind).join(", ") || "nothing";
    $("alertChannels").textContent = alerts.channels.length
        ? `Sent to ${alerts.channels.join(" and ")} for ${kinds}.`
        : `Alerts only show below. Set ALERT_WEBHOOK_URL or the email settings to get them on your phone. Watching for ${kinds}.`;
    $("testAlert").disabled = !alerts.channels.length;

    $("alertList").replaceChildren(...alerts.recent.slice(0, 5).map((alert) => {
        const failed = Object.values(alert.delivery).some((result) => result.startsWith("failed"));
        return el("li", {},
            el("div", { class: "alert-title" }, alert.title),
            el("div", { class: "hint" },
                `${alert.message} · ${timeAgo(alert.created_at)}`,
                failed ? el("span", { class: "failed" }, " · delivery failed") : null),
        );
    }));
}

$("testAlert").addEventListener("click", async () => {
    try {
        const record = await api("/alerts/test", { method: "POST" });
        const results = Object.entries(record.delivery).map(([channel, result]) => `${channel}: ${result}`).join(", ");
        say(`Test alert sent (${results}).`, results.includes("failed") ? "error" : "ok");
        await loadSystem();
    } catch (error) {
        say(error.message, "error");
    }
});

let resolveLogin = null;

function showLogin() {
    $("loginScreen").hidden = false;
    $("loginPassword").focus();
    return new Promise((resolve) => { resolveLogin = resolve; });
}

$("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    $("loginError").textContent = "";
    try {
        await api("/auth/login", { method: "POST", body: { password: $("loginPassword").value } });
        $("loginPassword").value = "";
        $("loginScreen").hidden = true;
        if (resolveLogin) resolveLogin();
        resolveLogin = null;
        if (state.signedOut) location.reload();
    } catch (error) {
        $("loginError").textContent = error.message;
        $("loginPassword").select();
    }
});

$("signOutButton").addEventListener("click", async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    state.signedOut = true;
    showLogin();
});

$("dismissBanner").addEventListener("click", () => {
    $("openBanner").hidden = true;
    try { sessionStorage.setItem("openBannerDismissed", "1"); } catch (error) {}
});

async function checkAuth() {
    let status;
    try {
        status = await api("/auth/status");
    } catch (error) {
        return;
    }
    let dismissed = false;
    try { dismissed = sessionStorage.getItem("openBannerDismissed") === "1"; } catch (error) {}
    $("openBanner").hidden = status.required || dismissed;
    $("accountSetting").hidden = !status.required;
    if (status.required && !status.signed_in) await showLogin();
}

let pollTimer = null;

function connectSocket() {
    const base = API || location.origin;
    const socket = new WebSocket(base.replace(/^http/, "ws") + "/dashboard/ws");

    socket.onopen = () => {
        clearInterval(pollTimer);
        pollTimer = null;
        setOnline(true);
    };
    socket.onmessage = (message) => onSummary(JSON.parse(message.data));
    socket.onclose = async (event) => {
        if (event.code === 4401 || event.code === 1008 || event.code === 403) {
            await showLogin();
        }
        if (!pollTimer) pollTimer = setInterval(loadSummary, 5000);
        setTimeout(connectSocket, 3000);
    };
}

function tickClock() {
    const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    $("clock").textContent = now;
    $("presentClock").textContent = now;
}

async function init() {
    setupCameras();
    showPage(location.hash.slice(1));
    tickClock();
    setInterval(tickClock, 10000);

    await checkAuth();
    await loadSummary();
    loadVideos();
    loadModels();
    loadCameras();

    setInterval(loadCameras, 2000);
    setInterval(() => {
        if (state.summary) renderBays(state.summary.parking);
        loadLatest();
        loadEvents();
        loadSystem();
    }, 60000);
    connectSocket();
    if (new URLSearchParams(location.search).has("present")) setPresenting(true);
}

init();
