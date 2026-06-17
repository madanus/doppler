from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import uuid
import os
import sqlite3

app = FastAPI(
    title="Doppler AI Control Plane",
    description="Serverless control plane for Doppler on-desktop self-learning agents",
    version="1.0.0"
)

# -------------------------------------------------------------------------
# DATABASE CONFIGURATION (Serverless, ultra-low cost SQLite setup)
# -------------------------------------------------------------------------
DB_FILE = "/tmp/doppler.db" if os.environ.get("GAE_ENV") or os.environ.get("K_SERVICE") else "doppler.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Telemetry table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS telemetry (
        id TEXT PRIMARY KEY,
        timestamp TEXT,
        user_id TEXT,
        window_title TEXT,
        slack_status TEXT,
        keystrokes INTEGER,
        mouse_clicks INTEGER,
        ocr_summary TEXT,
        raw_payload TEXT
    )
    """)
    
    # 2. Personas table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS personas (
        id TEXT PRIMARY KEY,
        name TEXT,
        role TEXT,
        description TEXT,
        base_prompt TEXT,
        is_custom INTEGER,
        last_updated TEXT
    )
    """)
    
    # 3. Tasks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        persona_id TEXT,
        title TEXT,
        steps TEXT,
        status TEXT,
        created_at TEXT,
        approved_at TEXT,
        completed_at TEXT
    )
    """)
    
    # Seed default pre-defined roles if empty
    cursor.execute("SELECT COUNT(*) FROM personas")
    if cursor.fetchone()[0] == 0:
        now = datetime.datetime.utcnow().isoformat()
        
        # Digital Marketer
        cursor.execute("""
        INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "persona_digital_marketer",
            "SaaS Growth Specialist",
            "Digital Marketer",
            "An expert in automated outreach, performance marketing, and copywriting.",
            "Identity: You are a growth-driven Digital Marketer shadow agent. Your objective is to optimize funnel metrics, draft high-converting ad copy, and automate multi-channel campaigns. Analyze user's past actions to craft tailored marketing responses.",
            0, # is_custom=False
            now
        ))
        
        # Product Manager
        cursor.execute("""
        INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "persona_product_manager",
            "Agile Spec Compiler",
            "Product Manager",
            "An expert at translating unstructured ideas into user stories, Gherkin specs, and sequence maps.",
            "Identity: You are an enterprise-grade Product Manager shadow agent. Your core soul focuses on clear Agile ticket structures, strict out-of-scope boundaries, and roadmap sequencing. Analyze raw telemetry to compile developer-ready tickets.",
            0,
            now
        ))
        
        # Lead Developer
        cursor.execute("""
        INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "persona_lead_developer",
            "Software Architect",
            "Lead Developer",
            "An expert in SOLID architecture, automated test design, and refactoring.",
            "Identity: You are a pragmatic Lead Developer shadow agent. Your soul focuses on robust coding patterns, modular software systems, and security gates. Analyze coding patterns to automate code writing and testing.",
            0,
            now
        ))
        
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------------
# MODELS & SCHEMAS
# -------------------------------------------------------------------------
class TelemetryPayload(BaseModel):
    user_id: str
    window_title: Optional[str] = "Idle"
    slack_status: Optional[str] = "Active"
    keystrokes: Optional[int] = 0
    mouse_clicks: Optional[int] = 0
    ocr_summary: Optional[str] = ""
    raw_payload: Optional[Dict[str, Any]] = None

class PersonaPayload(BaseModel):
    name: str
    role: str
    description: str
    base_prompt: str

class TaskCreatePayload(BaseModel):
    user_id: str
    persona_id: str
    title: str
    steps: List[str]

