const DEFAULT_SERVER_URL = "https://doppler-server-60115314704.us-central1.run.app";

document.addEventListener("DOMContentLoaded", async () => {
  const panelLogin = document.getElementById("panel-login");
  const panelActive = document.getElementById("panel-active");
  const btnLogin = document.getElementById("btn-login");
  const btnLogout = document.getElementById("btn-logout");
  const toggleLearn = document.getElementById("toggle-learn");
  const toggleRun = document.getElementById("toggle-run");
  const userInfo = document.getElementById("user-info");
  const coInfo = document.getElementById("co-info");
  const logsContainer = document.getElementById("logs-container");

  // Helper to add log
  function addLog(text) {
    const time = new Date().toLocaleTimeString();
    const div = document.createElement("div");
    div.innerHTML = `<span class="text-indigo-400">[${time}]</span> ${text}`;
    logsContainer.appendChild(div);
    logsContainer.scrollTop = logsContainer.scrollHeight;
  }

  // Restore State
  chrome.storage.local.get(["user", "serverUrl"], (data) => {
    // Force reset/update serverUrl to prevent stale local storage (like legacy localhost) from blocking connection
    let serverUrl = data.serverUrl;
    if (!serverUrl || serverUrl.includes("localhost") || serverUrl.includes("127.0.0.1")) {
      serverUrl = DEFAULT_SERVER_URL;
    }
    chrome.storage.local.set({ serverUrl });

    if (data.user) {
      showActivePanel(data.user);
    } else {
      showLoginPanel();
    }
  });

  // Login
  btnLogin.addEventListener("click", async () => {
    const company_name = document.getElementById("ext-company").value.trim();
    const username = document.getElementById("ext-username").value.trim();
    const password = document.getElementById("ext-password").value;
    
    if (!company_name) {
      alert("Please enter your Company Name.");
      return;
    }
    
    chrome.storage.local.get(["serverUrl"], async (data) => {
      let serverUrl = data.serverUrl;
      if (!serverUrl || serverUrl.includes("localhost") || serverUrl.includes("127.0.0.1")) {
        serverUrl = DEFAULT_SERVER_URL;
      }
      addLog(`Attempting handshake with ${serverUrl}...`);
      
      try {
        const res = await fetch(`${serverUrl}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_name, username, password })
        });
        
        if (res.status === 200) {
          const user = await res.json();
          chrome.storage.local.set({ user });
          showActivePanel(user);
        } else {
          const errData = await res.json().catch(() => ({}));
          const errMsg = errData.detail || "Invalid username or password under this company.";
          addLog(`Handshake failed: ${errMsg}`);
          alert(`Login Failed: ${errMsg}`);
        }
      } catch (err) {
        addLog(`Network Error: ${err.message}`);
        alert(`Network Error: Could not connect to Doppler server at ${serverUrl}. Please check your internet connection and verify the server is running.`);
      }
    });
  });

  // Logout
  btnLogout.addEventListener("click", () => {
    chrome.storage.local.remove("user", () => {
      showLoginPanel();
    });
  });

  // Toggle Mode
  toggleLearn.addEventListener("click", () => toggleMode("learn"));
  toggleRun.addEventListener("click", () => toggleMode("run"));

  async function toggleMode(mode) {
    chrome.storage.local.get(["user", "serverUrl"], async (data) => {
      if (!data.user) return;
      const serverUrl = data.serverUrl || DEFAULT_SERVER_URL;
      
      try {
        const res = await fetch(`${serverUrl}/api/users/toggle-mode`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: data.user.id, mode })
        });
        
        if (res.status === 200) {
          data.user.mode = mode;
          chrome.storage.local.set({ user: data.user });
          updateModeUI(mode);
          addLog(`Client mode toggled to: ${mode.toUpperCase()}`);
          
          // Notify background worker of state change
          chrome.runtime.sendMessage({ action: "modeChanged", mode });
        }
      } catch (err) {
        addLog(`Toggle failed: ${err.message}`);
      }
    });
  }

  function showActivePanel(user) {
    panelLogin.classList.add("hidden");
    panelActive.classList.remove("hidden");
    userInfo.innerText = `👤 ${user.username}`;
    coInfo.innerText = user.company_name || "TouchTap Workspace";
    updateModeUI(user.mode);
    addLog(`Connected securely as ${user.username}`);
  }

  function showLoginPanel() {
    panelActive.classList.add("hidden");
    panelLogin.classList.remove("hidden");
    document.getElementById("ext-company").value = "";
    document.getElementById("ext-username").value = "";
    document.getElementById("ext-password").value = "";
  }

  function updateModeUI(mode) {
    if (mode === "learn") {
      toggleLearn.className = "toggle-btn active-learn";
      toggleRun.className = "toggle-btn";
    } else {
      toggleLearn.className = "toggle-btn";
      toggleRun.className = "toggle-btn active-run";
    }
  }
});
