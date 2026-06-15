// ================================================================
//  Face Recognition Attendance System — Frontend Logic
//  ---------------------------------------------------------------
//  Features:
//    1. Webcam capture & recognise loop (every 1.5 s)
//    2. Attendance session management (start/stop with time window)
//    3. Multiple face display — every recognised face shown
//    4. Attendance summary polling — present / absent counts + table
//    5. Tab system — All / Present / Absent views
//    6. Enroll new students from webcam frame
// ================================================================

// ---- Configuration ----
const API_URL = "";
const CAPTURE_INTERVAL = 1500;

// ---- DOM: Camera ----
const video          = document.getElementById("video");
const overlay        = document.getElementById("overlay");
const overlayCtx     = overlay.getContext("2d");
const captureCanvas  = document.getElementById("captureCanvas");
const captureCtx     = captureCanvas.getContext("2d");
const videoContainer = document.getElementById("videoContainer");
const placeholder    = document.getElementById("placeholder");
const startBtn       = document.getElementById("startBtn");
const stopBtn        = document.getElementById("stopBtn");
const statusText     = document.getElementById("statusText");

// ---- DOM: Attendance ----
const startAttendanceBtn = document.getElementById("startAttendanceBtn");
const stopAttendanceBtn  = document.getElementById("stopAttendanceBtn");
const sessionStatus      = document.getElementById("sessionStatus");

// ---- DOM: Recognised faces ----
const faceList          = document.getElementById("faceList");
const presentCountEl    = document.getElementById("presentCount");
const absentCountEl     = document.getElementById("absentCount");
const totalCountEl      = document.getElementById("totalCount");

// ---- DOM: Student table + tabs ----
const studentBody = document.getElementById("studentBody");
const tabBar      = document.getElementById("tabBar");
let   currentTab  = "all";

// ---- DOM: Modal ----
const modal          = document.getElementById("timeModal");
const startTimeInput = document.getElementById("startTime");
const endTimeInput   = document.getElementById("endTime");
const modalConfirm   = document.getElementById("modalConfirmBtn");
const modalCancel    = document.getElementById("modalCancelBtn");

// ---- DOM: Enroll ----
const enrollNameInput = document.getElementById("enrollName");
const enrollBtn       = document.getElementById("enrollBtn");

// ---- State ----
let stream           = null;
let captureTimer     = null;
let isProcessing     = false;
let isSessionActive  = false;
let summaryInterval  = null;

// ================================================================
//  1. CAMERA CONTROL
// ================================================================

async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }
    });
    video.srcObject = stream;
    await video.play();

    placeholder.style.display = "none";
    setStatus("Camera active", "active");
    startBtn.disabled = true;
    stopBtn.disabled  = false;

    startCaptureLoop();
  } catch (err) {
    setStatus("Camera error: " + err.message, "error");
  }
}

function stopCamera() {
  if (stream) {
    stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
  }
  if (captureTimer) {
    clearInterval(captureTimer);
    captureTimer = null;
  }
  video.srcObject = null;
  placeholder.style.display = "flex";
  setStatus("Camera stopped", "inactive");
  startBtn.disabled = false;
  stopBtn.disabled  = true;
  videoContainer.className = "video-container";
  overlayCtx.clearRect(0, 0, overlay.width, overlay.height);
}

// ================================================================
//  2. CAPTURE & RECOGNISE LOOP
// ================================================================

function startCaptureLoop() {
  // Give the video a moment to settle, then size the canvases
  requestAnimationFrame(function () {
    sizeCanvases();
  });
  captureTimer = setInterval(captureAndRecognize, CAPTURE_INTERVAL);
}

function sizeCanvases() {
  // Capture canvas: native video resolution (for sending to API)
  captureCanvas.width  = video.videoWidth  || 640;
  captureCanvas.height = video.videoHeight || 480;
  // Overlay canvas: match the VIDEO element's actual CSS pixel size
  const rect = video.getBoundingClientRect();
  overlay.width  = rect.width  || captureCanvas.width;
  overlay.height = rect.height || captureCanvas.height;
}

