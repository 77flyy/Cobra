## Installation

Follow these steps to set up Cobra locally. Commands are cross‑platform (Windows PowerShell, macOS, Linux).

### Prerequisites

- Python 3.10+
- Git
- pip

### 1) Clone the repository and install requirements

```bash
git clone https://github.com/FLOCK4H/Cobra
cd Cobra
pip install -r req.txt
```

### 2) Install the CobraRouter module (for programmatic use)

If you plan to import and use Cobra as a library, install the router package locally:

```bash
cd CobraRouter
pip install .
```

You can later reinstall after local edits with:

```bash
pip uninstall cobra-router -y
pip install .
```

### 3) Optional: CLI configuration

To use Cobra’s CLI, set these variables in `secrets.env`:

```bash
RUN_AS_CLI=True
HTTP_RPC="https://api.apewise.org/rpc?api-key="

# CLI CONFIG SECTION
PRIVATE_KEY=2wY3abcde5Pj4xxxxxxxxxxxxxxxxxxxxxxxxxxxx
SLIPPAGE=30               # 1..100
PRIORITY_FEE_LEVEL="high"  # low | medium | high | turbo
```

Run the CLI from the repo root:

```bash
python main.py
```

> For Telegram hosting (CobraNET), you’ll need PostgreSQL installed for database operations. See the root `README.md` for details.
