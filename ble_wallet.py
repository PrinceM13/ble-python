import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import json

BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"

SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
STATE_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SWITCH_CHAR_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"

active_card = "Office"

# ---------- Advertisement ----------

class Advertisement(dbus.service.Object):
    PATH_BASE = "/org/bluez/example/advertisement"

    def __init__(self, bus, index):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        super().__init__(bus, self.path)

    @dbus.service.method(
        "org.freedesktop.DBus.Properties",
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface):
        if interface != "org.bluez.LEAdvertisement1":
            return {}

        return {
            "Type": "peripheral",
            "ServiceUUIDs": dbus.Array([SERVICE_UUID], signature="s"),
            "LocalName": "NFC-Wallet-Dev",
            "Includes": dbus.Array(["tx-power"], signature="s"),
        }

    @dbus.service.method(
        "org.bluez.LEAdvertisement1",
        in_signature="",
        out_signature="",
    )
    def Release(self):
        print("Advertisement released")

# ---------- GATT ----------

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/"
        self.services = []
        super().__init__(bus, self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.path] = service.get_properties()
            for ch in service.characteristics:
                response[ch.path] = ch.get_properties()
        return response

class Service(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/org/bluez/example/service{index}"
        self.bus = bus
        self.uuid = SERVICE_UUID
        self.primary = True
        self.characteristics = []
        super().__init__(bus, self.path)

    def add_characteristic(self, char):
        self.characteristics.append(char)

    def get_properties(self):
        return {
            "org.bluez.GattService1": {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": [c.path for c in self.characteristics]
            }
        }

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags):
        self.path = f"/org/bluez/example/char{index}"
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            "org.bluez.GattCharacteristic1": {
                "UUID": self.uuid,
                "Flags": self.flags,
            }
        }

class StateCharacteristic(Characteristic):
    def __init__(self, bus):
        super().__init__(bus, 0, STATE_CHAR_UUID, ["read"])

    @dbus.service.method("org.bluez.GattCharacteristic1",
                         in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        data = json.dumps({
            "activeCard": active_card,
            "battery": 87
        }).encode()
        return dbus.Array([dbus.Byte(b) for b in data], signature="y")

class SwitchCharacteristic(Characteristic):
    def __init__(self, bus):
        super().__init__(bus, 1, SWITCH_CHAR_UUID, ["write"])

    @dbus.service.method("org.bluez.GattCharacteristic1",
                         in_signature="aya{sv}", out_signature="")
    def WriteValue(self, value, options):
        global active_card
        payload = bytes(value).decode()
        data = json.loads(payload)
        active_card = data["card"]
        print("Switched to:", active_card)

# ---------- Main ----------

def find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"),
                        DBUS_OM_IFACE)
    objects = om.GetManagedObjects()
    for path, ifaces in objects.items():
        if GATT_MANAGER_IFACE in ifaces:
            return path
    raise Exception("BLE adapter not found")

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = find_adapter(bus)

    app = Application(bus)
    service = Service(bus, 0)
    service.add_characteristic(StateCharacteristic(bus))
    service.add_characteristic(SwitchCharacteristic(bus))
    app.add_service(service)

    adv = Advertisement(bus, 0)

    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        GATT_MANAGER_IFACE)

    adv_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        LE_ADV_MANAGER_IFACE)

    service_manager.RegisterApplication(app.path, {})
    adv_manager.RegisterAdvertisement(adv.path, {})

    print("✅ NFC-Wallet-Dev advertising")
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
