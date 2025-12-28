#!/usr/bin/env python3

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


class Descriptor(dbus.service.Object):
    """GATT Descriptor"""
    
    def __init__(self, bus, index, uuid, flags, characteristic):
        self.path = f"{characteristic.path}/desc{index}"
        self.uuid = uuid
        self.flags = flags
        self.characteristic = characteristic.path
        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            "org.bluez.GattDescriptor1": {
                "UUID": dbus.String(self.uuid),
                "Characteristic": dbus.ObjectPath(self.characteristic),
                "Flags": dbus.Array([dbus.String(f) for f in self.flags], signature="s"),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.GattDescriptor1":
            props = self.get_properties()[interface]
            if prop in props:
                return props[prop]
        raise dbus.exceptions.DBusException(f"Unknown property: {prop}")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattDescriptor1":
            return self.get_properties()[interface]
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")


class Characteristic(dbus.service.Object):
    """GATT Characteristic Base Class"""
    
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.uuid = uuid
        self.flags = flags
        self.service = service.path
        self.descriptors = []
        super().__init__(bus, self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_properties(self):
        return {
            "org.bluez.GattCharacteristic1": {
                "UUID": dbus.String(self.uuid),
                "Service": dbus.ObjectPath(self.service),
                "Flags": dbus.Array([dbus.String(f) for f in self.flags], signature="s"),
                "Descriptors": dbus.Array([dbus.ObjectPath(d.path) for d in self.descriptors], signature="o"),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.GattCharacteristic1":
            props = self.get_properties()[interface]
            if prop in props:
                return props[prop]
        raise dbus.exceptions.DBusException(f"Unknown property: {prop}")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattCharacteristic1":
            return self.get_properties()[interface]
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")


class StateCharacteristic(Characteristic):
    """Read-only characteristic for wallet state"""
    
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
    """Write-only characteristic for switching cards"""
    
    def __init__(self, bus, service):
        super().__init__(bus, 1, SWITCH_CHAR_UUID, ["write"], service)

    @dbus.service.method(
        "org.bluez.GattCharacteristic1",
        in_signature="aya{sv}",
        out_signature="",
    )
    def WriteValue(self, value, options):
        global active_card
        try:
            data = json.loads(bytes(value).decode())
            active_card = data.get("card", active_card)
            print(f"✅ Switched to: {active_card}")
        except Exception as e:
            print(f"❌ Failed to parse write value: {e}")


class Service(dbus.service.Object):
    """GATT Service"""
    
    def __init__(self, bus, index, uuid, primary=True):
        self.path = f"/org/bluez/example/service{index}"
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        super().__init__(bus, self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_properties(self):
        return {
            "org.bluez.GattService1": {
                "UUID": dbus.String(self.uuid),
                "Primary": dbus.Boolean(self.primary),
                "Characteristics": dbus.Array(
                    [dbus.ObjectPath(c.path) for c in self.characteristics],
                    signature="o"
                ),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.GattService1":
            props = self.get_properties()[interface]
            if prop in props:
                return props[prop]
        raise dbus.exceptions.DBusException(f"Unknown property: {prop}")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattService1":
            return self.get_properties()[interface]
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")


class Application(dbus.service.Object):
    """GATT Application - Implements ObjectManager"""
    
    def __init__(self, bus):
        self.path = "/org/bluez/example"
        self.services = []
        super().__init__(bus, self.path)

    def add_service(self, service):
        self.services.append(service)

    def get_managed_objects(self):
        managed_objects = {}
        for service in self.services:
            managed_objects[dbus.ObjectPath(service.path)] = service.get_properties()
            for char in service.characteristics:
                managed_objects[dbus.ObjectPath(char.path)] = char.get_properties()
                for desc in char.descriptors:
                    managed_objects[dbus.ObjectPath(desc.path)] = desc.get_properties()
        return managed_objects

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        return self.get_managed_objects()

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")


class Advertisement(dbus.service.Object):
    """BLE Advertisement"""
    
    def __init__(self, bus, index):
        self.path = f"/org/bluez/example/advertisement{index}"
        self.type = "peripheral"
        self.service_uuids = [SERVICE_UUID]
        self.local_name = "NFC-Wallet-Dev"
        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            "org.bluez.LEAdvertisement1": {
                "Type": dbus.String(self.type),
                "ServiceUUIDs": dbus.Array(
                    [dbus.String(u) for u in self.service_uuids],
                    signature="s"
                ),
                "LocalName": dbus.String(self.local_name),
            }
        }

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.LEAdvertisement1":
            props = self.get_properties()[interface]
            if prop in props:
                return props[prop]
        raise dbus.exceptions.DBusException(f"Unknown property: {prop}")

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.LEAdvertisement1":
            return self.get_properties()[interface]
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")

    @dbus.service.method("org.bluez.LEAdvertisement1", in_signature="", out_signature="")
    def Release(self):
        print("Advertisement released")


def find_adapter(bus):
    """Find the BLE adapter"""
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
        # Create the GATT application
        app = Application(bus)
        
        # Create service
        service = Service(bus, 0, SERVICE_UUID, primary=True)
        
        # Add characteristics
        service.add_characteristic(StateCharacteristic(bus, service))
        service.add_characteristic(SwitchCharacteristic(bus, service))
        
        # Add service to application
        app.add_service(service)

        # Create advertisement
        adv = Advertisement(bus, 0)

        # Get managers
        gatt_mgr = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            GATT_MANAGER_IFACE,
        )

        adv_mgr = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            LE_ADV_MANAGER_IFACE,
        )

        # Register GATT application
        print(f"📝 Registering GATT application at {app.path}...")
        gatt_mgr.RegisterApplication(
            dbus.ObjectPath(app.path),
            {},
            timeout=10000
        )
        print("✅ GATT application registered")

        # Register advertisement
        print(f"📝 Registering advertisement at {adv.path}...")
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
        print("\nTroubleshooting:")
        print("  sudo systemctl restart bluetooth")
        print("  sudo hciconfig hci0 up")
        print("  sudo python3 ble_wallet.py")
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
