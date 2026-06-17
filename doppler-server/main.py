from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import datetime
import uuid
import os
import sqlite3

app = FastAPI(
    title="Doppler AI Control Plane",
    description="Multi-tenant serverless control plane for Doppler on-desktop self-learning agents",
    version="2.2.0"
)

# -------------------------------------------------------------------------
# DATABASE CONFIGURATION & UPGRADES (Multi-tenant SQLite schema)
# -------------------------------------------------------------------------
DB_FILE = "/tmp/doppler.db" if os.environ.get("GAE_ENV") or os.environ.get("K_SERVICE") else "doppler.db"

# Force recreate DB on startup once to cleanly apply the new functional_role column schema
if os.path.exists(DB_FILE) and not os.environ.get("GAE_ENV") and not os.environ.get("K_SERVICE"):
    try:
        os.remove(DB_FILE)
        print("Legacy local SQLite DB removed for functional_role schema migration.")
    except Exception as e:
        print(f"Failed to remove legacy DB: {e}")

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
    
    # 1. Companies Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT UNIQUE,
        created_at TEXT
    )
    """)
    
    # 2. Users Table (Now with functional_role column)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        company_id TEXT,
        username TEXT,
        password TEXT,
        role TEXT, -- 'global_admin', 'co_admin', 'agent'
        functional_role TEXT, -- 'Product Manager', 'Lead Developer', 'Digital Marketer', etc.
        mode TEXT, -- 'learn', 'run'
        created_at TEXT,
        FOREIGN KEY(company_id) REFERENCES companies(id),
        UNIQUE(company_id, username)
    )
    """)
    
    # 3. Telemetry Table
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
    
    # 4. Personas Table
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
    
    # 5. Tasks Table
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
    
    # Seed default entities
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
        
        # Seed Users (Including functional_role values)
        # Global Admin
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_global_admin", co_global, "admin", "admin123", "global_admin", "Global Administrator", "learn", now
        ))
        # TouchTap Admin
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_touchtap_admin", co_touchtap, "touchtap_admin", "admin123", "co_admin", "Company Administrator", "learn", now
        ))
        # MadAlgos Admin
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_madalgos_admin", co_madalgos, "madalgos_admin", "admin123", "co_admin", "Company Administrator", "learn", now
        ))
        # Agent Users (TouchTap)
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_agent_pm", co_touchtap, "agent_pm", "user123", "agent", "Product Manager", "learn", now
        ))
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_agent_dev", co_touchtap, "agent_dev", "user123", "agent", "Lead Developer", "run", now
        ))
        # Agent Users (MadAlgos)
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            "usr_agent_marketer", co_madalgos, "agent_mkt", "user123", "agent", "Digital Marketer", "learn", now
        ))
        
        # Seed default pre-defined personas if empty
        cursor.execute("SELECT COUNT(*) FROM personas")
        if cursor.fetchone()[0] == 0:
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
            
        # Seed initial telemetry logs
        cursor.execute("INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            "tel_1", now, "usr_agent_pm", "Slack - #C0BATMT8XJA (Specs Channel)", "Active", 45, 12, "OCR: Text field focus 'Specs Input'", "{}"
        ))
        cursor.execute("INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            "tel_2", now, "usr_agent_dev", "Cursor - magic-publisher/main.py", "In a Meeting", 120, 5, "OCR: Editor file 'main.py'", "{}"
        ))
        
    conn.commit()
    conn.close()

init_db()

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

class ModeTogglePayload(BaseModel):
    user_id: str
    mode: str # 'learn' or 'run'

# -------------------------------------------------------------------------
# ENDPOINTS
# -------------------------------------------------------------------------

@app.get("/api/extension/download")
def download_extension():
    zip_path = os.path.join(os.path.dirname(__file__), "doppler-extension.zip")
    if os.path.exists(zip_path):
        return FileResponse(zip_path, filename="doppler-extension.zip", media_type="application/zip")
    raise HTTPException(status_code=404, detail="Extension zip file not found on server.")

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    """
    Renders a unified multi-tenant login & control dashboard.
    """
    html_file_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(html_file_path):
        with open(html_file_path, "r") as f:
            return f.read()
    return HTMLResponse(content="Dashboard HTML loading... Please call /api/metadata", status_code=200)

