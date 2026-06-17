from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
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
@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "app": "Doppler Serverless Control Plane",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "database": DB_FILE,
        "pricing_warning": "No active databases running above serverless free tiers."
    }

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