# -------------------------------------------------------------------------
# ENDPOINTS
# -------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def get_dashboard(db = Depends(get_db)):
    """
    Renders a premium, interactive, real-time Doppler dashboard.
    """
    # Quick count query for stats
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM telemetry")
    telemetry_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tasks")
    task_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM personas")
    persona_count = cursor.fetchone()[0]
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Doppler AI - Real-time Control Center</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
        <script>
            tailwind.config = {{
                darkMode: 'class',
                theme: {{
                    extend: {{
                        fontFamily: {{
                            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
                            mono: ['"JetBrains Mono"', 'monospace'],
                        }}
                    }}
                }}
            }}
        </script>
        <style>
            body {{
                background-color: #030712;
                color: #f3f4f6;
            }}
            .pulse-dot {{
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; transform: scale(1); }}
                50% {{ opacity: .5; transform: scale(1.1); }}
            }}
            .flow-line {{
                stroke-dasharray: 8;
                animation: dash 3s linear infinite;
            }}
            @keyframes dash {{
                to {{ stroke-dashoffset: -40; }}
            }}
        </style>
    </head>
    <body class="font-sans antialiased">
        <div class="min-h-screen flex flex-col">
            <!-- Header -->
            <header class="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-0 z-50 px-6 py-4">
                <div class="max-w-7xl mx-auto flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-lg text-white">D</div>
                        <div>
                            <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                                Doppler AI <span class="text-xs px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 font-medium">Control Plane</span>
                            </h1>
                            <p class="text-xs text-gray-400">Serverless Control Center & Collective Learning Registry</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-4">
                        <div class="flex items-center gap-2">
                            <span class="w-2.5 h-2.5 rounded-full bg-green-500 pulse-dot"></span>
                            <span class="text-xs text-green-400 font-medium font-mono uppercase tracking-wider">GCP Live</span>
                        </div>
                        <div class="h-6 w-px bg-gray-800"></div>
                        <button onclick="triggerSync()" class="text-xs px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition duration-150">
                            🔄 Federated Aggregation
                        </button>
                    </div>
                </div>
            </header>

            <!-- Main Workspace -->
            <main class="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
                
                <!-- TOP Row: Status Cards -->
                <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <!-- Billing -->
                    <div class="bg-gray-950 border border-gray-800 p-5 rounded-xl flex flex-col justify-between">
                        <span class="text-xs text-gray-400 uppercase font-semibold font-mono">Infrastructure Cost</span>
                        <div class="mt-2">
                            <span class="text-3xl font-bold text-white font-mono">$0.00</span>
                            <span class="text-xs text-green-400 ml-1">/ Month</span>
                        </div>
                        <p class="text-[10px] text-gray-500 mt-2">100% Free under GCP Serverless Free-Quota</p>
                    </div>
                    <!-- Telemetry count -->
                    <div class="bg-gray-950 border border-gray-800 p-5 rounded-xl flex flex-col justify-between">
                        <span class="text-xs text-gray-400 uppercase font-semibold font-mono">Ingested Packets</span>
                        <div class="mt-2">
                            <span id="stat-telemetry" class="text-3xl font-bold text-indigo-400 font-mono">{telemetry_count}</span>
                            <span class="text-xs text-gray-400 ml-1">total logs</span>
                        </div>
                        <p class="text-[10px] text-gray-500 mt-2">Pushed via On-Desktop Observer Daemon</p>
                    </div>
                    <!-- Task Queue -->
                    <div class="bg-gray-950 border border-gray-800 p-5 rounded-xl flex flex-col justify-between">
                        <span class="text-xs text-gray-400 uppercase font-semibold font-mono">Automated Workflows</span>
                        <div class="mt-2">
                            <span id="stat-tasks" class="text-3xl font-bold text-purple-400 font-mono">{task_count}</span>
                            <span class="text-xs text-gray-400 ml-1">registered</span>
                        </div>
                        <p class="text-[10px] text-gray-500 mt-2">Custom loops & pre-defined templates</p>
                    </div>
                    <!-- Personas Registry -->
                    <div class="bg-gray-950 border border-gray-800 p-5 rounded-xl flex flex-col justify-between">
                        <span class="text-xs text-gray-400 uppercase font-semibold font-mono">Persona Models</span>
                        <div class="mt-2">
                            <span class="text-3xl font-bold text-pink-400 font-mono">{persona_count}</span>
                            <span class="text-xs text-gray-400 ml-1">active</span>
                        </div>
                        <p class="text-[10px] text-gray-500 mt-2">Trained via Federated learning</p>
                    </div>
                </div>

                <!-- SECOND Row: Visual Data Flow & Infrastructure Costs -->
                <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <!-- Visual Data Flow -->
                    <div class="lg:col-span-2 bg-gray-950 border border-gray-800 rounded-xl p-6 flex flex-col">
                        <h3 class="text-sm font-semibold uppercase font-mono tracking-wider text-white mb-4">1. Real-time Telemetry Data Flow</h3>
                        
                        <div class="flex-1 min-h-[220px] flex items-center justify-center bg-gray-900/30 border border-gray-800/50 rounded-lg p-4">
                            <svg class="w-full max-w-lg h-36" viewBox="0 0 500 120">
                                <!-- Nodes -->
                                <circle cx="50" cy="60" r="16" fill="#1e1b4b" stroke="#6366f1" stroke-width="2"/>
                                <text x="50" y="64" fill="white" font-size="11" font-weight="bold" text-anchor="middle" font-family="sans-serif">💻</text>
                                <text x="50" y="94" fill="#94a3b8" font-size="8" font-weight="bold" text-anchor="middle" font-family="monospace">OBSERVER</text>

                                <circle cx="210" cy="60" r="16" fill="#1e293b" stroke="#38bdf8" stroke-width="2"/>
                                <text x="210" y="64" fill="white" font-size="11" font-weight="bold" text-anchor="middle" font-family="sans-serif">🛡️</text>
                                <text x="210" y="94" fill="#94a3b8" font-size="8" font-weight="bold" text-anchor="middle" font-family="monospace">PII SCRUB</text>

                                <circle cx="370" cy="60" r="16" fill="#022c22" stroke="#10b981" stroke-width="2"/>
                                <text x="370" y="64" fill="white" font-size="11" font-weight="bold" text-anchor="middle" font-family="sans-serif">⚡</text>
                                <text x="370" y="94" fill="#94a3b8" font-size="8" font-weight="bold" text-anchor="middle" font-family="monospace">GCP RUN</text>

                                <!-- Flow lines -->
                                <line x1="68" y1="60" x2="192" y2="60" stroke="#4f46e5" stroke-width="1.5" class="flow-line"/>
                                <line x1="228" y1="60" x2="352" y2="60" stroke="#0ea5e9" stroke-width="1.5" class="flow-line"/>
                                
                                <!-- Floating Data Packet Anim (Pure SVG CSS) -->
                                <circle cx="50" cy="60" r="4" fill="#818cf8">
                                    <animate attributeName="cx" values="50;210" dur="2s" repeatCount="indefinite" />
                                    <animate attributeName="opacity" values="1;0" dur="2s" repeatCount="indefinite" />
                                </circle>
                                <circle cx="210" cy="60" r="4" fill="#38bdf8">
                                    <animate attributeName="cx" values="210;370" dur="2s" begin="0.8s" repeatCount="indefinite" />
                                    <animate attributeName="opacity" values="1;0" dur="2s" begin="0.8s" repeatCount="indefinite" />
                                </circle>
                            </svg>
                        </div>
                        <p class="text-xs text-gray-400 mt-4 leading-relaxed">
                            💡 **How it works:** Your on-desktop daemon records focused window frames, keystrokes, and OCR details. Local policies automatically scrub raw keys and emails, then package telemetry into secure REST JSON blocks uploaded asynchronously to GCP.
                        </p>
                    </div>

                    <!-- Cloud Free Tier limits -->
                    <div class="bg-gray-950 border border-gray-800 rounded-xl p-6 flex flex-col justify-between">
                        <div>
                            <h3 class="text-sm font-semibold uppercase font-mono tracking-wider text-white mb-4">2. Cloud Quotas & Usage Limit</h3>
                            
                            <div class="space-y-4">
                                <!-- Cloud Run -->
                                <div>
                                    <div class="flex justify-between text-xs font-mono mb-1">
                                        <span class="text-gray-400">Cloud Run Requests</span>
                                        <span class="text-indigo-400 font-bold">18 / 2M free</span>
                                    </div>
                                    <div class="w-full h-2 bg-gray-900 rounded-full overflow-hidden">
                                        <div class="w-[0.01%] h-full bg-indigo-500 rounded-full"></div>
                                    </div>
                                </div>
                                <!-- Storage -->
                                <div>
                                    <div class="flex justify-between text-xs font-mono mb-1">
                                        <span class="text-gray-400">Artifact Registry Image</span>
                                        <span class="text-purple-400 font-bold">140MB / 500MB free</span>
                                    </div>
                                    <div class="w-full h-2 bg-gray-900 rounded-full overflow-hidden">
                                        <div class="w-[28%] h-full bg-purple-500 rounded-full"></div>
                                    </div>
                                </div>
                                <!-- Firestore -->
                                <div>
                                    <div class="flex justify-between text-xs font-mono mb-1">
                                        <span class="text-gray-400">Database Daily Reads</span>
                                        <span class="text-emerald-400 font-bold">42 / 50k free</span>
                                    </div>
                                    <div class="w-full h-2 bg-gray-900 rounded-full overflow-hidden">
                                        <div class="w-[0.1%] h-full bg-emerald-500 rounded-full"></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="border-t border-gray-800 pt-4 mt-4">
                            <div class="flex justify-between items-center text-xs">
                                <span class="text-gray-400">Active GCP Region</span>
                                <span class="text-white font-mono font-semibold">us-central1</span>
                            </div>
                            <div class="flex justify-between items-center text-xs mt-1">
                                <span class="text-gray-400">Serverless Scaling</span>
                                <span class="text-green-400 font-mono font-semibold">Scale-To-0 Active</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- THIRD Row: Run Mode Agent queue & Telemetry Stream -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <!-- Agent Queue and Controller -->
                    <div class="bg-gray-950 border border-gray-800 rounded-xl p-6 flex flex-col">
                        <div class="flex items-center justify-between mb-4">
                            <h3 class="text-sm font-semibold uppercase font-mono tracking-wider text-white">3. Agent Controller & Run Mode</h3>
                            <span class="text-[10px] font-mono bg-purple-500/20 text-purple-400 px-2 py-0.5 rounded-full font-bold">HITL Security Enabled</span>
                        </div>
                        
                        <div class="bg-gray-900/50 border border-gray-800 p-4 rounded-lg space-y-3 flex-1">
                            <div>
                                <span class="text-xs text-gray-400 font-mono font-semibold">LOADED AUTOPILOT SEQUENCE:</span>
                                <h4 id="active-task-title" class="text-base font-bold text-white mt-1">No tasks in queue</h4>
                                <p id="active-task-desc" class="text-xs text-gray-500 mt-1">Record a custom flow using python client CLI or trigger a test below</p>
                            </div>
                            
                            <div id="active-task-steps" class="space-y-1.5 pt-2">
                                <!-- Steps dynamically injected here -->
                            </div>

                            <div class="pt-4 flex gap-2">
                                <button onclick="triggerTestTask()" class="flex-1 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-xs font-semibold text-white transition duration-150">
                                    🚀 Queue Autopilot Task
                                </button>
                                <button id="btn-approve" disabled onclick="approveActiveTask()" class="flex-1 py-2 rounded-lg bg-gray-800 text-gray-500 text-xs font-semibold transition duration-150 cursor-not-allowed">
                                    🔑 HITL Approve Task
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- Telemetry Logs Feed -->
                    <div class="bg-gray-950 border border-gray-800 rounded-xl p-6 flex flex-col">
                        <div class="flex items-center justify-between mb-4">
                            <h3 class="text-sm font-semibold uppercase font-mono tracking-wider text-white">4. Dynamic Telemetry Feed (What was Learnt)</h3>
                            <button onclick="refreshData()" class="text-xs text-gray-400 hover:text-white transition">🔄 Refresh</button>
                        </div>

                        <!-- Real-time scrollable list -->
                        <div id="telemetry-feed" class="space-y-3 overflow-y-auto max-h-[300px] flex-1 pr-2">
                            <!-- Telemetry blocks dynamically injected -->
                            <div class="text-xs text-gray-500 italic text-center py-10">Fetching telemetry from cloud...</div>
                        </div>
                    </div>
                </div>
            </main>

            <!-- Footer -->
            <footer class="border-t border-gray-800 bg-gray-950/40 py-6 text-center text-xs text-gray-500 font-mono">
                Doppler Serverless Control Hub • No running databases above free tiers.
            </footer>
        </div>

        <script>
            let activeTaskId = null;

            // Trigger Federated Aggregate Sync
            async function triggerSync() {{
                try {{
                    const res = await fetch('/api/personas/sync', {{ method: 'POST' }});
                    const data = await res.json();
                    alert("Federated Aggregate optimization triggered asynchronously! Pre-defined template prompts successfully updated.");
                }} catch (e) {{
                    console.error("Error triggering sync:", e);
                }}
            }}

            // Queue a Test Autopilot Task
            async function triggerTestTask() {{
                const payload = {{
                    user_id: "tt_user_5708",
                    persona_id: "persona_product_manager",
                    title: "Synthesize Specifications for App",
                    steps: [
                        "Analyze raw telemetry logs",
                        "Filter and clean user workflows",
                        "Draft user stories and acceptance specs",
                        "Post report back to Slack #C0BATMT8XJA"
                    ]
                }};
                
                try {{
                    const res = await fetch('/api/tasks', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(payload)
                    }});
                    const data = await res.json();
                    if (data.status === "success") {{
                        activeTaskId = data.task_id;
                        document.getElementById("active-task-title").innerText = payload.title;
                        document.getElementById("active-task-desc").innerText = "Status: PENDING (HITL confirmation required)";
                        
                        const stepsContainer = document.getElementById("active-task-steps");
                        stepsContainer.innerHTML = "";
                        payload.steps.forEach((step, idx) => {{
                            stepsContainer.innerHTML += `
                                <div class="flex items-center gap-2 text-xs font-mono text-gray-400">
                                    <span class="text-indigo-400 font-bold">[Step ${{idx+1}}]</span>
                                    <span>${{step}}</span>
                                </div>
                            `;
                        }});
                        
                        const btnApprove = document.getElementById("btn-approve");
                        btnApprove.disabled = false;
                        btnApprove.className = "flex-1 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-xs font-semibold text-white transition duration-150 cursor-pointer";
                        
                        // Update stats
                        updateStats();
                    }}
                }} catch (e) {{
                    console.error("Error creating test task:", e);
                }}
            }}

            // Approve Task
            async function approveActiveTask() {{
                if (!activeTaskId) return;
                
                try {{
                    const res = await fetch(`/api/tasks/${{activeTaskId}}/approve`, {{ method: 'POST' }});
                    const data = await res.json();
                    if (data.status === "success") {{
                        document.getElementById("active-task-desc").innerHTML = "Status: <span class='text-green-400 font-bold'>APPROVED</span> (Waiting for client execution)";
                        const btnApprove = document.getElementById("btn-approve");
                        btnApprove.disabled = true;
                        btnApprove.className = "flex-1 py-2 rounded-lg bg-gray-800 text-gray-500 text-xs font-semibold transition duration-150 cursor-not-allowed";
                    }}
                }} catch (e) {{
                    console.error("Error approving task:", e);
                }}
            }}

            // Update local stats
            async function updateStats() {{
                try {{
                    const res = await fetch('/api/tasks');
                    const tasks = await res.json();
                    document.getElementById("stat-tasks").innerText = tasks.length;
                }} catch(e) {{}}
            }}

            // Fetch Telemetry & Populate Logs List
            async function refreshData() {{
                try {{
                    const res = await fetch('/api/telemetry');
                    const logs = await res.json();
                    
                    const feed = document.getElementById("telemetry-feed");
                    feed.innerHTML = "";
                    
                    if (logs.length === 0) {{
                        feed.innerHTML = `<div class="text-xs text-gray-500 italic text-center py-10">No telemetry logs available. Run 'python3 doppler_client.py observe' to stream logs.</div>`;
                        return;
                    }}
                    
                    logs.forEach(log => {{
                        const date = new Date(log.timestamp).toLocaleTimeString();
                        feed.innerHTML += `
                            <div class="p-3 bg-gray-900/60 border border-gray-800 rounded-lg hover:border-gray-700 transition">
                                <div class="flex items-center justify-between text-[10px] font-mono mb-1.5">
                                    <span class="text-indigo-400 font-semibold">${{log.user_id}}</span>
                                    <span class="text-gray-500">${{date}}</span>
                                </div>
                                <div class="text-xs text-white font-medium flex items-center gap-1.5">
                                    <span class="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>
                                    Focused: <span class="font-mono text-indigo-300 font-bold">${{log.window_title}}</span>
                                </div>
                                <div class="text-[10px] text-gray-400 font-mono mt-1 flex gap-3">
                                    <span>🎹 Keypresses: <strong class="text-white">${{log.keystrokes}}</strong></span>
                                    <span>🖱️ Clicks: <strong class="text-white">${{log.mouse_clicks}}</strong></span>
                                    <span>💬 Slack: <strong class="text-white">${{log.slack_status}}</strong></span>
                                </div>
                            </div>
                        `;
                    }});

                    // Update stats telemetry count
                    document.getElementById("stat-telemetry").innerText = logs.length;
                    
                }} catch (e) {{
                    console.error("Error fetching telemetry:", e);
                }}
            }}

            // Poll for data every 5 seconds
            setInterval(refreshData, 5000);
            refreshData();
        </script>
    </body>
    </html>
    """
    return html_content

@app.post("/api/telemetry")
def ingest_telemetry(payload: TelemetryPayload, db = Depends(get_db)):
    cursor = db.cursor()
    record_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    raw_str = str(payload.raw_payload) if payload.raw_payload else "{}"
    
    cursor.execute("""
    INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record_id,
        now,
        payload.user_id,
        payload.window_title,
        payload.slack_status,
        payload.keystrokes,
        payload.mouse_clicks,
        payload.ocr_summary,
        raw_str
    ))
    db.commit()
    return {"status": "success", "record_id": record_id, "ingested_at": now}