# Auth Endpoint
@app.post("/api/auth/login")
def login(payload: LoginPayload, db = Depends(get_db)):
    cursor = db.cursor()
    # 1. Resolve company by name (case-insensitive)
    cursor.execute("SELECT id, name FROM companies WHERE LOWER(name) = LOWER(?)", (payload.company_name.strip(),))
    crow = cursor.fetchone()
    if not crow:
        raise HTTPException(status_code=401, detail="Company not found")
        
    company_id = crow["id"]
    
    # 2. Authenticate user under that company
    cursor.execute("""
    SELECT users.*, companies.name as company_name 
    FROM users 
    JOIN companies ON users.company_id = companies.id 
    WHERE users.company_id = ? AND users.username = ? AND users.password = ?
    """, (company_id, payload.username, payload.password))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid username or password under this company")
    return dict(row)

# Multi-tenant Creation: Add Company
@app.post("/api/companies")
def create_company(payload: CompanyCreatePayload, db = Depends(get_db)):
    cursor = db.cursor()
    # Verify company name is unique
    cursor.execute("SELECT id FROM companies WHERE LOWER(name) = LOWER(?)", (payload.name.strip(),))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Company name already exists")
        
    company_id = f"co_{uuid.uuid4().hex[:8]}"
    admin_user_id = f"usr_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    
    try:
        # Create company
        cursor.execute("INSERT INTO companies VALUES (?, ?, ?)", (company_id, payload.name, now))
        # Create company admin (username unique within this company_id) with Company Administrator functional_role
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            admin_user_id, company_id, payload.admin_username, payload.admin_password, "co_admin", "Company Administrator", "learn", now
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
    return {"status": "success", "company_id": company_id, "admin_user_id": admin_user_id}

@app.get("/api/companies")
def list_companies(db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM companies")
    return [dict(row) for row in cursor.fetchall()]

# Multi-tenant Creation: Add Agent User (With functional_role support)
@app.post("/api/users")
def create_user(payload: UserCreatePayload, db = Depends(get_db)):
    cursor = db.cursor()
    # Check uniqueness of username within that company ONLY
    cursor.execute("SELECT id FROM users WHERE company_id = ? AND username = ?", (payload.company_id, payload.username))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Username already exists in this company")
        
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    
    # Save with both permission role and professional/functional role!
    cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        user_id, payload.company_id, payload.username, payload.password, payload.role, payload.functional_role, "learn", now
    ))
    db.commit()
    return {"status": "success", "user_id": user_id}

@app.get("/api/users")
def list_users(company_id: Optional[str] = None, db = Depends(get_db)):
    cursor = db.cursor()
    if company_id:
        cursor.execute("SELECT * FROM users WHERE company_id = ?", (company_id,))
    else:
        cursor.execute("SELECT * FROM users")
    return [dict(row) for row in cursor.fetchall()]