async function captureAndRecognize() {
  if (isProcessing) return;
  isProcessing = true;

  // Sync canvases to match video
  captureCanvas.width  = video.videoWidth  || 640;
  captureCanvas.height = video.videoHeight || 480;
  const videoRect = video.getBoundingClientRect();
  overlay.width  = videoRect.width  || captureCanvas.width;
  overlay.height = videoRect.height || captureCanvas.height;
  captureCtx.drawImage(video, 0, 0);

  const imageData = captureCanvas.toDataURL("image/jpeg", 0.8);
  const base64    = imageData.split(",")[1];

  let allFaceItems = [];

  try {
    const response = await fetch(API_URL + "/recognize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: base64 })
    });
    const data = await response.json();

    // Clear overlay
    overlayCtx.clearRect(0, 0, overlay.width, overlay.height);
    faceList.innerHTML = "";

    // ---- Session status banner ----
    let sessionInfo = null;
    if (data.session_active === true) {
      sessionInfo = { text: "Session active — marking attendance", cls: "marked" };
    } else if (data.session_active === false) {
      sessionInfo = { text: "No active session — not marking",    cls: "skipped" };
    }

    if (data.status === "success" && data.results.length > 0) {
      // Scale: native video resolution -> overlay display pixel size
      const nativeW = video.videoWidth  || captureCanvas.width;
      const nativeH = video.videoHeight || captureCanvas.height;
      const scaleX  = overlay.width  / nativeW;
      const scaleY  = overlay.height / nativeH;

      data.results.forEach(function (r) {
        const [x1, y1, x2, y2] = r.bbox;
        const color = r.status === "recognized" ? "#10b981" : "#ef4444";

        // Draw face box
        overlayCtx.strokeStyle = color;
        overlayCtx.lineWidth   = 3;
        overlayCtx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY);

        // Draw label (name + confidence %)
        const label = r.status === "recognized"
          ? r.student_name + " (" + (r.confidence * 100).toFixed(0) + "%)"
          : "Unknown";
        overlayCtx.fillStyle = color;
        overlayCtx.font      = "bold 15px sans-serif";
        overlayCtx.fillText(label, x1 * scaleX, Math.max(y1 * scaleY - 8, 16));

        // Build face card for side panel
        const isUnknown = r.status !== "recognized";
        allFaceItems.push(createFaceCard(
          isUnknown ? "Unknown" : r.student_name,
          r.confidence,
          !isUnknown && r.attendance_marked,
          isUnknown
        ));
      });

      videoContainer.className = "video-container recognized";
    } else {
      videoContainer.className = "video-container";
    }

    // Build face list HTML
    let html = "";
    if (sessionInfo) {
      html += '<div class="face-card session-info">'
        + '<span class="face-badge badge-' + sessionInfo.cls + '">' + escapeHtml(sessionInfo.text) + '</span>'
        + '</div>';
    }
    if (allFaceItems.length === 0) {
      html += '<p class="face-list-empty"><em>No faces detected&hellip;</em></p>';
    } else {
      // Show newest first
      allFaceItems.reverse();
      allFaceItems.forEach(function (el) { html += el.outerHTML; });
    }
    faceList.innerHTML = html;

  } catch (err) {
    console.error("Recognize error:", err);
  }

  isProcessing = false;
}

function createFaceCard(name, confidence, marked, isUnknown) {
  const div = document.createElement("div");
  div.className = "face-card";
  const badgeText = marked ? "MARKED" : (isUnknown ? "" : "SKIP");
  div.innerHTML = [
    '<span class="face-name">', escapeHtml(name), '</span>',
    '<span class="face-confidence">', (confidence * 100).toFixed(0), '%</span>',
    badgeText ? '<span class="face-badge ' + (marked ? "badge-marked" : "badge-skip") + '">' + badgeText + '</span>' : ''
  ].join('');
  return div;
}

// ================================================================
//  3. ATTENDANCE SESSION
// ================================================================

// Open modal when "Start Attendance" is clicked
startAttendanceBtn.addEventListener("click", function () {
  modal.classList.remove("hidden");
});

// Cancel modal
modalCancel.addEventListener("click", function () {
  modal.classList.add("hidden");
});

// Confirm: start the session
modalConfirm.addEventListener("click", async function () {
  const startTime = startTimeInput.value;
  const endTime   = endTimeInput.value;

  if (!startTime || !endTime) {
    alert("Please set both start and end times.");
    return;
  }

  try {
    const res = await fetch(API_URL + "/attendance/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_time: startTime, end_time: endTime })
    });
    const data = await res.json();

    if (data.status === "started") {
      isSessionActive = true;
      updateSessionUI(true, startTime, endTime);
      modal.classList.add("hidden");
      startAttendanceBtn.disabled = true;
      stopAttendanceBtn.disabled  = false;
      startPollingSummary();
    } else {
      alert("Failed to start session: " + JSON.stringify(data));
    }
  } catch (err) {
    alert("Error starting session: " + err.message);
  }
});

