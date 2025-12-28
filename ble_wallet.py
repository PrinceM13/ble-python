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

# Introspection XML for proper DBus interface exposure
ADAPTER_INTROSPECT = """
<node>
    <interface name="org.freedesktop.DBus.ObjectManager">
        <method name="GetManagedObjects">
            <arg type="a{oa{sa{sv}}}" direction="out"/>
        </method>
    </interface>
</node>
"""

SERVICE_INTROSPECT = """
<node>
    <interface name="org.bluez.GattService1">
        <property name="UUID" type="s" access="read"/>
        <property name="Primary" type="b" access="read"/>
        <property name="Characteristics" type="ao" access="read"/>
    </interface>
    <interface name="org.freedesktop.DBus.Properties">
        <method name="Get">
            <arg type="s" direction="in"/>
            <arg type="s" direction="in"/>
            <arg type="v" direction="out"/>
        </method>
        <method name="GetAll">
            <arg type="s" direction="in"/>
            <arg type="a{sv}" direction="out"/>
        </method>
    </interface>
</node>
"""

CHAR_INTROSPECT = """
<node>
    <interface name="org.bluez.GattCharacteristic1">
        <method name="ReadValue">
            <arg type="a{sv}" direction="in"/>
            <arg type="ay" direction="out"/>
        </method>
        <method name="WriteValue">
            <arg type="ay" direction="in"/>
            <arg type="a{sv}" direction="in"/>
        </method>
        <property name="UUID" type="s" access="read"/>
        <property name="Service" type="o" access="read"/>
        <property name="Flags" type="as" access="read"/>
    </interface>
    <interface name="org.freedesktop.DBus.Properties">
        <method name="Get">
            <arg type="s" direction="in"/>
            <arg type="s" direction="in"/>
            <arg type="v" direction="out"/>
        </method>
        <method name="GetAll">
            <arg type="s" direction="in"/>
            <arg type="a{sv}" direction="out"/>
        </method>
    </interface>
</node>
"""

ADV_INTROSPECT = """
<node>
    <interface name="org.bluez.LEAdvertisement1">
        <method name="Release"/>
        <property name="Type" type="s" access="read"/>
        <property name="ServiceUUIDs" type="as" access="read"/>
        <property name="LocalName" type="s" access="read"/>
    </interface>
    <interface name="org.freedesktop.DBus.Properties">
        <method name="Get">
            <arg type="s" direction="in"/>
            <arg type="s" direction="in"/>
            <arg type="v" direction="out"/>
        </method>
        <method name="GetAll">
            <arg type="s" direction="in"/>
            <arg type="a{sv}" direction="out"/>
        </method>
    </interface>
</node>
"""

# -------------------------------------------------
# Advertisement
# -------------------------------------------------

class Advertisement(dbus.service.Object):
    PATH = "/org/bluez/example/advertisement0"

    def __init__(self, bus):
        super().__init__(bus, self.PATH)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        props = self.GetAll(interface)
        return props.get(prop)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != "org.bluez.LEAdvertisement1":
            raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")

        return {
            "Type": dbus.String("peripheral"),
            "ServiceUUIDs": dbus.Array([dbus.String(SERVICE_UUID)], signature="s"),
            "LocalName": dbus.String("NFC-Wallet-Dev"),
        }

    @dbus.service.method("org.bluez.LEAdvertisement1", in_signature="", out_signature="")
    def Release(self):
        print("Advertisement released")

# -------------------------------------------------
# Application
# -------------------------------------------------

class Application(dbus.service.Object):
    PATH = "/org/bluez/example/app"

    def __init__(self, bus):
        self.bus = bus
        self.services = []
        super().__init__(bus, self.PATH)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        objects = {}
        for service in self.services:
            objects[dbus.ObjectPath(service.path)] = service.get_properties()
            for ch in service.characteristics:
                objects[dbus.ObjectPath(ch.path)] = ch.get_properties()
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
        self.bus = bus
        super().__init__(bus, self.path)

    def add_characteristic(self, ch):
        self.characteristics.append(ch)

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
            return self.get_properties()["org.bluez.GattService1"].get(prop)
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")
    
    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattService1":
            return self.get_properties()["org.bluez.GattService1"]
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")

# -------------------------------------------------
# Characteristic Base
# -------------------------------------------------

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = f"{service.path}/char{index}"
        self.uuid = uuid
        self.flags = flags
        self.service = service.path
        self.bus = bus
        super().__init__(bus, self.path)

    def get_properties(self):
        return {
            "org.bluez.GattCharacteristic1": {
                "UUID": dbus.String(self.uuid),
                "Flags": dbus.Array([dbus.String(f) for f in self.flags], signature="s"),
                "Service": dbus.ObjectPath(self.service),
                "Notifying": dbus.Boolean(False),
                "Descriptors": dbus.Array([], signature="o"),
            }
        }
    
    @dbus.service.method(DBUS_PROP_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface == "org.bluez.GattCharacteristic1":
            return self.get_properties()["org.bluez.GattCharacteristic1"].get(prop)
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")
    
    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == "org.bluez.GattCharacteristic1":
            return self.get_properties()["org.bluez.GattCharacteristic1"]
        raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")

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
        try:
            data = json.loads(bytes(value).decode())
            active_card = data.get("card", active_card)
            print(f"✅ Switched to: {active_card}")
        except Exception as e:
            print(f"❌ Failed to parse write value: {e}")

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

    try:
        adapter = find_adapter(bus)
        print(f"✅ Found adapter: {adapter}")
    except Exception as e:
        print(f"❌ Failed to find adapter: {e}")
        sys.exit(1)

    try:
        # Create application and service hierarchy
        app = Application(bus)
        service = Service(bus)

        # Add characteristics to service
        state_char = StateCharacteristic(bus, service)
        switch_char = SwitchCharacteristic(bus, service)
        service.add_characteristic(state_char)
        service.add_characteristic(switch_char)
        
        # Add service to application
        app.add_service(service)

        # Create advertisement
        adv = Advertisement(bus)

        # Get GATT and advertising managers
        gatt_mgr = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            GATT_MANAGER_IFACE,
        )

        adv_mgr = dbus.Interface(
            bus.get_object(BLUEZ_SERVICE_NAME, adapter),
            LE_ADV_MANAGER_IFACE,
        )

        # Register the GATT application with extended timeout
        print(f"📝 Registering GATT application at {app.PATH}...")
        gatt_mgr.RegisterApplication(
            dbus.ObjectPath(app.PATH), 
            {}, 
            timeout=5000  # 5 second timeout
        )
        print("✅ GATT application registered")

        # Register the advertisement
        print(f"📝 Registering advertisement at {adv.PATH}...")
        adv_mgr.RegisterAdvertisement(
            dbus.ObjectPath(adv.PATH), 
            {}, 
            timeout=5000  # 5 second timeout
        )
        print("✅ Advertisement registered")

        print("🔊 NFC-Wallet-Dev is advertising")
        GLib.MainLoop().run()

    except dbus.exceptions.DBusException as e:
        print(f"❌ DBus Error: {e}")
        print("\nTroubleshooting tips:")
        print("1. Make sure BlueZ is running: systemctl status bluetooth")
        print("2. Check BLE adapter is up: sudo hciconfig hci0 up")
        print("3. Run as root: sudo python3 ble_wallet.py")
        print("4. Check BlueZ version: bluetoothctl --version")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
