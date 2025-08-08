# NovaStar MCTRLR5 Plugin

The **NovaStar MCTRLR5** plugin allows control over the NovaStar MCTRLR5 LED controller via TCP/IP. You can switch inputs, toggle blackout/normal display modes, and adjust brightness levels programmatically using Stage Precision.

---

## 📡 Connection

Before using the plugin, ensure the correct **Device IP** and **Port** (default `5200`) are configured. Use the `Connect` action to test connectivity.

### Connection Status
- **Connected** – Communication with MCTRLR5 was successful.
- **Disconnected** – Failed to connect or device not responding.

---

## ⚙️ Plugin Actions

### 🔌 Connect
**Category:** Control  
**Description:** Attempts to establish a connection to the MCTRLR5 and verifies communication.

---

### 🔁 Switch Input
**Category:** Control  
**Parameters:**
- **Input Signal (Enum):**  
  - `SDI`
  - `HDMI`
  - `DVI`  

**Description:** Switches the input source of the device.

---

### 🌑 Switch Blackout / Normal
**Category:** Control  
**Parameters:**
- **Select Mode (Enum):**
  - `Blackout` – Disables output (black screen)
  - `Normal` – Enables normal display output

**Description:** Toggles blackout mode on the display.

---

### 💡 Set Brightness (%)
**Category:** Control  
**Parameters:**
- **Percentage (Integer):** `0`–`100`

**Description:** Adjusts the brightness of the output. Internally maps percentage to 8-bit value (0–255).

---

## 📊 Status Entities

| Entity Path                     | Description                        |
|-------------------------------|------------------------------------|
| Brightness                    | Current brightness level (0–255)   |
| Blackout Mode                 | `True` if blackout mode is active  |
| Normal Mode                   | `True` if normal mode is active    |
| Input Status/SDI             | `Enabled` or `Disabled`            |
| Input Status/HDMI            | `Enabled` or `Disabled`            |
| Input Status/DVI             | `Enabled` or `Disabled`            |

---

## 📥 Events

### 🔄 On Input Source Changed
**Token:** `source`  
**Emitted When:** Input is changed to SDI, HDMI, or DVI.

---

### 🔆 On Brightness Updated
**Token:** `value`  
**Emitted When:** Brightness is successfully updated.

---

### 🌓 On Blackout Switched
**Emitted When:** Blackout or normal mode is toggled.

---

## 🔄 Auto Polling

The plugin includes a background polling mechanism that runs every 5 seconds to verify device connectivity and update the status accordingly.

---

## ❗ Troubleshooting

- Ensure the correct IP and port are provided.
- Verify that the device is powered on and reachable on the network.
- Watch logs for raw command and response data for debugging.
- If the plugin fails to connect, check firewall or TCP restrictions.

---

## 🔧 Developer Notes

- The plugin uses `asyncio` for async TCP communication.
- Command encoding and parsing is handled using hexadecimal formatting and checksums.
- Device-specific responses are parsed to trigger status updates and events.

---

**Author:** Stage Precision  
**Version:** 1.0  
**SP Version Required:** 1.9.0

---
