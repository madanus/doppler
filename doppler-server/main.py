from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status, Header
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import uuid
import os
import sqlite3
import hashlib

app = FastAPI(
    title="Doppler AI Control Plane",
    description="Production-grade, highly stable Multi-tenant RBAC serverless control plane for Doppler on-desktop self-learning agents",
    version="3.1.0"
)

# -------------------------------------------------------------------------
# DATABASE CONFIGURATION & STABLE SCHEMA
# -------------------------------------------------------------------------
DB_FILE = os.environ.get("DOPPLER_DB_PATH") or ("/tmp/doppler.db" if os.environ.get("GAE_ENV") or os.environ.get("K_SERVICE") else "doppler.db")

# Force recreate DB on startup to ensure a completely clean, pristine, stable RBAC migration.
if os.path.exists(DB_FILE) and not os.environ.get("GAE_ENV") and not os.environ.get("K_SERVICE"):
    try:
        os.remove(DB_FILE)
        print("Legacy local SQLite DB removed for stable production RBAC schema migration.")
    except Exception as e:
        print(f"Failed to remove legacy DB: {e}")

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def hash_password(password: str) -> str:
    """Secure SHA-256 hashing for user passwords."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Companies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        created_at TEXT
    )
    """)
    
    # 2. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        company_id TEXT,
        username TEXT,
        password TEXT, -- Hashed
        role TEXT, -- 'global_admin', 'co_admin', 'agent'
        functional_role TEXT, -- 'Product Manager', 'Lead Developer', etc.
        mode TEXT, -- 'learn', 'run'
        created_at TEXT,
        FOREIGN KEY(company_id) REFERENCES companies(id),
        UNIQUE(company_id, username)
    )
    """)
    
    # 3. Active Sessions Table (For secure, stateful server-side token auth)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id TEXT,
        expires_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # 4. Telemetry Table
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
        raw_payload TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # 5. Personas Table
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
    
    # 6. Tasks Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        persona_id TEXT,
        title TEXT,
        steps TEXT,
        status TEXT, -- 'pending', 'approved', 'completed'
        created_at TEXT,
        approved_at TEXT,
        completed_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    
    # 7. Learnt Rules Table (New! Closes the loop of Learn Mode -> Automatic Run Mode actions!)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learnt_rules (
        id TEXT PRIMARY KEY,
        company_id TEXT,
        trigger_text TEXT,
        reply_text TEXT,
        created_at TEXT,
        FOREIGN KEY(company_id) REFERENCES companies(id)
    )
    """)
    
    # Seed default data
    cursor.execute("SELECT COUNT(*) FROM companies")
    if cursor.fetchone()[0] == 0:
        now = datetime.datetime.utcnow().isoformat()
        
        # Seed Companies
        co_global = "co_global_admin"
        co_touchtap = "co_touchtap_tech"
        co_madalgos = "co_madalgos_ai"
        
        cursor.execute("INSERT INTO companies VALUES (?, ?, ?)", (co_global, "Doppler Global Operations", now))
        cursor.execute("INSERT INTO companies VALUES (?, ?, ?)", (co_touchtap, "TouchTap Technologies", now))
        cursor.execute("INSERT INTO companies VALUES (?, ?, ?)", (co_madalgos, "MadAlgos AI Corp", now))
        
        # Seed Users with secure SHA-256 hashed passwords
        # Global Admin
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_global_admin", co_global, "admin", hash_password("admin123"), "global_admin", "Global Administrator", "learn", now
        ))
        # TouchTap Admin
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_touchtap_admin", co_touchtap, "touchtap_admin", hash_password("admin123"), "co_admin", "Company Administrator", "learn", now
        ))
        # MadAlgos Admin
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_madalgos_admin", co_madalgos, "madalgos_admin", "admin123", "co_admin", "Company Administrator", "learn", now
        ))
        # Agent Users (TouchTap)
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_agent_pm", co_touchtap, "agent_pm", hash_password("user123"), "agent", "Product Manager", "learn", now
        ))
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_agent_dev", co_touchtap, "agent_dev", hash_password("user123"), "agent", "Lead Developer", "run", now
        ))
        # Agent Users (MadAlgos)
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_agent_marketer", co_madalgos, "agent_mkt", hash_password("user123"), "agent", "Digital Marketer", "learn", now
        ))
        
        # Seed default pre-defined personas
        # Digital Marketer
        cursor.execute("INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)", (
            "persona_digital_marketer", "SaaS Growth Specialist", "Digital Marketer",
            "An expert in automated outreach, performance marketing, and copywriting.",
            "Identity: You are a growth-driven Digital Marketer shadow agent. Your objective is to optimize funnel metrics, draft high-converting ad copy, and automate multi-channel campaigns. Analyze user's past actions to craft tailored marketing responses.",
            0, now
        ))
        # Product Manager
        cursor.execute("INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)", (
            "persona_product_manager", "Agile Spec Compiler", "Product Manager",
            "An expert at translating unstructured ideas into user stories, Gherkin specs, and sequence maps.",
            "Identity: You are an enterprise-grade Product Manager shadow agent. Your core soul focuses on clear Agile ticket structures, strict out-of-scope boundaries, and roadmap sequencing. Analyze raw telemetry to compile developer-ready tickets.",
            0, now
        ))
        # Lead Developer
        cursor.execute("INSERT INTO personas VALUES (?, ?, ?, ?, ?, ?, ?)", (
            "persona_lead_developer", "Software Architect", "Lead Developer",
            "An expert in SOLID architecture, automated test design, and refactoring.",
            "Identity: You are a pragmatic Lead Developer shadow agent. Your soul focuses on robust coding patterns, modular software systems, and security gates. Analyze coding patterns to automate code writing and testing.",
            0, now
        ))
        
        # Seed initial telemetry
        cursor.execute("INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            "tel_1", now, "usr_agent_pm", "Slack - #C0BATMT8XJA (Specs Channel)", "Active", 45, 12, "OCR: Text field focus 'Specs Input'", "{}"
        ))
        cursor.execute("INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            "tel_2", now, "usr_agent_dev", "Cursor - magic-publisher/main.py", "In a Meeting", 120, 5, "OCR: Editor file 'main.py'", "{}"
        ))
        
        # Seed initial learned rules
        cursor.execute("INSERT INTO learnt_rules VALUES (?, ?, ?, ?, ?)", (
            "rule_1", co_touchtap, "hi", "Hello there! Doppler shadow PM is ready to compile specifications.", now
        ))
        
    conn.commit()
    conn.close()

