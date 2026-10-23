"use strict";

// Entry screen: a display at the entry gate that tells the arriving driver
// which space to park in. Read-only; it never changes anything.

const API = location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

// How long a driver's message stays up before the screen goes back to idle.
const HOLD_MS = 30000;

const $ = (id) => document.getElementById(id);

let idleTimer = null;
let refreshing = false;
let again = false;

function applyTheme() {
    let theme = "auto";
    try { theme = localStorage.getItem("theme") || "auto"; } catch (error) { /* storage blocked */ }
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
}

async function api(path) {
    const response = await fetch(API + path, { credentials: "include" });
    if (response.status === 401) {
        const error = new Error("Sign in on the dashboard in this browser first, then reload this page.");
        error.signIn = true;
        throw error;
    }
    if (!response.ok) throw new Error(`The server answered ${response.status}.`);
    return response.json();
}

function setNotice(text) {
    $("notice").hidden = !text;
    $("notice").textContent = text || "";
}

function show({ tone, plate = null, lead, big, message, slot = null, slots = [] }) {
    $("arrival").dataset.tone = tone;
    $("plate").hidden = !plate;
    $("plate").textContent = plate || "";
    $("lead").textContent = lead;
    $("big").textContent = big;
    $("message").textContent = message;

    $("map").hidden = !slot;
    if (!slot) return;
    $("map").replaceChildren(...slots.map((bay) => {
        const item = document.createElement("li");
        const mine = bay.slot_id === slot;
        item.className = mine ? "mine" : bay.plate_number ? "taken" : "free";
        item.textContent = bay.slot_id;
        if (mine) item.setAttribute("aria-current", "true");
        return item;
    }));
}

function showIdle(stats) {
    const free = stats.available;
    if (free <= 0) {
        show({
            tone: "amber",
            lead: "Sorry",
            big: "The car park is full",
            message: "Please wait or come back later. A space opens as soon as a car leaves.",
        });
        return;
    }
    show({
        tone: "idle",
        lead: `${free} space${free === 1 ? "" : "s"} free`,
        big: "Drive up to the barrier",
        message: "Your parking space will show here once your number plate is read.",
    });
}

function showEvent(event, stats) {
    const plate = event.plate_number;
    switch (event.status) {
        case "entered":
            show({
                tone: "green",
                plate,
                lead: "Welcome. Please park in",
                big: event.slot_id,
                message: "The barrier is opening. Your space is highlighted below.",
                slot: event.slot_id,
                slots: stats.slots,
            });
            return true;
        case "already_parked": {
            const bay = stats.slots.find((item) => item.plate_number === plate);
            show({
                tone: "green",
                plate,
                lead: "You're already checked in. Your space is",
                big: bay ? bay.slot_id : "–",
                message: "If this isn't right, please ask the attendant.",
                slot: bay ? bay.slot_id : null,
                slots: stats.slots,
            });
            return true;
        }
        case "capacity_full":
            show({
                tone: "amber",
                plate,
                lead: "Sorry",
                big: "The car park is full",
                message: "Please wait or come back later. A space opens as soon as a car leaves.",
            });
            return true;
        case "entry_rejected":
            // A driver-facing screen never says why (e.g. "stolen").
            show({
                tone: "red",
                plate,
                lead: "Please wait",
                big: "An attendant will help you",
                message: "This car can't be let in automatically.",
            });
            return true;
        default:
            return false;
    }
}

async function refresh() {
    // Collapse bursts of updates into one request at a time.
    if (refreshing) { again = true; return; }
    refreshing = true;
    try {
        const [{ events }, stats] = await Promise.all([
            api("/events?gate=entry&limit=1"),
            api("/parking/stats"),
        ]);
        setNotice(null);

        clearTimeout(idleTimer);
        const event = events[0];
        const age = event ? Date.now() - Date.parse(event.timestamp) : Infinity;
        if (age < HOLD_MS && showEvent(event, stats)) {
            idleTimer = setTimeout(refresh, HOLD_MS - age + 100);
        } else {
            showIdle(stats);
        }
    } catch (error) {
        setNotice(error.signIn ? error.message : "Can't reach the server. Retrying…");
    }
    refreshing = false;
    if (again) { again = false; refresh(); }
}

let pollTimer = null;

function connectSocket() {
    const base = API || location.origin;
    const socket = new WebSocket(base.replace(/^http/, "ws") + "/dashboard/ws");
    socket.onopen = () => { clearInterval(pollTimer); pollTimer = null; };
    // The socket pushes a summary whenever anything changes.
    socket.onmessage = () => refresh();
    socket.onclose = () => {
        if (!pollTimer) pollTimer = setInterval(refresh, 5000);
        setTimeout(connectSocket, 3000);
    };
}

function tickClock() {
    $("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

applyTheme();
tickClock();
setInterval(tickClock, 10000);
refresh();
connectSocket();
