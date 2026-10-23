"use strict";

// Plate test: reads a plate from the laptop camera. Only calls
// /plate-test/read, which never records anything or opens a gate.

const API = location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

// The guide frame, as a share of the video: keep in sync with .guide in screens.css.
const GUIDE = { left: 0.1, top: 0.3, width: 0.8, height: 0.4 };
const HISTORY_SIZE = 8;

const $ = (id) => document.getElementById(id);

let stream = null;
let busy = false;
let firstRead = true;
const history = [];

function applyTheme() {
    let theme = "auto";
    try { theme = localStorage.getItem("theme") || "auto"; } catch (error) { /* storage blocked */ }
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
}

function cameraNote(text) {
    $("cameraNote").hidden = !text;
    $("cameraNote").textContent = text || "";
}

function cameraError(error) {
    if (!window.isSecureContext) {
        return "The browser only allows the camera on a secure page. Open this page at http://localhost:8000/plate-test.html.";
    }
    switch (error && error.name) {
        case "NotAllowedError":
            return "Camera access was blocked. Allow it from the camera symbol in the address bar, then reload.";
        case "NotFoundError":
            return "No camera was found on this computer.";
        case "NotReadableError":
            return "The camera is being used by another app. Close it and reload.";
        default:
            return "The camera couldn't be started.";
    }
}

async function startCamera(deviceId) {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    cameraNote("Starting the camera…");
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: deviceId
                ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
                : { width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false,
        });
    } catch (error) {
        cameraNote(cameraError(error));
        return;
    }
    $("video").srcObject = stream;
    cameraNote(null);
    $("readButton").disabled = false;
    $("keepReading").disabled = false;
    await listCameras();
}

async function listCameras() {
    // Labels are only filled in once the camera has been allowed.
    const devices = (await navigator.mediaDevices.enumerateDevices())
        .filter((device) => device.kind === "videoinput");
    const select = $("cameraSelect");
    select.hidden = devices.length < 2;
    const current = stream && stream.getVideoTracks()[0].getSettings().deviceId;
    select.replaceChildren(...devices.map((device, index) => {
        const option = document.createElement("option");
        option.value = device.deviceId;
        option.textContent = device.label || `Camera ${index + 1}`;
        return option;
    }));
    if (current) select.value = current;
}

function captureGuide() {
    // Send only what's inside the frame: less to read, fewer stray words.
    const video = $("video");
    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) return null;

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width * GUIDE.width);
    canvas.height = Math.round(height * GUIDE.height);
    canvas.getContext("2d").drawImage(
        video,
        Math.round(width * GUIDE.left), Math.round(height * GUIDE.top), canvas.width, canvas.height,
        0, 0, canvas.width, canvas.height,
    );
    return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
}

function showResult(result) {
    const verdict = $("resultVerdict");
    if (!result.plate_number) {
        $("resultPlate").textContent = "–";
        verdict.className = "bench-verdict amber";
        verdict.textContent = "Nothing readable. Write bigger, fill the frame and hold it still.";
        return;
    }
    $("resultPlate").textContent = result.plate_number;
    const sure = `${Math.round(result.confidence * 100)}% sure`;
    verdict.className = `bench-verdict ${result.looks_like_plate ? "green" : "amber"}`;
    verdict.textContent = (result.looks_like_plate
        ? `${sure} · Looks like a valid number plate`
        : `${sure} · Doesn't match the plate format set in Settings`)
        + (result.raw && result.raw !== result.plate_number
            ? ` · Read ${result.raw}, corrected using the plate layout`
            : "");

    history.unshift({ ...result, at: new Date() });
    history.length = Math.min(history.length, HISTORY_SIZE);
    $("history").replaceChildren(...history.map((item) => {
        const row = document.createElement("li");
        const time = document.createElement("span");
        time.className = "hint";
        time.textContent = item.at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        const plate = document.createElement("span");
        plate.className = "plate";
        plate.textContent = item.plate_number;
        const sureness = document.createElement("span");
        sureness.className = "hint";
        sureness.textContent = `${Math.round(item.confidence * 100)}%`;
        row.append(time, plate, sureness);
        return row;
    }));
}

function showError(message) {
    $("resultPlate").textContent = "–";
    $("resultVerdict").className = "bench-verdict red";
    $("resultVerdict").textContent = message;
}

async function readOnce() {
    if (busy) return;
    busy = true;
    $("readButton").disabled = true;
    $("resultVerdict").className = "bench-verdict";
    $("resultVerdict").textContent = firstRead
        ? "Loading the reader. The first time takes up to 20 seconds…"
        : "Reading…";

    try {
        const image = await captureGuide();
        if (!image) throw new Error("The camera isn't showing a picture yet.");
        const response = await fetch(API + "/plate-test/read", {
            method: "POST",
            headers: { "Content-Type": "image/jpeg" },
            body: image,
            credentials: "include",
        });
        const body = await response.json().catch(() => ({}));
        if (response.status === 401) throw new Error("Sign in on the dashboard in this browser first, then reload.");
        if (!response.ok) throw new Error(body.detail || `The server answered ${response.status}.`);
        firstRead = false;
        showResult(body);
    } catch (error) {
        showError(error instanceof TypeError ? "Can't reach the server. Is it running?" : error.message);
        $("keepReading").checked = false;
    }

    busy = false;
    $("readButton").disabled = false;
}

async function keepReading() {
    while ($("keepReading").checked) {
        await readOnce();
        await new Promise((resolve) => setTimeout(resolve, 800));
    }
}

$("readButton").addEventListener("click", readOnce);
$("keepReading").addEventListener("change", (event) => { if (event.target.checked) keepReading(); });
$("cameraSelect").addEventListener("change", (event) => startCamera(event.target.value));

applyTheme();
if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) startCamera();
else cameraNote(cameraError(null));
