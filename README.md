# PACCAR HASI Gateway ECU - Automated HIL Validation Suite

**Automated Pytest hardware-in-the-loop (HIL) validation suite for the HASI Gateway ECU.**

This repository contains a Python-based test architecture designed to eliminate the manual testing bottleneck for PACCAR's development cycle. It autonomously validates the HASI gateway's routing logic, ensures strict CAN Classic to CAN FD protocol translation accuracy, and automatically generates XML artifacts for enterprise CI/CT pipelines.

---

## ⚙️ Hardware Prerequisites & Setup

This electronic control unit (ECU) gateway validation suite requires a specific hardware setup to inject CAN signals and monitor CAN buses.

**Hardware Requirements:**
* **Vector Interface:** Vector Hardware Transceiver (VN1640A, VN1610, etc.)
  * *Bus Termination:* 120Ω bus termination is handled internally by the Vector hardware. **Do not** add external termination resistors to the physical harness.
* **System Under Test (SUT):** New Eagle RCM112 (programmed as the HASI Gateway)
* **Wiring:** Custom test harness (DB9 Female to Raptor Connectors)
  * *Physical Layer Note:* The harness utilizes a CAN_H and CAN_L twisted pair configuration (per SAE J1939 CAN wiring standards) for ensuring signal integrity.

**Physical Setup Instructions:**
1. Connect the Vector device to the host PC via USB.
2. Connect the Vector CAN channels (DB9 male) to the custom test harness.
3. Plug the Raptor connectors securely into the New Eagle RCM112.

---

## 💻 Software Environment & Dependencies

**System Requirements:**
* Python 3.10+
* Windows OS (Required for Vector hardware drivers)

**Installation:**
1. Clone the repository:
```bash
git clone https://github.com/VladAndral/UWB_Capstone_PACCAR_HASI_Tester.git
cd UWB_Capstone_PACCAR_HASI_Tester
```

2. Install the required Python dependencies:
```bash
pip install -r requirements.txt
```
*(Note: This includes `pytest`, `pytest-check`, `python-can`, and required Vector API wrappers.)*

**Database Configuration:**
* Ensure the PACCAR `.dbc` database file is placed in the `./database/` directory before execution so the parser can extract the gateway routing rules.

---

## 🚀 Execution Instructions

The suite can be run using the standard `pytest` CLI with our custom configuration hooks. 

**Standard Hardware-in-the-Loop Test:**
To execute the standard test suite with physical hardware connected using the default database (`./HASI_Primary_ALL_CAN.dbc`):
```bash
pytest tests/
```

**Custom Database Path:**
To run the suite using a different database file:
```bash
pytest tests/ --dbcPath ./path/to/your/custom_database.dbc
```

**Virtual Hardware Bypass Mode:**
If physical hardware (Vector/ECU) is unavailable, you can run the suite in virtual mode. This bypasses hardware requirements and intentionally mutates 20% of the TX payloads to verify the script’s pass/fail error-catching logic.
```bash
pytest tests/ --virtual true
```

---

## 📊 CI/CT Artifact Output

Upon completion of the test suite, the host PC automatically aggregates routing successes, timeout failures (1.0s threshold), and mutated frame failures. 

A standard **JUnit XML Report** is generated and saved to:
`./reports/gateway_test_results.xml`

This artifact is fully formatted for downstream integration into PACCAR's enterprise deployment and CI/CT pipelines.