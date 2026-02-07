# MicroHack AI — Agentic Chat API

A LangGraph-based multi-agent system for port logistics management. Provides intelligent chat capabilities for carriers, terminal operators, and administrators.

## Overview

This AI service powers the chat functionality for the MicroHack port management system. It uses:

- **LangGraph** for multi-agent orchestration
- **Mistral AI** for LLM inference
- **PostgreSQL** for conversation checkpointing
- **FastAPI** for the REST API

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                            │
│                   (FastAPI - port 8000)                     │
├─────────────────────────────────────────────────────────────┤
│                      LangGraph Agents                       │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────┐ │
│  │Orchestrator│──│  Booking  │  │ Capacity  │  │ Guardian │ │
│  │   Agent   │  │   Agent   │  │   Agent   │  │  Agent   │ │
│  └───────────┘  └───────────┘  └───────────┘  └──────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Backend API (port 3000)                  │
│              (Bookings, Terminals, Analytics)               │
└─────────────────────────────────────────────────────────────┘
```

### LangGraph Workflow

```mermaid
graph TD
    START((Start)) --> ORCHESTRATOR[🎯 Orchestrator Agent]

    ORCHESTRATOR -->|intent: BOOKING| BOOKING[📋 Booking Agent]
    ORCHESTRATOR -->|intent: CAPACITY| CAPACITY[📊 Capacity Agent]
    ORCHESTRATOR -->|intent: HELP / OUT_OF_SCOPE| GUARDIAN[🛡️ Guardian Agent]

    BOOKING -->|tool calls + response| GUARDIAN
    CAPACITY -->|tool calls + response| GUARDIAN

    GUARDIAN -->|formatted response| END((End))

    subgraph "Agent Tools"
        BOOKING -.-> BT1[get_bookings_by_user]
        BOOKING -.-> BT2[prepare_booking_form]
        BOOKING -.-> BT3[get_all_bookings]
        BOOKING -.-> BT4[communicate_with_user]

        CAPACITY -.-> CT1[get_capacity_summary]
        CAPACITY -.-> CT2[get_terminal_details]
        CAPACITY -.-> CT3[check_availability]
    end

    subgraph "Backend API"
        BT1 & BT2 & BT3 --> API[(MicroHack Backend<br/>port 3000)]
        CT1 & CT2 & CT3 --> API
    end

    style START fill:#10b981,stroke:#059669,color:#fff
    style END fill:#10b981,stroke:#059669,color:#fff
    style ORCHESTRATOR fill:#3b82f6,stroke:#2563eb,color:#fff
    style BOOKING fill:#f59e0b,stroke:#d97706,color:#fff
    style CAPACITY fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style GUARDIAN fill:#ec4899,stroke:#db2777,color:#fff
```

### Agents

| Agent              | Purpose                                                                                |
| ------------------ | -------------------------------------------------------------------------------------- |
| **Orchestrator**   | Classifies intent (BOOKING/CAPACITY/HELP/OUT_OF_SCOPE) and routes to appropriate agent |
| **Booking Agent**  | Handles booking queries and form preparation                                           |
| **Capacity Agent** | Provides terminal capacity and availability info                                       |
| **Guardian Agent** | Formats final responses, handles translation                                           |

### User Roles

| Role         | Capabilities                                                         |
| ------------ | -------------------------------------------------------------------- |
| **CARRIER**  | View own bookings, create booking requests                           |
| **OPERATOR** | View bookings/capacity for assigned terminal + query other terminals |
| **ADMIN**    | Full access to all terminals, bookings, and system data              |

## API Endpoints

### Chat Endpoint

```http
POST /chat
Content-Type: application/json
X-API-Key: <AGENT_API_KEY>

