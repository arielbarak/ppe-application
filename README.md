# PPE Polling System

A cryptographic polling framework that guarantees vote integrity without trusting the server. Based on the **Public Verification of Private Effort** protocol described by Alberini, Moran, and Rosen (2014).

Every vote is backed by a peer-to-peer proof of effort, and anyone can independently verify the published results by reconstructing the certification graph from public parameters alone.

## Quick Start

```bash
docker compose up --build
```

- **Frontend** &rarr; http://localhost:3000
- **Backend API** &rarr; http://localhost:8000
- **API docs** &rarr; http://localhost:8000/docs

## Local Run Guide

### Prerequisites

- Python 3.10+
- Node.js 22+

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at http://localhost:8000 (docs at http://localhost:8000/docs).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at http://localhost:3000.

## Architecture

### Blind Relay Design

The server is a **blind signaling relay**. It routes WebSocket messages between peers but never inspects PPE challenge content. Trust is established directly between the two clients via ECDSA binding and commit-reveal:

```
Peer A  ──── [opaque PPE payload] ────►  Server  ────►  Peer B
                                        (no inspection)
```

### 6-Phase Protocol

Phase 1 - Announcement: Pollster creates a session with questions, edge probability p, and thresholds eta_E / eta_V.

Phase 2 - Registration: Responders solve a CAPTCHA and register their public key.

Phase 3 - Certification: Peers perform symmetric PPE challenges with their hash-determined neighbors.

Phase 4 - Response: Certified responders submit encrypted votes with collected peer signatures.

Phase 5 - Results: Pollster publishes all data (votes, graph, signatures) as a public bulletin.

Phase 6 - Verification: Anyone reconstructs the ideal graph and independently verifies the tally.

### Certification Graph

Edges aren't assigned by the pollster. They're derived deterministically:

```
edge(i, j) exists  <=>  SHA-256(min(i,j) : max(i,j))  <=  p * MAX_HASH
```

Both endpoints compute the same hash, so they independently agree on the edge without coordination. During verification, a third party recomputes this ideal graph from scratch and compares it to the published data to detect fabricated or omitted edges.

### Key Thresholds

- **kappa** (security parameter): drives all other parameters. Higher kappa means stronger security guarantees but stricter requirements. Typical values: 40 (low), 80 (medium), 128 (high).
- **eta_E** (effort threshold): if a node fails more than this fraction of its PPE challenges, it's excluded from the tally. Also controls PPE difficulty via the formula `difficulty = 1 - eta_E`. Lower eta_E (stricter exclusion) means harder challenges, higher eta_E (more lenient) means easier challenges.
- **eta_V** (validity threshold): if too many nodes get excluded, the entire poll is declared INVALID
- **C\*** (adversary advantage): `C* = (1 + eta_V) / (1 - eta_V)` defines the maximum ratio by which an adversary can skew results

### Security Parameter Calculation (Theorem 4.4)

The system provides utilities to compute optimal parameters based on the security parameter kappa and expected responder count m. The API endpoints `/api/poll/params/recommend` and `/api/poll/params/compute` help determine:

- **Expected degree d**: scales as `2*ln(m) + kappa/16` to ensure graph connectivity
- **Edge probability p**: derived as `d/(m-1)` from the expected degree
- **eta_E**: computed using Chernoff bounds to ensure honest nodes pass with probability `1 - 2^(-kappa)`
- **eta_V**: scaled based on kappa and m to bound adversary advantage

Example configurations:

For a small poll (10 responders, low security): expected degree d=7.1 means each node verifies with about 7 neighbors. Edge probability p=0.79 creates a dense graph. Effort threshold eta_E=0.20 allows up to 20% PPE failures before exclusion. Validity threshold eta_V=0.029 keeps adversary advantage C* under 1.06 (6% max skew).

For a medium poll (100 responders, medium security): d=14.2 neighbors per node, p=0.14 edge probability. Stricter eta_E=0.15 and eta_V=0.017 bound C* to 1.035 (3.5% max skew).

For a large poll (1000 responders, high security): d=21.8 neighbors, p=0.022 (sparser graph). Tight eta_E=0.14 and eta_V=0.012 achieve C*=1.024 (2.4% max skew).

Use `GET /api/poll/params/recommend?expected_responders=100&security_level=medium` to get recommended parameters for your poll.

## Project Structure

```
backend/
  app/
    crypto/          # graph.py (edge determination), verification.py (Protocol 6),
                     # signatures.py (ECDSA), keys.py (key generation)
    ppe/             # base.py (abstract interface), captcha.py (math CAPTCHA),
                     # coordinator.py (state machine), __init__.py (registry)
    api/routes/      # One file per protocol phase (poll, registration, certification,
                     # response, results, verification)
    storage/         # In-memory storage (thread-safe)
    models/          # Pydantic request/response models
frontend/
  src/services/
    symmetricCaptcha.ts  # Core PPE protocol (ECDSA binding, commit-reveal, state machine)
    ppe/
      PPEProvider.ts         # Pluggable task interface
      MathCaptchaProvider.ts # Default implementation
      registry.ts            # Provider registry
```

## Extensibility: Adding a New PPE Module

The system uses a provider/registry pattern. To add a new proof-of-effort type:

### Backend

1. Create a class inheriting from `PPEBase` in `backend/app/ppe/`:

```python
from app.ppe.base import PPEBase

class StorageProofPPE(PPEBase):
    def generate(self):
        # self._difficulty is set from eta_E: difficulty = 1 - eta_E
        # Use it to scale challenge complexity
        return {"question": ..., "solution": ..., "difficulty": self._difficulty}

    def validate(self, challenge, solution):
        return ...
```

2. Register it in `backend/app/ppe/__init__.py`:

```python
from .storage_proof import StorageProofPPE
register_ppe("storage_proof", StorageProofPPE)
```

### Frontend

1. Implement the `PPEProvider` interface in `frontend/src/services/ppe/`:

```typescript
import type { PPEProvider } from './PPEProvider';

export const StorageProofProvider: PPEProvider = {
  type: 'storage_proof',
  label: 'Storage Proof',
  // difficulty (0.0-1.0) is derived from eta_E as (1 - eta_E)
  generateChallenge(seed, difficulty = 0.5) { ... },
  validateSolution(seed, solution, difficulty = 0.5) { ... },
  extractDisplay(challengeImage) { ... },
};
```

2. Register it in `frontend/src/services/ppe/registry.ts`:

```typescript
import { StorageProofProvider } from './StorageProofProvider';
registerProvider(StorageProofProvider);
```

3. Set `ppe_type: "storage_proof"` when creating a poll (Protocol 1).

## References

Alberini, R., Moran, T., & Rosen, A. (2014). *Public Verification of Private Effort*. Interdisciplinary Center Herzliya.
