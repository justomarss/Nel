from src.events.event_bus import EventBus

bus = EventBus()

def hello(data):
    print("Hello:", data)

bus.subscribe("wake_up", hello)

bus.emit("wake_up", "Nel oyandı.")