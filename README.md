# Doppler AI - On-Desktop Self-Learning Agent Ecosystem 🚀

Doppler is a secure, three-tier, serverless SaaS platform designed to observe on-desktop user interactions, model professional behaviors into reusable shadow personas, and run automated autopilot flows with strict Human-in-the-Loop (HITL) safety gates and federated learning synchronization.

---

## 🏗️ High-Level System Architecture

Doppler's architecture is built on a clean decoupling of **Identity/Cognition (SaaS Cloud Control Plane)** from **Observation & Execution (Local Desktop Client)**.

```
       [USER WORKSPACE: Slack / Browser / IDE]
                         │
                      Observe
                         ▼
        ┌───────────────────────────────────┐
        │  Doppler-Observer (Local Daemon)  │  <── Scrub PII Locally
        └───────────────────────────────────┘
                         │
                    POST Telemetry
                         ▼
        ┌───────────────────────────────────┐
        │    Doppler-Cloud Control Plane    │  (FastAPI on Google Cloud Run)
        │   └─> SQLite/Firestore Storage    │
        └───────────────────────────────────┘
                         │
                 Aggregate & Sync
                         ▼
        ┌───────────────────────────────────┐
        │   Collective SaaS Persona Hub     │  (Digital Marketer, PM, Lead Dev)
        └───────────────────────────────────┘
                         │
                    Deploy Plan
                         ▼
        ┌───────────────────────────────────┐
        │  Doppler-Executor (Actuator)      │  <── Human-in-the-Loop Approval
        └───────────────────────────────────┘
                         │
                     Execute OS
                         ▼
       [USER WORKSPACE: Slack / Browser / IDE]
```

### 1. Doppler-Observer (Client-Side Learning)
A lightweight background daemon that runs on the user's host machine. It polls focused window titles, keystrokes, mouse events, and Slack status to understand active context. It scrubs sensitive PII (tokens, keys, credit cards) locally on-device before uploading anonymized telemetry packets.

### 2. Doppler-Control Plane (Serverless Control Plane)
A secure FastAPI application deployed to **Google Cloud Run**. It ingests telemetry, manages custom/pre-defined personas, structures task queues, and runs the "Federated Aggregate Engine" which uses collective cross-user patterns to refine pre-defined role templates.

### 3. Doppler-Executor (Client-Side Actuator & Safety Gate)
A sandboxed local client that pulls active execution plans. It includes a mandatory **Human-in-the-Loop (HITL) Policy Gate** that alerts the user and halts execution for explicit signature approval before any local OS simulation or interaction.

---

## ⚡ Google Cloud Infrastructure Setup & Deployment

Doppler is designed to run entirely on GCP's serverless tiers, guaranteeing **zero monthly running costs** during inactive or low-volume periods.

### Google Cloud Components Created:
1. **Google Cloud Project:** `doppler-self-learning-73466`
2. **Artifact Registry:** Secure repository hosting the containerized Docker server image.
3. **Cloud Build:** Remote building pipeline that compiles the FastAPI Docker container in the cloud without needing local Docker.
4. **Google Cloud Run:** Serverless container execution plane hosting the FastAPI service with automatic scaling to 0.

### Automated Deployment Script
To deploy updates or spin up a new clone of the infrastructure, run:
```bash
./deploy.sh
```

---

## 💸 Cost-Control & Cost Split Breakdown

To avoid costly recurring GCP dashboards or running unexpected bills, Doppler's infrastructure has been architected under **strict serverless scale-to-zero parameters**. 

When the platform is not actively in use, **its run-rate is exactly $0.00/month**.

### Monthly Cost Split & Free-Tier Quotas:

| GCP Resource | Configuration / Role | Monthly Cost | Free Tier Quota / Details |
| :--- | :--- | :--- | :--- |
| **Google Cloud Run** | FastAPI Serverless Server | **$0.00** | • Up to **2 million requests/month** free.<br>• 180,000 vCPU-seconds & 360,000 GB-seconds free.<br>• **Scale-to-zero:** $0.00 cost when idle. |
| **Artifact Registry** | Container Image Storage | **$0.00** | • First **500 MB** of container storage is **100% free**.<br>• Doppler container is ~140 MB. |
| **Cloud Build** | Cloud Compilation | **$0.00** | • First **120 build-minutes per day** are **100% free**.<br>• Doppler deploys in under 1 minute. |
| **Datastore / Firestore** | Serverless SQLite Database | **$0.00** | • First **1 GB** of storage is **100% free**.<br>• 50,000 reads & 20,000 writes/day are **100% free**. |
| **Network Egress** | Server Response Traffic | **$0.00** | • First **100 GB** of internet egress per month is **100% free**. |
| **TOTAL RUN-RATE** | **Idle / Under Quotas** | **$0.00** | **Fully covered by Google Cloud Free Tier.** |

### Cost Prevention Rules Integrated:
* **No Managed SQL (Cloud SQL):** Traditional PostgreSQL instances on GCP cost a minimum of $15–$50/month even if they handle zero queries. Doppler avoids this by using SQLite or serverless Firestore.
* **No Compute Engine (VMs):** Avoids 24/7 VM run-rates (~$15/month per instance).
* **No static External IPs:** Dynamic Cloud Run endpoints avoid static IPv4 reservation fees ($7.30/month).

---

## 🚀 How to Use Doppler (Detailed Step-by-Step)

Ensure you have your Python virtual environment activated:
```bash
source venv/bin/activate
```

### 1. Verify Connectivity
Run a live status handshake against your GCP-deployed Cloud Run backend:
```bash
python3 doppler-client/doppler_client.py --server https://doppler-server-60115314704.us-central1.run.app status
```

### 2. Start the On-Desktop Observer (Learner Daemon)
To start capturing desktop state changes and Slack window interactions to build context:
```bash
python3 doppler-client/doppler_client.py --server https://doppler-server-60115314704.us-central1.run.app observe
```
*Observe logs roll in as you switch active windows. PII filtering occurs locally before upload.*

### 3. Query the SaaS Persona Directory
To inspect pre-defined role templates (PM, Lead Dev, Marketer) and review their underlying behavioral prompts:
```bash
python3 doppler-client/doppler_client.py --server https://doppler-server-60115314704.us-central1.run.app personas
```

### 4. Record a Custom Action Flow
To record a custom, multi-step sequential desktop workflow to train your clone:
```bash
python3 doppler-client/doppler_client.py --server https://doppler-server-60115314704.us-central1.run.app record
```
*Enter steps like 'Synthesize specifications', 'Draft test suites', and push the sequence directly to the cloud.*

### 5. Execute Autopilot with Human-In-The-Loop (HITL) Gate
To fetch and run the workflow we just uploaded:
```bash
python3 doppler-client/doppler_client.py --server https://doppler-server-60115314704.us-central1.run.app run
```
*The client loads the steps, detects a `PENDING` state, alerts you with a security warnings, and prompts for explicit 'y/n' approval before starting sandboxed execution.*

### 6. Trigger Federated Collective Learning Optimizations
To simulate the SaaS model compiling telemetry across thousands of professional users to dynamically "upgrade" pre-defined role souls:
```bash
python3 doppler-client/doppler_client.py --server https://doppler-server-60115314704.us-central1.run.app sync
```