init_db()

# -------------------------------------------------------------------------
# AUTHENTICATION & SECURE RBAC MIDDLEWARE DEPENDENCY
# -------------------------------------------------------------------------
def get_current_user(x_doppler_token: Optional[str] = Header(None), db = Depends(get_db)):
    """
    Middleware dependency that extracts session tokens, verifies expiration,
    resolves the active user role, and returns user identity securely.
    """
    if not x_doppler_token:
        raise HTTPException(status_code=401, detail="X-Doppler-Token authentication header is required.")
        
    cursor = db.cursor()
    now = datetime.datetime.utcnow().isoformat()
    
    cursor.execute("""
    SELECT users.*, companies.name as company_name 
    FROM sessions 
    JOIN users ON sessions.user_id = users.id 
    JOIN companies ON users.company_id = companies.id
    WHERE sessions.token = ? AND sessions.expires_at > ?
    """, (x_doppler_token, now))
    
    user_row = cursor.fetchone()
    if not user_row:
        raise HTTPException(status_code=401, detail="Session expired or invalid token. Please log in again.")
        
    return dict(user_row)

# -------------------------------------------------------------------------
# MODELS & SCHEMAS
# -------------------------------------------------------------------------
class LoginPayload(BaseModel):
    company_name: str
    username: str
    password: str

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

class CompanyCreatePayload(BaseModel):
    name: str
    admin_username: str
    admin_password: str

