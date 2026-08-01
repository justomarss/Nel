import sys

from src.core.nel import Nel


for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


nel = Nel()

while True:

    text = input("Sən: ")

    if text == "exit":
        break

    if text.startswith("/remember "):
        nel.remember(text[10:])
        print("Yadda saxladım.")
        continue

    print(nel.think(text))
