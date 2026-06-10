markdown_content = """# PACCAR HASI Gateway ECU - Automated HIL Validation Suite

**Automated Pytest hardware-in-the-loop (HIL) validation suite for the HASI Gateway ECU.**

This repository contains a Python-based test architecture designed to eliminate the manual testing bottleneck for PACCAR's development cycle. It autonomously validates the HASI gateway's routing logic, ensures strict CAN Classic to CAN FD protocol translation accuracy, and automatically generates XML artifacts for enterprise CI/CT pipelines.

---

## ⚙️ Hardware Prerequisites & Setup

This electronic control unit(ECU)gateway validation suite requires a specific hardware setup to inject CAN signals and monitor CAN buses.

**Hardware Requirements:**
* **Vector Interface:** Vector Hardware Transceiver(VN1640A,VN1610, etc.)
* **System Under Test (SUT):** New Eagle RCM112 (programmed as the HASI Gateway)
* **Wiring:** Custom test harness (DB9 Female to Raptor Connectors)
  * *Note:* The harness utilizes a CAN_H and CAN_L twisted pair configuration(per SAE J1939 CAN wiring standards) for ensuring signal integrity

**Physical Setup Instructions:**
1. Connect the Vector device to the host PC via USB.
2. Connect the Vector CAN channels(DB9 male) to the custom test harness.
3. Plug the Raptor connectors securely into the New Eagle RCM112.

---

## 💻 Software Environment & Dependencies

**System Requirements:**
* Python 3.10+
* Windows OS (Required for Vector hardware drivers)

**Installation:**
1. Clone the repository:
   ```bash
   git clone [https://github.com/VladAndral/UWB_Capstone_PACCAR_HASI_Tester.git](https://github.com/VladAndral/UWB_Capstone_PACCAR_HASI_Tester.git)
   cd UWB_Capstone_PACCAR_HASI_Tester