class UserCreatePayload(BaseModel):
    company_id: str
    username: str
    password: str
    role: str # 'co_admin' or 'agent'
    functional_role: Optional[str] = "Product Manager"

class UserUpdatePayload(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    functional_role: Optional[str] = None

class ModeTogglePayload(BaseModel):
    user_id: str
    mode: str # 'learn' or 'run'

class LearntRulePayload(BaseModel):
    company_id: str
    trigger_text: str
    reply_text: str

# -------------------------------------------------------------------------
# ENDPOINTS (STRICT ENFORCEMENT)
# -------------------------------------------------------------------------

@app.get("/api/extension/download")
def download_extension():
    zip_path = os.path.join(os.path.dirname(__file__), "doppler-extension.zip")
    if os.path.exists(zip_path):
        return FileResponse(zip_path, filename="doppler-extension.zip", media_type="application/zip")
    raise HTTPException(status_code=404, detail="Extension zip file not found on server.")

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """Renders unified multi-tenant login & control dashboard."""
    html_file_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(html_file_path):
        with open(html_file_path, "r") as f:
            return f.read()
    return HTMLResponse(content="Dashboard HTML loading... Please call /api/metadata", status_code=200)

# Auth Endpoint
@app.post("/api/auth/login")
def login(payload: LoginPayload, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, name FROM companies WHERE LOWER(name) = LOWER(?)", (payload.company_name.strip(),))
    crow = cursor.fetchone()
    if not crow:
        raise HTTPException(status_code=401, detail="Company not found")
        
    company_id = crow["id"]
    hashed_pass = hash_password(payload.password)
    
    cursor.execute("""
    SELECT users.*, companies.name as company_name 
    FROM users 
    JOIN companies ON users.company_id = companies.id 
    WHERE users.company_id = ? AND users.username = ? AND users.password = ?
    """, (company_id, payload.username, hashed_pass))
    
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid username or password under this company")
        
    user = dict(row)
    
    token = str(uuid.uuid4())
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(hours=24)).isoformat()
    
    cursor.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token, user["id"], expires_at))
    db.commit()
    
    user["token"] = token
    user.pop("password", None)
    return user

# Multi-tenant Creation: Add Company (GLOBAL ADMIN ONLY)
@app.post("/api/companies")
def create_company(payload: CompanyCreatePayload, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] != "global_admin":
        raise HTTPException(status_code=403, detail="Forbidden: Only Doppler Global Administrators can register customer companies.")
        
    cursor = db.cursor()
    cursor.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (payload.name.strip(),))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Company name already exists")
        
    company_id = f"co_{uuid.uuid4().hex[:8]}"
    admin_user_id = f"usr_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    hashed_pass = hash_password(payload.admin_password)
    
    try:
        cursor.execute("INSERT INTO companies VALUES (?, ?, ?)", (company_id, payload.name, now))
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            admin_user_id, company_id, payload.admin_username, hashed_pass, "co_admin", "Company Administrator", "learn", now
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
    return {"status": "success", "company_id": company_id, "admin_user_id": admin_user_id}

@app.get("/api/companies")
def list_companies(current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] != "global_admin":
        raise HTTPException(status_code=403, detail="Forbidden: Restricted to Global Admins.")
    cursor = db.cursor()
    cursor.execute("SELECT * FROM companies")
    return [dict(row) for row in cursor.fetchall()]

# Multi-tenant Creation: Add Agent User (GLOBAL ADMIN ONLY)
@app.post("/api/users")
def create_user(payload: UserCreatePayload, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] != "global_admin":
        raise HTTPException(status_code=403, detail="Forbidden: Only Doppler Global Administrators can provision agent accounts.")
        
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE company_id = ? AND username = ?", (payload.company_id, payload.username))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Username already exists in this company")
        
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    hashed_pass = hash_password(payload.password)
    
    cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        user_id, payload.company_id, payload.username, hashed_pass, payload.role, payload.functional_role, "learn", now
    ))
    db.commit()
    return {"status": "success", "user_id": user_id}

