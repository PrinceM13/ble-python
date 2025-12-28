import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import json

BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
STATE_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SWITCH_CHAR_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"

active_card = "Office"

# -------------------------------------------------
# Advertisement
# -------------------------------------------------

class Advertisement(dbus.service.Object):
    PATH = "/org/bluez/example/advertisement0"

    def __init__(self, bus):
        super().__init__(bus, self.PATH)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != "org.bluez.LEAdvertisement1":
            return {}

        return {
            "Type": "peripheral",
            "ServiceUUIDs": dbus.Array([SERVICE_UUID], signature="s"),
            "LocalName": "NFC-Wallet-Dev",
        }

    @dbus.service.method("org.bluez.LEAdvertisement1")
    def Release(self):
        print("Advertisement released")

# -------------------------------------------------
# Application
# -------------------------------------------------

class Application(dbus.service.Object):
    PATH = "/org/bluez/example/app"

    def __init__(self, bus):
        self.services = []
        super().__init__(bus, self.PATH)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        objects = {}
        for service in self.services:
            objects[service.path] = service.get_properties()
            for ch in service.characteristics:
                objects[ch.path] = ch.get_properties()
        return objects

# -------------------------------------------------
# Service
# -------------------------------------------------

class Service(dbus.service.Object):
    def __init__(self, bus):
        self.path = f"{Application.PATH}/service0"
        self.uuid = SERVICE_UUID
        self.primary = True
        self.characteristics = []
        super().__init__(bus, self.path)

    def add_characteristic(self, ch):
        self.characteristics.append(ch)

    def get_properties(self):
        return {
            "org.bluez.GattService1": {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.path for c in self.characteristics],
                    signature="o"
                ),
            }
        }

# -------------------------------------------------
# Characteristic Base
# -------------------------------------------------

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.uuid = uuid
        self.flags = flags
        self.service = service.path
        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            "org.bluez.GattCharacteristic1": {
                "UUID": self.uuid,
                "Flags": dbus.Array(self.flags, signature="s"),
                "Service": dbus.ObjectPath(self.service),
            }
        }

# -------------------------------------------------
# Characteristics
# -------------------------------------------------

class StateCharacteristic(Characteristic):
    def __init__(self, bus, service):
        super().__init__(bus, 0, STATE_CHAR_UUID, ["read"], service)

    @dbus.service.method(
        "org.bluez.GattCharacteristic1",
        in_signature="a{sv}",
        out_signature="ay",
    )
    def ReadValue(self, options):
        payload = json.dumps({
            "activeCard": active_card,
            "battery": 87
        }).encode()
        return dbus.Array([dbus.Byte(b) for b in payload], signature="y")

class SwitchCharacteristic(Characteristic):
    def __init__(self, bus, service):
        super().__init__(bus, 1, SWITCH_CHAR_UUID, ["write"], service)

    @dbus.service.method(
        "org.bluez.GattCharacteristic1",
        in_signature="aya{sv}",
        out_signature="",
    )
    def WriteValue(self, value, options):
        global active_card
        data = json.loads(bytes(value).decode())
        active_card = data["card"]
        print("Switched to:", active_card)

# -------------------------------------------------
# Helpers
# -------------------------------------------------

def find_adapter(bus):
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
    objects = om.GetManagedObjects()
    for path, ifaces in objects.items():
        if (GATT_MANAGER_IFACE in ifaces and
            LE_ADV_MANAGER_IFACE in ifaces):
            return path
    raise Exception("No BLE adapter found")

# -------------------------------------------------
# Main
# -------------------------------------------------

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = find_adapter(bus)

    app = Application(bus)
    service = Service(bus)

    service.add_characteristic(StateCharacteristic(bus, service))
    service.add_characteristic(SwitchCharacteristic(bus, service))
    app.add_service(service)

    adv = Advertisement(bus)

    gatt_mgr = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        GATT_MANAGER_IFACE,
    )

    adv_mgr = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        LE_ADV_MANAGER_IFACE,
    )

    gatt_mgr.RegisterApplication(app.PATH, {})
    adv_mgr.RegisterAdvertisement(adv.PATH, {})

    print("✅ NFC-Wallet-Dev is advertising")
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
