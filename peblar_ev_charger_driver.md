# Peblar EV Charger Driver for Victron Venus OS

## Overview

This driver integrates **Peblar EV chargers** with **Victron Venus OS**
using the `dbus-modbus-client` framework.\
It communicates with the charger via **Modbus TCP** and exposes data and
controls on **D-Bus** so the Victron UI and other services can interact
with the charger.

The driver registers the service as:

`com.victronenergy.evcharger.peblar_<serial>`

This allows the charger to appear as a native EV charger device in the
Victron interface.

------------------------------------------------------------------------

# Features

-   Modbus TCP communication with Peblar chargers
-   Real‑time electrical measurements
-   Charging current control
-   Start / Stop charging
-   Persistent settings using the Victron settings service
-   Charging session timer
-   Compatible with the Victron EV charger UI

------------------------------------------------------------------------

# Communication

The Peblar charger exposes a **Modbus TCP server (port 502)**.

Characteristics:

  |Parameter    |Value|
  |------------|------------|
  |Protocol     |Modbus TCP|
  |Port         |502|
  |Unit ID      |1|
  |Byte order  |Big endian|

------------------------------------------------------------------------

# Supported Registers

## Information Registers

  Register   Description        D‑Bus Path
  ---------- ------------------ --------------------
  30050      Serial number      `/Serial`
  30062      Product number     `/ProductPn`
  30074      Firmware version   `/FirmwareVersion`
  30092      Phase count        `/PhaseCount`

------------------------------------------------------------------------

## Electrical Measurements

  Register   Description     D‑Bus Path
  ---------- --------------- ------------------
  30008      L1 power        `/Ac/L1/Power`
  30010      L2 power        `/Ac/L2/Power`
  30012      L3 power        `/Ac/L3/Power`
  30014      Total power     `/Ac/Power`
  30016      L1 voltage      `/Ac/L1/Voltage`
  30018      L2 voltage      `/Ac/L2/Voltage`
  30020      L3 voltage      `/Ac/L3/Voltage`
  30022      Total current   `/Current`
  30022      L1 current      `/Ac/L1/Current`
  30024      L2 current      `/Ac/L2/Current`
  30026      L3 current      `/Ac/L3/Current`

------------------------------------------------------------------------

## Energy Counters

  Register   Description      D‑Bus Path
  ---------- ---------------- ----------------------
  30000      Total energy     `/Ac/Energy/Forward`
  30004      Session energy   `/Session/Energy`

------------------------------------------------------------------------

## Charger Status

  Register   Description   D‑Bus Path
  ---------- ------------- ------------
  30110      CP State      `/Status`

CP states are translated to Victron EV charger status values:

  CP State   Meaning
  ---------- --------------
  A          Disconnected
  B          Connected
  C/D        Charging
  E/F/I      Fault

------------------------------------------------------------------------

# Control Registers

  Register   Description          D‑Bus Path
  ---------- -------------------- ---------------
  40000      ChargeCurrentLimit   `/SetCurrent`
  40000      ChargeCurrentLimit   `/StartStop`

This register represents the maximum charging current in **mA**.

------------------------------------------------------------------------

# D‑Bus Interface

Important exposed paths:

  Path                Description
  ------------------- ---------------------------------
  `/Mode`             Charger operating mode
  `/SetCurrent`       Charging current setpoint
  `/StartStop`        Start or stop charging
  `/Current`          Actual charging current
  `/Status`           Charger state
  `/MaxCurrent`       Maximum allowed current
  `/Position`         Charger direction
  `/Session/Energy`   Energy delivered during session
  `/Session/Time`     Charging session duration

------------------------------------------------------------------------

# Persistent Settings

The driver stores configuration using the Victron settings service:

`/Settings/Peblar`

Stored values:

  Setting      Path
  ------------ -------------------------------
  Position     `/Settings/Peblar/Position`
  MaxCurrent   `/Settings/Peblar/MaxCurrent`
  Mode         `/Settings/Peblar/Mode`

These values are restored when the driver restarts.

------------------------------------------------------------------------

# Charging Session Tracking

The driver automatically tracks charging sessions.

When charging current becomes positive:

-   A session timer starts
-   `/Session/Time` increases in seconds

When charging stops:

-   The session timer resets.

------------------------------------------------------------------------

# Device Identification

Each charger is identified using its serial number.

Example:

`peblar_25_20_A79_55E`

This ensures multiple Peblar chargers can operate on the same system.

------------------------------------------------------------------------

# Example D‑Bus Service

`com.victronenergy.evcharger.peblar_<serial>`

------------------------------------------------------------------------

# Debugging

Inspect the service using:

    dbus-spy

or:

    dbus -y com.victronenergy.evcharger.peblar_xxx

------------------------------------------------------------------------

# License

Example integration driver for Peblar EV chargers on Victron Venus OS.
