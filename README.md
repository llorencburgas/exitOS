# exitOS: Smart Grid Scheduler & Optimizer for Home Assistant

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Home Assistant Add-on](https://img.shields.io/badge/Home_Assistant-Add--on-blue.svg)](https://www.home-assistant.io/)
[![Supports aarch64](https://img.shields.io/badge/aarch64-yes-green.svg)](#)
[![Supports amd64](https://img.shields.io/badge/amd64-yes-green.svg)](#)

**exitOS** is a high-performance Home Assistant add-on designed to manage, simulate, and optimize smart sensor and energy networks. It serves as a core management layer for local energy resources (such as photovoltaic generation, battery storage systems, and domestic loads) and enables seamless integration and collaboration within the **eXiT Energy Community**.

For comprehensive documentation, visit the [eXiTOS Documentation Portal](https://siragordillo.github.io/eXiT_OS_Documentation/).

---

## 🚀 Key Features

*   **Asset Abstraction & Registry:** Model your energy resources (prosumers, consumers, generators, and battery storage) through clean, hardware-agnostic class definitions.
*   **Predictive Forecasting (Machine Learning):** Build, train, and run predictive ML models (Random Forest, Extra Trees, etc.) directly on historical sensor data to forecast consumption and generation patterns.
*   **Optimal Scheduler & Flexibility Management:** Execute mathematical optimization algorithms to plan battery charge/discharge cycles and schedule controllable assets, maximizing self-consumption and cost efficiency.
*   **Decentralized Community Ledger:** Share and record transactions securely via an integrated blockchain interface to support the eXiT Energy Community mechanisms.
*   **Agentic LLM Integration:** Connect directly to local large language models (such as Ollama hosting `llama3.1`) to inspect sensor states, configurations, and optimization statuses through natural language.
*   **Elegant Dashboard Interface:** Monitor and control all features using an interactive, modern web interface fully embedded inside Home Assistant as an Ingress panel.

---

## 📂 Repository Structure

The project code is organized as follows:

```text
├── exitos/                     # Main Home Assistant Add-on directory
│   ├── config.yaml             # Add-on configuration schema, ingress, and parameters
│   ├── Dockerfile              # Containerization definition
│   ├── README.md               # User manual displayed inside Home Assistant
│   └── rootfs/                 # Files copied directly into the container's filesystem
│       ├── server.py           # Ingress web server (Bottle framework) & API routing
│       ├── sqlDB.py            # Local database manager wrapper (SQLite)
│       ├── blockchain.py       # Blockchain ledger integration
│       ├── logging_config.py   # System-wide logging utilities
│       ├── inspect_pkl.py      # Diagnostic utility to inspect serialized ML models
│       ├── abstraction/        # Hardware/Device abstraction and registry classes
│       ├── forecast/           # ML models, training pipelines, and forecasting engines
│       ├── optimization/       # Mathematical optimization models and flexibility schedulers
│       ├── llm/                # LLM agentic tool definitions and engine
│       └── www/                # Ingress UI templates, styles, and static assets
├── .venv/                      # Python local virtual environment (recommended for development)
├── requirements.txt            # Python dependencies (scikit-learn, pandas, joblib, bottle, etc.)
└── README.md                   # This file (GitHub Repository documentation)
```

---

## 🛠️ Installation

You can install exitOS directly on your Home Assistant Supervisor:

1. Copy this repository URL: `https://github.com/llorencburgas/exitOS.git`
2. In Home Assistant, navigate to **Settings** > **Add-ons** > **Add-on Store**.
3. Click the three dots in the top-right corner and select **Repositories**.
4. Paste the URL and click **Add**.
5. Find **exitOS** in the list, click **Install**, and configure the options.

[![Open your Home Assistant instance and show the add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https://github.com/llorencburgas/exitOS.git)

---

## 💻 Local Development

To set up a local development and testing environment outside of a Home Assistant installation:

1. Clone the repository:
   ```bash
   git clone https://github.com/llorencburgas/exitOS.git
   cd exitOS
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the development server locally:
   ```bash
   python exitos/rootfs/server.py
   ```
   *The server will be reachable at `http://localhost:55023`.*

### Diagnostics Utility
A utility script [inspect_pkl.py](./exitos/rootfs/inspect_pkl.py) is included to inspect machine learning models or historical datasets serialized as `.pkl` files:
```bash
python exitos/rootfs/inspect_pkl.py <path_to_file.pkl>
```

---

## 👥 Support & Development

Developed by the **eXiT Research Group** at the **Universitat de Girona (UdG)**.

If you find any bugs or wish to contribute to the optimization and scheduling algorithms, please open an Issue or pull request.