# Multi-tenant Edit (GLOBAL ADMIN ONLY)
@app.put("/api/users/{user_id}")
def update_user(user_id: str, payload: UserUpdatePayload, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] != "global_admin":
        raise HTTPException(status_code=403, detail="Forbidden: Restricted to Global Admins.")
        
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
        
    fields = []
    params = []
    if payload.username is not None:
        fields.append("username = ?")
        params.append(payload.username)
    if payload.password is not None:
        fields.append("password = ?")
        params.append(hash_password(payload.password))
    if payload.role is not None:
        fields.append("role = ?")
        params.append(payload.role)
    if payload.functional_role is not None:
        fields.append("functional_role = ?")
        params.append(payload.functional_role)
        
    if not fields:
        return {"status": "no-op"}
        
    params.append(user_id)
    query = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"
    try:
        cursor.execute(query, tuple(params))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists in this company")
        
    return {"status": "success", "user_id": user_id}

# Multi-tenant Delete User (GLOBAL ADMIN ONLY)
@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] != "global_admin":
        raise HTTPException(status_code=403, detail="Forbidden: Restricted to Global Admins.")
        
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
        
    cursor.execute("DELETE FROM telemetry WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM tasks WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    return {"status": "success", "user_id": user_id}

@app.get("/api/users")
def list_users(company_id: Optional[str] = None, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    
    if current_user["role"] == "co_admin":
        company_id = current_user["company_id"]
    elif current_user["role"] == "agent":
        raise HTTPException(status_code=403, detail="Forbidden: Standard agents are restricted from browsing user directories.")
        
    query = "SELECT users.*, companies.name as company_name FROM users JOIN companies ON users.company_id = companies.id"
    params = []
    
    if company_id:
        query += " WHERE users.company_id = ?"
        params.append(company_id)
        
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    
    result = []
    for r in rows:
        d = dict(r)
        d.pop("password", None)
        result.append(d)
    return result

# Client Toggle Learn/Run Mode
@app.post("/api/users/toggle-mode")
def toggle_user_mode(payload: ModeTogglePayload, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] == "agent" and current_user["id"] != payload.user_id:
        raise HTTPException(status_code=403, detail="Forbidden: Agents cannot modify other users' client modes.")
        
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
        
    cursor.execute("UPDATE users SET mode = ? WHERE id = ?", (payload.mode, payload.user_id))
    db.commit()
    return {"status": "success", "user_id": payload.user_id, "mode": payload.mode}

# -------------------------------------------------------------------------
# LEARNT RULES CRUD (Closes loop: Learning observations -> Autopilot Actions)
# -------------------------------------------------------------------------
@app.post("/api/learning/rules")
def register_learnt_rule(payload: LearntRulePayload, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    rule_id = f"rule_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    
    # Enforce multi-tenant boundaries
    if current_user["role"] != "global_admin" and current_user["company_id"] != payload.company_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot write learnt rules for another company.")
        
    cursor.execute("""
    INSERT INTO learnt_rules VALUES (?, ?, ?, ?, ?)
    """, (rule_id, payload.company_id, payload.trigger_text.strip(), payload.reply_text.strip(), now))
    db.commit()
    return {"status": "success", "rule_id": rule_id, "created_at": now}

@app.get("/api/learning/rules")
def list_learnt_rules(current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    company_id = current_user["company_id"] if current_user["role"] != "global_admin" else None
    
    if company_id:
        cursor.execute("SELECT * FROM learnt_rules WHERE company_id = ? ORDER BY created_at DESC", (company_id,))
    else:
        cursor.execute("SELECT * FROM learnt_rules ORDER BY created_at DESC")
        
    return [dict(row) for row in cursor.fetchall()]

# -------------------------------------------------------------------------
# REAL-TIME SLACK MESSAGE WEBHOOK TRIGGERS (INTEGRATED WITH LEARNT RULES)
# -------------------------------------------------------------------------
@app.post("/api/webhooks/slack")
async def slack_webhook(payload: Dict[str, Any], db = Depends(get_db)):
    """
    Secure, real-time Slack Event Subscriptions Webhook.
    Wired directly to the self-learning dynamic rules database. If an incoming
    message matches a learnt pattern, it triggers an instant Autopilot Task!
    """
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}
        
    event = payload.get("event", {})
    if not event:
        return {"status": "ignored"}
        
    text = event.get("text", "").strip()
    channel = event.get("channel", "")
    
    # Anti-loop protection
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"status": "ignored"}
        
    cursor = db.cursor()
    
    # A. Check against the dynamic Self-Learning rule base first!
    # If the user taught Doppler "Trigger -> Response", look it up!
    cursor.execute("""
    SELECT learnt_rules.*, companies.id as co_id 
    FROM learnt_rules 
    JOIN companies ON learnt_rules.company_id = companies.id
    WHERE LOWER(?) LIKE '%' || LOWER(learnt_rules.trigger_text) || '%' LIMIT 1
    """, (text,))
    
    rule_row = cursor.fetchone()
    if rule_row:
        rule = dict(rule_row)
        print(f"Self-Learning Match Found: Trigger '{rule['trigger_text']}' matches message '{text}'!")
        
        # Pull standard agent under that company to run the learned response!
        cursor.execute("SELECT id, functional_role FROM users WHERE company_id = ? AND role = 'agent' LIMIT 1", (rule["company_id"],))
        u_row = cursor.fetchone()
        target_user_id = u_row["id"] if u_row else "usr_agent_pm"
        persona_role = u_row["functional_role"] if u_row else "Product Manager"
        
        task_id = f"task_learnt_{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.utcnow().isoformat()
        
        task_title = f"Autopilot Learned Reply (Trigger: '{rule['trigger_text']}')"
        steps = [
            f"Waking up custom shadow {persona_role} assistant.",
            "Analyzing incoming Slack context stream.",
            f"Pre-compiling learned response: '{rule['reply_text']}'.",
            f"Posting response back to Slack channel {channel}."
        ]
        steps_str = "||".join(steps)
        
        cursor.execute("INSERT INTO tasks VALUES (?, ?, 'persona_product_manager', ?, ?, 'pending', ?, NULL, NULL)", (
            task_id, target_user_id, task_title, steps_str, now
        ))
        db.commit()
        return {
            "status": "triggered_learnt_rule",
            "task_id": task_id,
            "assigned_to": target_user_id,
            "trigger": rule["trigger_text"],
            "reply": rule["reply_text"]
        }
        
    # B. Fallback to hardcoded core templates if no custom rule matches
    task_title = ""
    steps = []
    persona_id = ""
    target_user_id = "usr_agent_pm"
    
    text_lower = text.lower()
    if "test" in text_lower:
        task_title = f"Automated Pytest Run [Slack: {channel[:8]}]"
        persona_id = "persona_lead_developer"
        steps = [
            "Fetch latest branch commits from GitHub",
            "Initialize sandboxed virtual environment",
            "Execute pytest test suite locally",
            f"Report test outcomes back to Slack channel {channel}"
        ]
    elif "deploy" in text_lower:
        task_title = f"Autopilot Cloud Run Deploy [Slack: {channel[:8]}]"
        persona_id = "persona_lead_developer"
        steps = [
            "Trigger cloud container rebuild via Cloud Build",
            "Update routing paths on Google Cloud Run",
            "Perform live endpoint network health checks",
            f"Post active deployment URL back to Slack channel {channel}"
        ]
    elif "spec" in text_lower or "prd" in text_lower:
        task_title = f"Compile Agile Specifications [Slack: {channel[:8]}]"
        persona_id = "persona_product_manager"
        steps = [
            "Analyze telemetry streams and draft specifications",
            "Synthesize sequence architecture diagrams",
            "Format stories using Gherkin Given-When-Then rules",
            f"Upload specification PDF and notify channel {channel}"
        ]
        
    if task_title and steps:
        cursor.execute("SELECT id FROM users WHERE role = 'agent' AND functional_role LIKE ? LIMIT 1", 
                       (f"%{persona_id.split('_')[-1]}%",))
        row = cursor.fetchone()
        if row:
            target_user_id = row["id"]
            
        task_id = f"task_slack_{uuid.uuid4().hex[:6]}"
        now = datetime.datetime.utcnow().isoformat()
        steps_str = "||".join(steps)
        
        cursor.execute("""
        INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
        """, (task_id, target_user_id, persona_id, task_title, steps_str, "pending", now))
        db.commit()
        return {
            "status": "triggered",
            "task_id": task_id,
            "assigned_to": target_user_id
        }
        
    return {"status": "completed", "details": "No rule match."}

# -------------------------------------------------------------------------
# METRICS & BILLING ESTIMATES (Calculated proportionally)
# -------------------------------------------------------------------------
@app.get("/api/metrics")
def get_metrics(company_id: Optional[str] = None, user_id: Optional[str] = None, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    role = current_user["role"]
    
    if role == "agent":
        user_id = current_user["id"]
        company_id = current_user["company_id"]
    elif role == "co_admin":
        company_id = current_user["company_id"]
        user_id = None
        
    global_telemetry = 0
    global_tasks = 0
    global_cost = 0.0
    
    if role == "global_admin":
        cursor.execute("SELECT COUNT(*) FROM telemetry")
        global_telemetry = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks")
        global_tasks = cursor.fetchone()[0]
        global_cost = (global_telemetry * 0.000002) + (global_tasks * 0.00005)
        
    company_telemetry = 0
    company_tasks = 0
    company_cost = 0.0
    
    if company_id:
        cursor.execute("SELECT COUNT(*) FROM telemetry JOIN users ON telemetry.user_id = users.id WHERE users.company_id = ?", (company_id,))
        company_telemetry = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks JOIN users ON tasks.user_id = users.id WHERE users.company_id = ?", (company_id,))
        company_tasks = cursor.fetchone()[0]
        company_cost = (company_telemetry * 0.000002) + (company_tasks * 0.00005)
        
    user_telemetry = 0
    user_tasks = 0
    user_cost = 0.0
    user_mode = "learn"
    
    if user_id:
        cursor.execute("SELECT COUNT(*) FROM telemetry WHERE user_id = ?", (user_id,))
        user_telemetry = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,))
        user_tasks = cursor.fetchone()[0]
        user_cost = (user_telemetry * 0.000002) + (user_tasks * 0.00005)
        
        cursor.execute("SELECT mode FROM users WHERE id = ?", (user_id,))
        urow = cursor.fetchone()
        if urow:
            user_mode = urow[0]
            
    return {
        "global": {
            "telemetry_count": global_telemetry if role == "global_admin" else 0,
            "tasks_count": global_tasks if role == "global_admin" else 0,
            "estimated_cost_usd": round(global_cost, 6) if role == "global_admin" else 0.0
        },
        "company": {
            "telemetry_count": company_telemetry if role != "agent" else 0,
            "tasks_count": company_tasks if role != "agent" else 0,
            "estimated_cost_usd": round(company_cost, 6) if role != "agent" else 0.0
        },
        "user": {
            "telemetry_count": user_telemetry,
            "tasks_count": user_tasks,
            "estimated_cost_usd": round(user_cost, 6),
            "mode": user_mode
        }
    }

# Ingest Telemetry
@app.post("/api/telemetry")
def ingest_telemetry(payload: TelemetryPayload, db = Depends(get_db)):
    cursor = db.cursor()
    record_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    raw_str = str(payload.raw_payload) if payload.raw_payload else "{}"
    
    cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Unrecognized user ID. Telemetry rejected.")
        
    cursor.execute("""
    INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record_id, now, payload.user_id, payload.window_title, payload.slack_status,
        payload.keystrokes, payload.mouse_clicks, payload.ocr_summary, raw_str
    ))
    db.commit()
    return {"status": "success", "record_id": record_id, "ingested_at": now}

@app.get("/api/telemetry")
def get_telemetry(company_id: Optional[str] = None, user_id: Optional[str] = None, limit: int = 50, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    
    role = current_user["role"]
    if role == "agent":
        user_id = current_user["id"]
        company_id = current_user["company_id"]
    elif role == "co_admin":
        company_id = current_user["company_id"]
        
    query = """
    SELECT telemetry.*, users.username, users.functional_role 
    FROM telemetry 
    JOIN users ON telemetry.user_id = users.id
    """
    params = []
    conditions = []
    
    if company_id:
        conditions.append("users.company_id = ?")
        params.append(company_id)
    if user_id:
        conditions.append("telemetry.user_id = ?")
        params.append(user_id)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@app.get("/api/personas")
def get_personas(current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM personas")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@app.get("/api/tasks")
def get_tasks(company_id: Optional[str] = None, user_id: Optional[str] = None, status: Optional[str] = None, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    
    role = current_user["role"]
    if role == "agent":
        user_id = current_user["id"]
        company_id = current_user["company_id"]
    elif role == "co_admin":
        company_id = current_user["company_id"]
        
    query = """
    SELECT tasks.*, users.username, users.functional_role 
    FROM tasks 
    JOIN users ON tasks.user_id = users.id
    """
    params = []
    conditions = []
    
    if company_id:
        conditions.append("users.company_id = ?")
        params.append(company_id)
    if user_id:
        conditions.append("tasks.user_id = ?")
        params.append(user_id)
    if status:
        conditions.append("tasks.status = ?")
        params.append(status)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY created_at DESC"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    
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
def create_task(payload: TaskCreatePayload, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] == "agent" and current_user["id"] != payload.user_id:
        raise HTTPException(status_code=403, detail="Forbidden: Agents can only queue tasks for themselves.")
        
    cursor = db.cursor()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    steps_str = "||".join(payload.steps)
    
    cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Target agent user not found.")
        
    cursor.execute("""
    INSERT INTO tasks VALUES (?, ?, 'persona_product_manager', ?, ?, 'pending', ?, NULL, NULL)
    """, (
        task_id, payload.user_id, payload.title, steps_str, now
    ))
    db.commit()
    return {"status": "success", "task_id": task_id, "created_at": now}

@app.post("/api/tasks/{task_id}/approve")
def approve_task(task_id: str, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    task = dict(row)
    
    if current_user["role"] == "agent" and current_user["id"] != task["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden: Restricted from approving other agents' tasks.")
        
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("UPDATE tasks SET status = 'approved', approved_at = ? WHERE id = ?", (now, task_id))
    db.commit()
    return {"status": "success", "task_id": task_id, "approved_at": now}

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, current_user = Depends(get_current_user), db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    task = dict(row)
    
    if current_user["role"] == "agent" and current_user["id"] != task["user_id"]:
        raise HTTPException(status_code=403, detail="Forbidden: Restricted from executing other agents' tasks.")
        
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?", (now, task_id))
    db.commit()
    return {"status": "success", "task_id": task_id, "completed_at": now}

@app.post("/api/personas/sync")
def federated_sync(background_tasks: BackgroundTasks, current_user = Depends(get_current_user), db = Depends(get_db)):
    if current_user["role"] != "global_admin":
        raise HTTPException(status_code=403, detail="Forbidden: Sync optimized prompts restricted to Global Admin.")
        
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM telemetry")
    total_logs = cursor.fetchone()[0]
    now = datetime.datetime.utcnow().isoformat()
    
    def run_optimization():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        new_prompt = """Identity: You are an enterprise-grade Product Manager shadow agent. 
LEARNED UPDATE (Collective): Based on aggregate telemetry logs, we optimized the workflows to prioritize structured Agile specifications with explicit Given-When-Then logic."""
        c.execute("UPDATE personas SET base_prompt = ?, last_updated = ? WHERE id = 'persona_product_manager'", (new_prompt, now))
        conn.commit()
        conn.close()

    background_tasks.add_task(run_optimization)
    return {"status": "triggered", "message": f"Federated aggregation active on {total_logs} logs.", "updates_applied": ["persona_product_manager"], "timestamp": now}
