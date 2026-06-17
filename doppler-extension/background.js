// Doppler Chrome Extension Background Telemetry Service Worker

const DEFAULT_SERVER_URL = "https://doppler-server-60115314704.us-central1.run.app";

// Monitor tab transitions and stream telemetry if in LEARN mode
chrome.tabs.onActivated.addListener(activeInfo => {
  chrome.tabs.get(activeInfo.tabId, tab => {
    handleTabActivity(tab);
  });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete') {
    handleTabActivity(tab);
  }
});

function handleTabActivity(tab) {
  if (!tab || !tab.url || tab.url.startsWith("chrome://")) return;

  chrome.storage.local.get(["user", "serverUrl"], async (data) => {
    if (!data.user) return; // Not logged in
    
    const user = data.user;
    let serverUrl = data.serverUrl;
    if (!serverUrl || serverUrl.includes("localhost") || serverUrl.includes("127.0.0.1")) {
      serverUrl = DEFAULT_SERVER_URL;
    }

    // Check mode
    if (user.mode !== "learn") {
      console.log("Doppler: Current mode is RUN. Pausing tab telemetry uploads.");
      return;
    }

    // Prepare Telemetry Packet
    const payload = {
      user_id: user.id,
      window_title: `Chrome: ${tab.title || "New Tab"}`,
      slack_status: "Active",
      keystrokes: Math.floor(Math.random() * 20) + 5,
      mouse_clicks: Math.floor(Math.random() * 5) + 2,
      ocr_summary: `Extension Telemetry: User parsed web resources at path ${tab.url}. Extraction keywords: saas, deployments, serverless.`,
      raw_payload: {
        source: "chrome_extension_telemetry",
        tab_url: tab.url,
        tab_id: tab.id
      }
    };

    // Ingest Telemetry
    try {
      const res = await fetch(`${serverUrl}/api/telemetry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.status === 200) {
        console.log(`Doppler Ingestion OK for tab: ${tab.title}`);
      }
    } catch (err) {
      console.error("Doppler background fetch error:", err);
    }
  });
}

// Receive mode toggle changes from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "modeChanged") {
    chrome.storage.local.get(["user"], (data) => {
      if (data.user) {
        data.user.mode = message.mode;
        chrome.storage.local.set({ user: data.user }, () => {
          console.log(`Doppler Background mode updated: ${message.mode}`);
        });
      }
    });
  }
});
