import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import json

SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
STATE_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
SWITCH_CHAR_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"

active_card = "Office"

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def add_service(self, service):
        self.services.append(service)

class Service(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = f"/service{index}"
        self.uuid = SERVICE_UUID
        self.primary = True
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def add_characteristic(self, char):
        self.characteristics.append(char)

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags):
        self.path = f"/char{index}"
        self.uuid = uuid
        self.flags = flags
        dbus.service.Object.__init__(self, bus, self.path)

class StateCharacteristic(Characteristic):
    def __init__(self, bus):
        super().__init__(bus, 0, STATE_CHAR_UUID, ["read"])

    def ReadValue(self, options):
        data = json.dumps({
            "activeCard": active_card,
            "battery": 87
        }).encode()
        return dbus.Array([dbus.Byte(b) for b in data], signature="y")

class SwitchCharacteristic(Characteristic):
    def __init__(self, bus):
        super().__init__(bus, 1, SWITCH_CHAR_UUID, ["write"])

    def WriteValue(self, value, options):
        global active_card
        payload = bytes(value).decode()
        data = json.loads(payload)
        active_card = data["card"]
        print("Switched to:", active_card)

def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    app = Application(bus)
    service = Service(bus, 0)

    service.add_characteristic(StateCharacteristic(bus))
    service.add_characteristic(SwitchCharacteristic(bus))
    app.add_service(service)

    print("BLE Wallet running as NFC-Wallet-Dev")
    loop = GLib.MainLoop()
    loop.run()

if __name__ == "__main__":
    main()