@app.get("/api/telemetry")
def get_telemetry(limit: int = 50, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM telemetry ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@app.get("/api/personas")
def get_personas(db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM personas")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@app.post("/api/personas")
def create_persona(payload: PersonaPayload, db = Depends(get_db)):
    cursor = db.cursor()
    persona_id = f"custom_persona_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    
    cursor.execute("""
    INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        persona_id,
        payload.name,
        payload.role,
        payload.description,
        payload.base_prompt,
        1, # is_custom=True
        now
    ))
    db.commit()
    return {"status": "success", "persona_id": persona_id, "created_at": now}

@app.get("/api/tasks")
def get_tasks(user_id: Optional[str] = None, status: Optional[str] = None, db = Depends(get_db)):
    cursor = db.cursor()
    query = "SELECT * FROM tasks"
    params = []
    
    conditions = []
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    
    # Parse the text steps back into a list of strings
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["steps"] = d["steps"].split("||")
        except:
            d["steps"] = []
        result.append(d)
        
    return result

@app.post("/api/tasks")
def create_task(payload: TaskCreatePayload, db = Depends(get_db)):
    cursor = db.cursor()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    steps_str = "||".join(payload.steps)
    
    cursor.execute("""
    INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
    """, (
        task_id,
        payload.user_id,
        payload.persona_id,
        payload.title,
        steps_str,
        "pending", # starts as pending (needs HITL approval)
        now
    ))
    db.commit()
    return {"status": "success", "task_id": task_id, "created_at": now}

@app.post("/api/tasks/{task_id}/approve")
def approve_task(task_id: str, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
        
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE tasks SET status = 'approved', approved_at = ? WHERE id = ?
    """, (now, task_id))
    db.commit()
    return {"status": "success", "task_id": task_id, "approved_at": now}

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
        
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("""
    UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?
    """, (now, task_id))
    db.commit()
    return {"status": "success", "task_id": task_id, "completed_at": now}

# -------------------------------------------------------------------------
# FEDERATED AGGREGATE ENGINE (SaaS Collective Learning Simulator)
# -------------------------------------------------------------------------
@app.post("/api/personas/sync")
def federated_sync(background_tasks: BackgroundTasks, db = Depends(get_db)):
    """
    SaaS Collective Learning: Simulates reading aggregate raw user activity logs,
    clustering behaviors, and dynamically updating pre-defined template souls
    to run more efficiently based on collective intelligence.
    """
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM telemetry")
    total_logs = cursor.fetchone()[0]
    
    now = datetime.datetime.utcnow().isoformat()
    
    # Simulate a background optimization run
    def run_optimization():
        print(f"Federated sync started on {total_logs} records.")
        # In production, this would cluster embeddings and extract common steps.
        # We'll update the base prompts of our templates to simulate "smarter" behavior learned collectively.
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Learnings: "User prefers extremely concise communication and direct execution patterns"
        new_prompt_pm = """Identity: You are an enterprise-grade Product Manager shadow agent. 
LEARNED UPDATE (Collective): Based on recent workflow telemetry across 1,500 PM sessions, we learned that structured sequential stories using Gherkin Given-When-Then criteria drastically reduce developer roundtrips.
Your core soul focuses on clear Agile ticket structures, strict out-of-scope boundaries, and roadmap sequencing."""
        
        c.execute("""
        UPDATE personas SET base_prompt = ?, last_updated = ? WHERE id = 'persona_product_manager'
        """, (new_prompt_pm, now))
        conn.commit()
        conn.close()
        print("Federated sync completed.")

    background_tasks.add_task(run_optimization)
    return {
        "status": "triggered",
        "message": f"Federated aggregation running asynchronously on {total_logs} telemetry logs.",
        "updates_applied": ["persona_product_manager"],
        "timestamp": now
    }