// Stop session
stopAttendanceBtn.addEventListener("click", async function () {
  try {
    await fetch(API_URL + "/attendance/stop", { method: "POST" });
    isSessionActive = false;
    updateSessionUI(false);
    startAttendanceBtn.disabled = false;
    stopAttendanceBtn.disabled  = true;
    if (summaryInterval) {
      clearInterval(summaryInterval);
      summaryInterval = null;
    }
  } catch (err) {
    console.error("Error stopping session:", err);
  }
});

function updateSessionUI(active, start, end) {
  if (active) {
    sessionStatus.className = "session-badge active";
    sessionStatus.innerHTML = "&#x1F534; Session: " + escapeHtml(start) + " - " + escapeHtml(end);
  } else {
    sessionStatus.className = "session-badge inactive";
    sessionStatus.textContent = "No active session";
  }
}

// ================================================================
//  4. ATTENDANCE SUMMARY POLLING
// ================================================================

function startPollingSummary() {
  fetchSummary();
  summaryInterval = setInterval(fetchSummary, 3000);
}

async function fetchSummary() {
  try {
    const res = await fetch(API_URL + "/attendance/summary");
    const data = await res.json();

    presentCountEl.textContent = data.present;
    absentCountEl.textContent  = data.absent;
    totalCountEl.textContent   = data.total;
    document.getElementById("percentCount").textContent = data.percentage + "%";

    // Store for tab rendering
    window._attendanceData = data;
    renderTable(currentTab);
  } catch (err) {
    console.error("Summary poll error:", err);
  }
}

// ================================================================
//  5. TAB SYSTEM
// ================================================================

tabBar.addEventListener("click", function (e) {
  const tabBtn = e.target.closest(".tab");
  if (!tabBtn) return;

  // Update active tab
  tabBar.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
  tabBtn.classList.add("active");
  currentTab = tabBtn.dataset.tab;

  if (window._attendanceData) {
    renderTable(currentTab);
  }
});

function renderTable(tab) {
  const data = window._attendanceData;
  if (!data || !data.students || data.students.length === 0) {
    studentBody.innerHTML = '<tr><td colspan="4" class="empty-msg">No students enrolled yet.</td></tr>';
    return;
  }

  let filtered = data.students;
  if (tab === "present") filtered = data.students.filter(function (s) { return s.present; });
  if (tab === "absent")  filtered = data.students.filter(function (s) { return !s.present; });

  let html = "";
  filtered.forEach(function (s, i) {
    const statusClass = s.present ? "status-present" : "status-absent";
    const statusText  = s.present ? "Present" : "Absent";
    const timeText    = s.time || "—";
    html += "<tr>"
      + "<td>" + (i + 1) + "</td>"
      + "<td>" + escapeHtml(s.name) + "</td>"
      + "<td><span class=\"status-pill " + statusClass + "\">" + statusText + "</span></td>"
      + "<td>" + timeText + "</td>"
      + "</tr>";
  });

  if (filtered.length === 0) {
    html = '<tr><td colspan="4" class="empty-msg">No students in this category.</td></tr>';
  }

  studentBody.innerHTML = html;
}

// ================================================================
//  6. ENROLL
// ================================================================

enrollBtn.addEventListener("click", async function () {
  const name = enrollNameInput.value.trim();
  if (!name) {
    alert("Please enter a student name first.");
    enrollNameInput.focus();
    return;
  }
  if (!stream) {
    alert("Camera must be running to capture an enrollment photo.");
    return;
  }

  captureCanvas.width  = video.videoWidth;
  captureCanvas.height = video.videoHeight;
  captureCtx.drawImage(video, 0, 0);

  captureCanvas.toBlob(async function (blob) {
    const formData = new FormData();
    formData.append("name", name);
    formData.append("file", blob, "enrollment.jpg");

    try {
      const res = await fetch(API_URL + "/enroll", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      alert("Enroll result:\n" + JSON.stringify(data, null, 2));
      if (data.status === "enrolled") {
        enrollNameInput.value = "";
        fetchSummary();  // refresh table
      }
    } catch (err) {
      alert("Enrollment failed:\n" + err.message);
    }
  }, "image/jpeg");
});

// ================================================================
//  7. UI HELPERS
// ================================================================

function setStatus(msg, type) {
  statusText.textContent = msg;
  statusText.className   = "status " + type;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.appendChild(document.createTextNode(text));
  return div.innerHTML;
}

// ================================================================
//  8. EVENT BINDING (camera start/stop)
// ================================================================

startBtn.addEventListener("click", startCamera);
stopBtn.addEventListener("click",  stopCamera);
