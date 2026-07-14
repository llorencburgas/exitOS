# exitOS - Home Assistant Add-on

**exitOS** is an intelligent scheduler and optimizer designed for smart grids, energy management, and cost optimization. It integrates directly with Home Assistant to monitor, manage, and optimize your domestic energy assets (such as battery storage, solar panels, and controllable loads) while facilitating integration with the **eXiT Energy Community**.

---

## 🌟 Key Features

*   **Optimal Energy Scheduling:** Automate charging and discharging schedules of battery storage systems to minimize electricity bills.
*   **Asset Configuration:** Set up and parameterize local energy consumers, generators, and storage systems easily.
*   **Time Series Forecasting:** Build predictive models using local sensor data to forecast energy generation and consumption.
*   **Agentic LLM Support:** Converse in natural language with your smart grid assets using local models (like Llama 3.1 via Ollama).
*   **Integrated Web UI:** Access dashboards, forecasts, and schedules directly via Home Assistant Ingress.

---

## ⚙️ Configuration Parameters

The add-on can be configured using the following options under the **Configuration** tab:

*   **ollama_url** *(Optional)*: The URL of your local Ollama server (e.g., `http://192.168.1.50:11434/`). Required if you want to use the natural language agent features.
*   **ollama_model** *(Optional)*: The name of the model loaded in Ollama (e.g., `llama3.1:latest`).

---

## 📋 Requirements

*   Home Assistant 2023.5 or higher.
*   Energy sensors configured and active in your Home Assistant installation.
*   (Optional) A running instance of Ollama for LLM features.

---

## 👥 Support & Development

Developed by the **eXiT Research Group** at the **Universitat de Girona (UdG)**.
For source code and local development guidelines, please refer to the [GitHub Repository](https://github.com/llorencburgas/exitOS).