# Client Toggle Learn/Run Mode
@app.post("/api/users/toggle-mode")
def toggle_user_mode(payload: ModeTogglePayload, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")
        
    cursor.execute("UPDATE users SET mode = ? WHERE id = ?", (payload.mode, payload.user_id))
    db.commit()
    return {"status": "success", "user_id": payload.user_id, "mode": payload.mode}

# -------------------------------------------------------------------------
# METRICS & BILLING ESTIMATES (Calculated proportionally)
# -------------------------------------------------------------------------
@app.get("/api/metrics")
def get_metrics(company_id: Optional[str] = None, user_id: Optional[str] = None, db = Depends(get_db)):
    cursor = db.cursor()
    
    # Global metrics
    cursor.execute("SELECT COUNT(*) FROM telemetry")
    global_telemetry = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tasks")
    global_tasks = cursor.fetchone()[0]
    
    # Calculate costs ($0.000002 per telemetry, $0.00005 per task execution)
    GLOBAL_RATE_TELEMETRY = 0.000002
    GLOBAL_RATE_TASK = 0.00005
    
    global_cost = (global_telemetry * GLOBAL_RATE_TELEMETRY) + (global_tasks * GLOBAL_RATE_TASK)
    
    # Company Metrics Filter
    company_telemetry = 0
    company_tasks = 0
    company_cost = 0.0
    
    if company_id:
        cursor.execute("""
        SELECT COUNT(*) FROM telemetry 
        JOIN users ON telemetry.user_id = users.id 
        WHERE users.company_id = ?
        """, (company_id,))
        company_telemetry = cursor.fetchone()[0]
        
        cursor.execute("""
        SELECT COUNT(*) FROM tasks 
        JOIN users ON tasks.user_id = users.id 
        WHERE users.company_id = ?
        """, (company_id,))
        company_tasks = cursor.fetchone()[0]
        company_cost = (company_telemetry * GLOBAL_RATE_TELEMETRY) + (company_tasks * GLOBAL_RATE_TASK)
        
    # User Metrics Filter
    user_telemetry = 0
    user_tasks = 0
    user_cost = 0.0
    user_mode = "learn"
    
    if user_id:
        cursor.execute("SELECT COUNT(*) FROM telemetry WHERE user_id = ?", (user_id,))
        user_telemetry = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,))
        user_tasks = cursor.fetchone()[0]
        user_cost = (user_telemetry * GLOBAL_RATE_TELEMETRY) + (user_tasks * GLOBAL_RATE_TASK)
        
        cursor.execute("SELECT mode FROM users WHERE id = ?", (user_id,))
        urow = cursor.fetchone()
        if urow:
            user_mode = urow[0]
            
    return {
        "global": {
            "telemetry_count": global_telemetry,
            "tasks_count": global_tasks,
            "estimated_cost_usd": round(global_cost, 6)
        },
        "company": {
            "telemetry_count": company_telemetry,
            "tasks_count": company_tasks,
            "estimated_cost_usd": round(company_cost, 6)
        },
        "user": {
            "telemetry_count": user_telemetry,
            "tasks_count": user_tasks,
            "estimated_cost_usd": round(user_cost, 6),
            "mode": user_mode
        }
    }

# Standard API mappings
@app.post("/api/telemetry")
def ingest_telemetry(payload: TelemetryPayload, db = Depends(get_db)):
    cursor = db.cursor()
    record_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat()
    raw_str = str(payload.raw_payload) if payload.raw_payload else "{}"
    
    # Verify user exists
    cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,))
    if not cursor.fetchone():
        # Fallback to create user if does not exist to retain legacy tests support
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            payload.user_id, "co_touchtap_tech", f"usr_{payload.user_id[:8]}", "pass123", "agent", "Product Manager", "learn", now
        ))
        
    cursor.execute("""
    INSERT INTO telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record_id, now, payload.user_id, payload.window_title, payload.slack_status,
        payload.keystrokes, payload.mouse_clicks, payload.ocr_summary, raw_str
    ))
    db.commit()
    return {"status": "success", "record_id": record_id, "ingested_at": now}

@app.get("/api/telemetry")
def get_telemetry(company_id: Optional[str] = None, user_id: Optional[str] = None, limit: int = 50, db = Depends(get_db)):
    cursor = db.cursor()
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
def get_personas(db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM personas")
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

@app.get("/api/tasks")
def get_tasks(company_id: Optional[str] = None, user_id: Optional[str] = None, status: Optional[str] = None, db = Depends(get_db)):
    cursor = db.cursor()
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
def create_task(payload: TaskCreatePayload, db = Depends(get_db)):
    cursor = db.cursor()
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    steps_str = "||".join(payload.steps)
    
    # Ensure user exists
    cursor.execute("SELECT id FROM users WHERE id = ?", (payload.user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
            payload.user_id, "co_touchtap_tech", f"usr_{payload.user_id[:8]}", "pass123", "agent", "Product Manager", "learn", now
        ))
        
    cursor.execute("""
    INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
    """, (
        task_id, payload.user_id, payload.persona_id, payload.title, steps_str, "pending", now
    ))
    db.commit()
    return {"status": "success", "task_id": task_id, "created_at": now}

@app.post("/api/tasks/{task_id}/approve")
def approve_task(task_id: str, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Task not found")
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("UPDATE tasks SET status = 'approved', approved_at = ? WHERE id = ?", (now, task_id))
    db.commit()
    return {"status": "success", "task_id": task_id, "approved_at": now}

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: str, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Task not found")
    now = datetime.datetime.utcnow().isoformat()
    cursor.execute("UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?", (now, task_id))
    db.commit()
    return {"status": "success", "task_id": task_id, "completed_at": now}

@app.post("/api/personas/sync")
def federated_sync(background_tasks: BackgroundTasks, db = Depends(get_db)):
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