{
  "message": "Show my bookings for today",
  "user_id": "uuid-of-user",
  "user_role": "CARRIER",
  "thread_id": "optional-conversation-id"
}
```

**Response:**

```json
{
  "response": [
    {
      "type": "text",
      "content": "Here are your bookings for today:\n\n| Truck | Date & Time | Terminal | Status |\n..."
    }
  ],
  "thread_id": "abc123",
  "ui_signal": null,
  "ui_payload": null
}
```

### UI Signals

When the AI needs to trigger a frontend action, it returns:

```json
{
  "response": [...],
  "ui_signal": "OPEN_BOOKING_FORM",
  "ui_payload": {
    "date": "2026-02-10",
    "time": "08:00",
    "terminal": "Terminal A",
    "terminal_id": "uuid-of-terminal"
  }
}
```

### Suggestions Endpoint (Admin Only)

```http
GET /suggestions
X-API-Key: <AGENT_API_KEY>
```

Returns AI-generated suggestions based on weekly capacity analysis:

```json
{
  "suggestions": [
    {
      "priority": "high",
      "icon": "🔴",
      "category": "Increase Capacity",
      "terminal": "Terminal A",
      "suggestion": "Terminal A exceeded 90% utilization Mon–Wed. Add 2 extra slots."
    }
  ],
  "generated_at": "2026-02-07T14:30:00.000000"
}
```

## Project Structure

```
microhack-ai/
├── api/
│   └── main.py              # FastAPI application
├── src/
│   ├── graph/
│   │   └── graph.py         # LangGraph workflow definition
│   ├── nodes/
│   │   ├── orchestrator.py  # Intent classification
│   │   ├── bookingAgent.py  # Booking operations
│   │   ├── capacityAgent.py # Capacity queries
│   │   └── guardianAgent.py # Response formatting
│   ├── prompts/
│   │   ├── orchestratorPrompts.py
│   │   ├── bookingPrompts.py
│   │   ├── capacityPrompts.py
│   │   └── guardianPrompts.py
│   ├── state/
│   │   └── AgentState.py    # LangGraph state definition
│   ├── services/
│   │   └── suggestion_service.py
│   └── utils/
│       ├── api_client.py    # Backend API client
│       ├── auth_tools.py    # Authentication
│       ├── booking_tools.py # Booking tools
│       ├── capacity_tools.py
│       └── terminal_tools.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Environment Variables

Create a `.env` file in the project root:

```env
# ═══════════════════════════════════════════════════════════
# REQUIRED — LLM Provider
# ═══════════════════════════════════════════════════════════
MISTRAL_API_KEY=your_mistral_api_key_here

# ═══════════════════════════════════════════════════════════
# REQUIRED — Backend Connection
# ═══════════════════════════════════════════════════════════
# URL of the MicroHack backend API
API_BASE_URL=http://localhost:3000

# Admin credentials for the AI to authenticate with the backend
ADMIN_EMAIL=admin@apcs-port.dz
ADMIN_PASSWORD=Admin@APCS2026!

# ═══════════════════════════════════════════════════════════
# REQUIRED — API Security
# ═══════════════════════════════════════════════════════════
# Secret key that frontend must send in X-API-Key header
AGENT_API_KEY=your_secret_api_key_here

# ═══════════════════════════════════════════════════════════
# REQUIRED — Database (for conversation checkpointing)
# ═══════════════════════════════════════════════════════════
# PostgreSQL connection string
CHECKPOINT_DB_URL=postgresql://postgres:123456789@localhost:5432/microhack_checkpoints

# ═══════════════════════════════════════════════════════════
# OPTIONAL — LangSmith Tracing (for debugging)
# ═══════════════════════════════════════════════════════════
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=microhack_ai
LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

## Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Running MicroHack backend on port 3000

### Setup

1. **Create virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Create `.env` file** (see Environment Variables section above)

4. **Start PostgreSQL** (for checkpointing):

   ```bash
   # Using Docker
   docker run -d --name microhack_postgres \
     -e POSTGRES_USER=postgres \
     -e POSTGRES_PASSWORD=123456789 \
     -e POSTGRES_DB=microhack_checkpoints \
     -p 5432:5432 \
     postgres:16-alpine
   ```

5. **Run the API:**
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   ```

The API will be available at `http://localhost:8000`.

### API Documentation

Once running, visit:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Testing

Send a test request:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_secret_api_key_here" \
  -d '{
    "message": "Show my bookings",
    "user_id": "test-user",
    "user_role": "CARRIER"
  }'
```

## Multi-Language Support

The AI automatically detects the user's language and responds in the same language. Supported:

- English
- French
- Arabic
- (and more — the AI will attempt to match the user's language)

Technical terms (terminal names, booking IDs, dates) are preserved as-is.

## Integration with Backend

The AI service requires the MicroHack backend to be running. It calls these backend endpoints:

| Endpoint               | Purpose                     |
| ---------------------- | --------------------------- |
| `POST /api/auth/login` | Authenticate on startup     |
| `GET /api/bookings`    | Fetch bookings              |
| `GET /api/terminals`   | Get terminal list           |
| `GET /api/users/:id`   | Resolve user details        |
| `GET /api/analytics/*` | Capacity and analytics data |

The AI authenticates as an admin user on startup and uses those credentials for all backend calls.

## License

Proprietary — APCS Port Management System
