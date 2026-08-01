import sys

from src.core.nel import Nel
from src.errors import ApplicationError


for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def run():
    nel = Nel()

    try:
        while True:
            text = input("Sən: ")

            if text == "exit":
                break

            if text.startswith("/remember "):
                nel.remember(text[10:])
                print("Yadda saxladım.")
                continue

            try:
                print(nel.think(text))
            except ApplicationError as exc:
                print(f"Nel: {exc}")
    finally:
        nel.stop()


if __name__ == "__main__":
    run()
