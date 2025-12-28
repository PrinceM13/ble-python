#!/usr/bin/env python3
"""
Minimal BLE GATT server implementation for Raspberry Pi
"""

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import json
import sys

BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADV_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
STATE_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SWITCH_CHAR_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"

active_card = "Office"


class Characteristic(dbus.service.Object):
    """GATT Characteristic"""
    
    def __init__(self, bus, uuid, flags, service_path, char_path):
        self.uuid = uuid
        self.flags = flags
        self.service_path = service_path
        self.path = char_path
        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            "org.bluez.GattCharacteristic1": {
                "UUID": dbus.String(self.uuid),
                "Service": dbus.ObjectPath(self.service_path),
                "Flags": dbus.Array([dbus.String(f) for f in self.flags], signature="s"),
                "Descriptors": dbus.Array([], signature="o"),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.GattCharacteristic1":
            return self.get_properties()[interface].get(prop)
        raise dbus.exceptions.DBusException(f"Unknown property")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattCharacteristic1":
            return self.get_properties()[interface]
        raise dbus.exceptions.DBusException(f"Unknown interface")


class ReadCharacteristic(Characteristic):
    """Read-only characteristic"""
    
    @dbus.service.method(
        "org.bluez.GattCharacteristic1",
        in_signature="a{sv}",
        out_signature="ay"
    )
    def ReadValue(self, options):
        payload = json.dumps({
            "activeCard": active_card,
            "battery": 87
        }).encode()
        return dbus.Array([dbus.Byte(b) for b in payload], signature="y")


class WriteCharacteristic(Characteristic):
    """Write-only characteristic"""
    
    @dbus.service.method(
        "org.bluez.GattCharacteristic1",
        in_signature="aya{sv}",
        out_signature=""
    )
    def WriteValue(self, value, options):
        global active_card
        try:
            data = json.loads(bytes(value).decode())
            active_card = data.get("card", active_card)
            print(f"✅ Switched to: {active_card}")
        except Exception as e:
            print(f"❌ Failed to parse write: {e}")


class Service(dbus.service.Object):
    """GATT Service"""
    
    def __init__(self, bus, service_path, uuid):
        self.path = service_path
        self.uuid = uuid
        self.characteristics = []
        super().__init__(bus, self.path)

    def add_char(self, char):
        self.characteristics.append(char)

    def get_properties(self):
        return {
            "org.bluez.GattService1": {
                "UUID": dbus.String(self.uuid),
                "Primary": dbus.Boolean(True),
                "Characteristics": dbus.Array(
                    [dbus.ObjectPath(c.path) for c in self.characteristics],
                    signature="o"
                ),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.GattService1":
            return self.get_properties()[interface].get(prop)
        raise dbus.exceptions.DBusException(f"Unknown property")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattService1":
            return self.get_properties()[interface]
        raise dbus.exceptions.DBusException(f"Unknown interface")


class Application(dbus.service.Object):
    """GATT Application"""
    
    def __init__(self, bus):
        self.path = "/org/bluez/example"
        self.services = []
        super().__init__(bus, self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        objs = {}
        for service in self.services:
            objs[dbus.ObjectPath(service.path)] = service.get_properties()
            for char in service.characteristics:
                objs[dbus.ObjectPath(char.path)] = char.get_properties()
        return objs


class Advertisement(dbus.service.Object):
    """LE Advertisement"""
    
    def __init__(self, bus):
        self.path = "/org/bluez/example/advertisement0"
        super().__init__(bus, self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.LEAdvertisement1":
            props = {
                "Type": dbus.String("peripheral"),
                "ServiceUUIDs": dbus.Array([dbus.String(SERVICE_UUID)], signature="s"),
                "LocalName": dbus.String("NFC-Wallet-Dev"),
            }
            return props.get(prop)
        raise dbus.exceptions.DBusException("Unknown property")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.LEAdvertisement1":
            return {
                "Type": dbus.String("peripheral"),
                "ServiceUUIDs": dbus.Array([dbus.String(SERVICE_UUID)], signature="s"),
                "LocalName": dbus.String("NFC-Wallet-Dev"),
            }
        raise dbus.exceptions.DBusException("Unknown interface")

    @dbus.service.method("org.bluez.LEAdvertisement1", in_signature="", out_signature="")
    def Release(self):
        print("Advertisement released")


def find_adapter(bus):
    """Find BLE adapter"""
    om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/"), DBUS_OM_IFACE)
    objects = om.GetManagedObjects()
    for path, ifaces in objects.items():
        if GATT_MANAGER_IFACE in ifaces and LE_ADV_MANAGER_IFACE in ifaces:
            return path
    raise Exception("No BLE adapter found")


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    try:
        adapter = find_adapter(bus)
        print(f"✅ Found adapter: {adapter}")
    except Exception as e:
        print(f"❌ Failed to find adapter: {e}")
        sys.exit(1)

    try:
        # Build GATT hierarchy
        app = Application(bus)
        
        service = Service(bus, "/org/bluez/example/service0", SERVICE_UUID)
        
        state_char = ReadCharacteristic(
            bus,
            STATE_CHAR_UUID,
            ["read"],
            service.path,
            "/org/bluez/example/service0/char0"
        )
        switch_char = WriteCharacteristic(
            bus,
            SWITCH_CHAR_UUID,
            ["write"],
            service.path,
            "/org/bluez/example/service0/char1"
        )
        
        service.add_char(state_char)
        service.add_char(switch_char)
        app.add_service(service)

        # Create advertisement
        adv = Advertisement(bus)

        # Get managers
        adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter)
        gatt_mgr = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
        adv_mgr = dbus.Interface(adapter_obj, LE_ADV_MANAGER_IFACE)

        # Register
        print(f"📝 Registering application...")
        gatt_mgr.RegisterApplication(
            dbus.ObjectPath(app.path),
            {},
            timeout=10000
        )
        print("✅ Application registered")

        print(f"📝 Registering advertisement...")
        adv_mgr.RegisterAdvertisement(
            dbus.ObjectPath(adv.path),
            {},
            timeout=10000
        )
        print("✅ Advertisement registered")

        print("🔊 NFC-Wallet-Dev is advertising")
        GLib.MainLoop().run()

    except dbus.exceptions.DBusException as e:
        print(f"❌ DBus Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
